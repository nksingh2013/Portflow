import logging
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pyotp
from fastapi import Depends, FastAPI, Form, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, get_current_principal, require_roles, verify_totp
from app.config import settings
from app.db import get_db, set_identity_context, set_public_organization_slug, set_tenant_context
from app.models import (
    AuditLog,
    Container,
    ContainerVisit,
    Customer,
    CustodyEvent,
    GateAppointment,
    Membership,
    MovementEvent,
    CustomerPortalRequest,
    OperationalInvoice,
    OperationalInvoiceLine,
    Organization,
    SaasUsageEvent,
    Tariff,
    TariffVersion,
    Terminal,
    User,
    VesselCall,
    YardSlot,
)
from app.schemas import (
    ContainerCreate,
    ContainerOut,
    CustodyReceiveInput,
    CustodyReleaseInput,
    CustomerCreate,
    CustomerOut,
    CustomerPortalGrant,
    CustomerPortalRequestCreate,
    CustomerPortalRequestOut,
    CustomerPortalUserCreate,
    GateAppointmentCreate,
    GateAppointmentOut,
    InvoiceDetailOut,
    InvoiceLineOut,
    InvoiceOut,
    MFAEnableInput,
    MFAConfirmInput,
    OrganizationOut,
    PublicMeta,
    RegisterInput,
    TariffCreate,
    TariffOut,
    TerminalCreate,
    TerminalOut,
    TokenResponse,
    VesselCallCreate,
    VesselCallOut,
    VisitCreate,
    VisitOut,
    WalkInInput,
    YardAllocationInput,
    YardSlotCreate,
    YardSlotOut,
    YardSlotView,
    YardSuggestion,
    MovementInput,
    MovementOut,
)

from app.security import create_token, decode_token, hash_password, verify_password
from app.services import (
    audit,
    ensure_customer_scope,
    ensure_terminal,
    generate_storage_invoice,
    record_visit_usage,
    to_utc,
    utc_now,
    yard_suggestions,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PortFlow API",
    version="0.1.0",
    description=(
        "India-first maritime terminal operations development MVP. "
        "External auth, port, notification, storage, GPS, and payment integrations are interfaces only."
    ),
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

db_dep = Annotated[Session, Depends(get_db)]
principal_dep = Annotated[Principal, Depends(get_current_principal)]


def _token_response(db: Session, user: User, membership: Membership, organization: Organization) -> TokenResponse:
    return TokenResponse(
        access_token=create_token(user.id, membership.organization_id, membership.id, membership.role),
        expires_in=settings.access_token_minutes * 60,
        role=membership.role,
        organization_name=organization.name,
        organization_slug=organization.slug,
        user_name=user.display_name,
    )


def _load_visit(db: Session, principal: Principal, visit_id: UUID) -> ContainerVisit:
    visit = db.scalar(
        select(ContainerVisit).where(
            ContainerVisit.id == visit_id,
            ContainerVisit.organization_id == principal.organization_id,
        )
    )
    if visit is None:
        raise HTTPException(status_code=404, detail="Container visit not found")
    if principal.membership.terminal_id and principal.membership.terminal_id != visit.terminal_id:
        raise HTTPException(status_code=403, detail="This account is limited to another terminal")
    container = db.get(Container, visit.container_id)
    if container is None:
        raise HTTPException(status_code=404, detail="Container not found")
    ensure_customer_scope(principal, container.customer_id)
    return visit


def _active_terminal_filter(statement, principal: Principal, terminal_id: UUID | None):
    if terminal_id is not None:
        if principal.membership.terminal_id and principal.membership.terminal_id != terminal_id:
            raise HTTPException(status_code=403, detail="This account is limited to another terminal")
        return statement.where(ContainerVisit.terminal_id == terminal_id)
    if principal.membership.terminal_id:
        return statement.where(ContainerVisit.terminal_id == principal.membership.terminal_id)
    return statement


def _visit_matches_request(visit: ContainerVisit, payload: VisitCreate) -> bool:
    return (
        visit.container_id == payload.container_id
        and visit.terminal_id == payload.terminal_id
        and visit.direction == payload.direction
        and visit.vessel_call_id == payload.vessel_call_id
        and visit.is_transshipment == payload.is_transshipment
    )


def _walk_in_replay(db: Session, principal: Principal, terminal: Terminal, payload: WalkInInput, event: CustodyEvent):
    visit = db.get(ContainerVisit, event.visit_id)
    container = db.get(Container, visit.container_id) if visit else None
    if (
        visit is None
        or container is None
        or visit.organization_id != principal.organization_id
        or container.organization_id != principal.organization_id
        or event.event_type != "received"
        or event.mode != payload.entry_mode
        or visit.terminal_id != terminal.id
        or container.terminal_id != terminal.id
        or visit.direction != payload.direction
        or visit.vessel_call_id != payload.vessel_call_id
        or visit.is_transshipment != payload.is_transshipment
        or container.customer_id != payload.customer_id
        or container.container_number != payload.container_number.upper()
    ):
        raise HTTPException(status_code=409, detail="Idempotency key was already used for another custody event")
    return {"visit": VisitOut.model_validate(visit), "custody_event_id": str(event.id), "duplicate": True}


def _authorized_customer(principal: Principal, customer_id: UUID) -> UUID:
    if principal.role == "customer" and principal.membership.customer_id != customer_id:
        raise HTTPException(status_code=403, detail="This customer account cannot access that record")
    return customer_id  # used as a guard before the scoped query


@app.get("/api/v1/health", tags=["system"])
def health():
    return {"status": "ok", "service": "portflow-api", "environment": settings.app_env}


@app.get("/api/v1/meta", response_model=PublicMeta, tags=["system"])
def public_meta():
    return PublicMeta(demo_mode=settings.demo_mode, google_login_enabled=False)


@app.post("/api/v1/auth/register", status_code=status.HTTP_201_CREATED, tags=["identity"])
def register(payload: RegisterInput, db: db_dep):
    """Create a tenant and its first administrator, then begin mandatory MFA setup."""
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    requested_slug = payload.organization_slug.strip().lower()
    organization_slug = requested_slug
    secret = pyotp.random_base32()
    password_hash = hash_password(payload.password)

    for attempt in range(4):
        user_id, organization_id, terminal_id, membership_id = uuid4(), uuid4(), uuid4(), uuid4()
        try:
            set_identity_context(db, user_id)
            set_tenant_context(db, organization_id)
            organization = Organization(
                id=organization_id,
                slug=organization_slug,
                name=payload.organization_name,
                legal_name=payload.organization_name,
                timezone="Asia/Kolkata",
                currency="INR",
                is_demo=False,
            )
            terminal = Terminal(
                id=terminal_id,
                organization_id=organization_id,
                code=payload.terminal_code.upper(),
                name=payload.terminal_name,
                timezone="Asia/Kolkata",
            )
            user = User(
                id=user_id,
                email=email,
                display_name=payload.admin_name,
                password_hash=password_hash,
                mfa_secret=secret,
                mfa_enabled=False,
            )
            membership = Membership(
                id=membership_id,
                user_id=user_id,
                organization_id=organization_id,
                organization_slug=organization_slug,
                role="organization_admin",
            )
            # These models do not declare ORM relationships, so make their
            # foreign-key order explicit for PostgreSQL's signup transaction.
            db.add(organization)
            db.flush()
            db.add_all([terminal, user])
            db.flush()
            db.add(membership)
            db.commit()
            break
        except IntegrityError as exc:
            db.rollback()
            constraint = _integrity_constraint_name(exc)
            conflict = _registration_conflict(constraint)
            logger.warning("Organization registration rejected by database constraint: %s", constraint or "unknown")

            # Organization slugs are globally unique. Automatically retry with a
            # short suffix so a taken slug cannot block a new college demo workspace.
            if conflict == "organization_slug" and attempt < 3:
                slug_prefix = requested_slug[:73].rstrip("-")
                organization_slug = f"{slug_prefix}-{secrets.token_hex(3)}"
                continue

            if conflict == "account_email":
                detail = "An account with this email already exists. Sign in with that account or use a different email."
            elif conflict == "terminal_code":
                detail = "That terminal code is already in use. Choose a different terminal code."
            elif conflict == "organization_slug":
                detail = "We could not find an unused organization slug. Please try again."
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Workspace setup hit an unexpected database conflict. Please try again; if it repeats, contact support.",
                ) from exc
            raise HTTPException(status_code=409, detail=detail) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    setup_token = create_token(
        user_id,
        organization_id,
        membership_id,
        "organization_admin",
        scope="mfa_setup",
        lifetime=timedelta(minutes=15),
    )
    return {
        "setup_token": setup_token,
        "mfa_secret": secret,
        "mfa_uri": pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="PortFlow"),
        "organization_slug": organization_slug,
        "message": "Add this account to an authenticator app, then confirm the current code.",
    }


def _integrity_constraint_name(exc: IntegrityError) -> str:
    diagnostic = getattr(exc.orig, "diag", None)
    constraint = getattr(diagnostic, "constraint_name", None)
    if constraint:
        return str(constraint).lower()
    # Some drivers (including SQLite in tests) do not expose constraint
    # metadata. Classify their message without logging any submitted values.
    message = str(exc.orig).lower()
    if "organizations.slug" in message or "ix_organizations_slug" in message:
        return "organizations_slug"
    if "terminals.code" in message or "uq_terminal_org_code" in message:
        return "terminals_code"
    if "users.email" in message or "ix_users_email" in message:
        return "users_email"
    return "unknown"


def _registration_conflict(constraint: str) -> str | None:
    if "organization" in constraint and "slug" in constraint or "organizations.slug" in constraint:
        return "organization_slug"
    if "terminal" in constraint and "code" in constraint or "terminals.code" in constraint:
        return "terminal_code"
    if "user" in constraint and "email" in constraint or "users.email" in constraint:
        return "account_email"
    return None


@app.post("/api/v1/auth/mfa/confirm", response_model=TokenResponse, tags=["identity"])
def confirm_mfa(payload: MFAConfirmInput, db: db_dep):
    try:
        claims = decode_token(payload.setup_token, expected_scope="mfa_setup")
        user_id, organization_id, membership_id = UUID(claims["sub"]), UUID(claims["org"]), UUID(claims["membership"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="MFA setup session expired; register again") from None
    set_identity_context(db, user_id)
    set_tenant_context(db, organization_id)
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.is_active.is_(True),
        )
    )
    if not user or not membership or not user.mfa_secret:
        raise HTTPException(status_code=401, detail="MFA setup session is no longer valid")
    if not pyotp.TOTP(user.mfa_secret).verify(payload.code.strip(), valid_window=1):
        raise HTTPException(status_code=401, detail="Authenticator code is not valid")
    user.mfa_enabled = True
    organization = db.get(Organization, organization_id)
    db.commit()
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _token_response(db, user, membership, organization)


@app.post("/api/v1/auth/token", response_model=TokenResponse, tags=["identity"])
def login(
    db: db_dep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    mfa_code: Annotated[str | None, Form()] = None,
    organization_slug: Annotated[str | None, Form()] = None,
):
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect", headers={"WWW-Authenticate": "Bearer"})
    set_identity_context(db, user.id)
    memberships = list(
        db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.is_active.is_(True)))
    )
    if organization_slug:
        membership = next((item for item in memberships if item.organization_slug == organization_slug.strip().lower()), None)
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        membership = None
    if membership is None:
        raise HTTPException(status_code=401, detail="No active access for that organization")
    set_tenant_context(db, membership.organization_id)
    if membership.role in ("organization_admin", "platform_super_admin"):
        if not user.mfa_enabled:
            raise HTTPException(status_code=403, detail="Administrator MFA setup is required before sign-in")
        if not verify_totp(user, mfa_code):
            raise HTTPException(status_code=401, detail="Authenticator code is required or invalid")
    elif user.mfa_enabled and not verify_totp(user, mfa_code):
        raise HTTPException(status_code=401, detail="Authenticator code is required or invalid")
    organization = db.get(Organization, membership.organization_id)
    if organization is None:
        raise HTTPException(status_code=401, detail="No active access for that organization")
    return _token_response(db, user, membership, organization)


@app.post("/api/v1/auth/customer-requests", status_code=201, tags=["identity"])
def request_customer_portal_access(payload: CustomerPortalRequestCreate, db: db_dep):
    """Queue a customer access request for the named organization administrators."""
    organization_slug = payload.organization_slug.strip().lower()
    set_public_organization_slug(db, organization_slug)
    organization_id = db.scalar(select(Organization.id).where(Organization.slug == organization_slug))
    if organization_id is None:
        raise HTTPException(status_code=404, detail="Organization not found. Check the organization slug with your terminal contact.")

    set_tenant_context(db, organization_id)
    email = str(payload.email).strip().lower()
    existing = db.scalar(
        select(CustomerPortalRequest).where(
            CustomerPortalRequest.organization_id == organization_id,
            CustomerPortalRequest.email == email,
            CustomerPortalRequest.status == "pending",
        )
    )
    if existing:
        return {
            "status": "pending",
            "request_id": str(existing.id),
            "message": "Your request is already waiting for the administrator.",
        }

    access_request = CustomerPortalRequest(
        organization_id=organization_id,
        company_name=payload.company_name.strip(),
        contact_name=payload.contact_name.strip(),
        email=email,
        message=payload.message.strip(),
    )
    db.add(access_request)
    try:
        db.flush()
        db.add(
            AuditLog(
                organization_id=organization_id,
                action="customer.portal_access_requested",
                entity_type="customer_portal_request",
                entity_id=str(access_request.id),
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An access request from this email is already pending") from exc
    return {
        "status": "pending",
        "request_id": str(access_request.id),
        "message": "Your request has been sent to the organization administrator.",
    }


@app.get("/api/v1/auth/providers", tags=["identity"])
def auth_providers():
    return {"email_password": True, "google": {"enabled": False, "reason": "OAuth credentials are not configured"}, "mfa": {"admin_required": True, "method": "TOTP"}}


@app.post("/api/v1/auth/mfa/setup", tags=["identity"])
def setup_optional_mfa(principal: principal_dep, db: db_dep):
    if principal.user.mfa_enabled:
        raise HTTPException(status_code=409, detail="Multi-factor authentication is already enabled")
    secret = pyotp.random_base32()
    principal.user.mfa_secret = secret
    audit(db, principal, "user.mfa_enrollment_started", "user", principal.user.id, principal.membership.terminal_id)
    db.commit()
    return {
        "mfa_secret": secret,
        "mfa_uri": pyotp.TOTP(secret).provisioning_uri(name=principal.user.email, issuer_name="PortFlow"),
        "message": "Add this account to an authenticator app, then confirm the current code.",
    }


@app.post("/api/v1/auth/mfa/enable", tags=["identity"])
def enable_optional_mfa(payload: MFAEnableInput, principal: principal_dep, db: db_dep):
    if principal.user.mfa_enabled:
        raise HTTPException(status_code=409, detail="Multi-factor authentication is already enabled")
    if not principal.user.mfa_secret or not pyotp.TOTP(principal.user.mfa_secret).verify(payload.code.strip(), valid_window=1):
        raise HTTPException(status_code=401, detail="Authenticator code is not valid")
    principal.user.mfa_enabled = True
    audit(db, principal, "user.mfa_enabled", "user", principal.user.id, principal.membership.terminal_id)
    db.commit()
    return {"enabled": True}


@app.get("/api/v1/me", tags=["identity"])
def me(principal: principal_dep, db: db_dep):
    organization = db.get(Organization, principal.organization_id)
    return {
        "id": str(principal.user.id),
        "email": principal.user.email,
        "display_name": principal.user.display_name,
        "role": principal.role,
        "organization": OrganizationOut.model_validate(organization),
        "terminal_id": str(principal.membership.terminal_id) if principal.membership.terminal_id else None,
        "customer_id": str(principal.membership.customer_id) if principal.membership.customer_id else None,
    }


@app.get("/api/v1/organizations/current", response_model=OrganizationOut, tags=["organizations"])
def get_organization(principal: principal_dep, db: db_dep):
    organization = db.get(Organization, principal.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@app.get("/api/v1/terminals", response_model=list[TerminalOut], tags=["organizations"])
def list_terminals(principal: principal_dep, db: db_dep):
    statement = select(Terminal).where(Terminal.organization_id == principal.organization_id, Terminal.is_active.is_(True))
    if principal.membership.terminal_id:
        statement = statement.where(Terminal.id == principal.membership.terminal_id)
    return list(db.scalars(statement.order_by(Terminal.name)))


@app.post("/api/v1/terminals", response_model=TerminalOut, status_code=201, tags=["organizations"])
def create_terminal(payload: TerminalCreate, principal: Principal = Depends(require_roles("organization_admin")), db: Session = Depends(get_db)):
    terminal = Terminal(
        organization_id=principal.organization_id,
        code=payload.code.upper(),
        name=payload.name,
        timezone=payload.timezone,
        address=payload.address,
    )
    db.add(terminal)
    try:
        db.flush()
        audit(db, principal, "terminal.created", "terminal", terminal.id, terminal.id)
        db.refresh(terminal)
        db.commit()
        return terminal
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A terminal with that code already exists") from exc


@app.get("/api/v1/customers", response_model=list[CustomerOut], tags=["customers"])
def list_customers(principal: principal_dep, db: db_dep, terminal_id: UUID | None = None):
    statement = select(Customer).where(Customer.organization_id == principal.organization_id)
    if terminal_id:
        ensure_terminal(db, principal, terminal_id)
        statement = statement.where(Customer.terminal_id == terminal_id)
    elif principal.membership.terminal_id:
        statement = statement.where(Customer.terminal_id == principal.membership.terminal_id)
    if principal.membership.customer_id:
        statement = statement.where(Customer.id == principal.membership.customer_id)
    return list(db.scalars(statement.order_by(Customer.name)))


@app.post("/api/v1/customers", response_model=CustomerOut, status_code=201, tags=["customers"])
def create_customer(payload: CustomerCreate, terminal_id: UUID, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager")), db: Session = Depends(get_db)):
    terminal = ensure_terminal(db, principal, terminal_id)
    customer = Customer(
        organization_id=principal.organization_id,
        terminal_id=terminal.id,
        code=payload.code.upper(),
        name=payload.name,
        email=str(payload.email or ""),
    )
    db.add(customer)
    try:
        db.flush()
        audit(db, principal, "customer.created", "customer", customer.id, terminal.id)
        db.refresh(customer)
        db.commit()
        return customer
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A customer with that code already exists") from exc


@app.get("/api/v1/portal-access-requests", response_model=list[CustomerPortalRequestOut], tags=["customer portal"])
def list_customer_portal_requests(
    principal: Principal = Depends(require_roles("organization_admin")),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(CustomerPortalRequest)
            .where(
                CustomerPortalRequest.organization_id == principal.organization_id,
                CustomerPortalRequest.status == "pending",
            )
            .order_by(CustomerPortalRequest.created_at.desc())
            .limit(100)
        )
    )


@app.post("/api/v1/portal-access-requests/{request_id}/approve", tags=["customer portal"])
def approve_customer_portal_request(
    request_id: UUID,
    payload: CustomerPortalGrant,
    principal: Principal = Depends(require_roles("organization_admin")),
    db: Session = Depends(get_db),
):
    access_request = db.scalar(
        select(CustomerPortalRequest)
        .where(
            CustomerPortalRequest.id == request_id,
            CustomerPortalRequest.organization_id == principal.organization_id,
            CustomerPortalRequest.status == "pending",
        )
        .with_for_update()
    )
    if access_request is None:
        raise HTTPException(status_code=404, detail="Pending customer access request not found")

    customer = db.scalar(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.organization_id == principal.organization_id,
            Customer.is_active.is_(True),
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Active customer account not found")
    if db.scalar(select(User.id).where(User.email == access_request.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=access_request.email,
        display_name=access_request.contact_name,
        password_hash=hash_password(payload.password),
        is_active=True,
        mfa_enabled=False,
    )
    db.add(user)
    try:
        db.flush()
        set_identity_context(db, user.id)
        membership = Membership(
            user_id=user.id,
            organization_id=principal.organization_id,
            organization_slug=principal.membership.organization_slug,
            terminal_id=customer.terminal_id,
            customer_id=customer.id,
            role="customer",
            is_active=True,
        )
        db.add(membership)
        access_request.status = "approved"
        access_request.customer_id = customer.id
        access_request.terminal_id = customer.terminal_id
        access_request.reviewed_by_id = principal.user.id
        access_request.reviewed_at = utc_now()
        db.flush()
        audit(db, principal, "customer.portal_access_approved", "customer_portal_request", access_request.id, customer.terminal_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This request was already reviewed or the email already has an account") from exc

    return {
        "email": user.email,
        "display_name": user.display_name,
        "organization_slug": membership.organization_slug,
        "customer_name": customer.name,
        "role": "customer",
    }


@app.post("/api/v1/portal-access-requests/{request_id}/reject", tags=["customer portal"])
def reject_customer_portal_request(
    request_id: UUID,
    principal: Principal = Depends(require_roles("organization_admin")),
    db: Session = Depends(get_db),
):
    access_request = db.scalar(
        select(CustomerPortalRequest)
        .where(
            CustomerPortalRequest.id == request_id,
            CustomerPortalRequest.organization_id == principal.organization_id,
            CustomerPortalRequest.status == "pending",
        )
        .with_for_update()
    )
    if access_request is None:
        raise HTTPException(status_code=404, detail="Pending customer access request not found")
    access_request.status = "rejected"
    access_request.reviewed_by_id = principal.user.id
    access_request.reviewed_at = utc_now()
    audit(db, principal, "customer.portal_access_rejected", "customer_portal_request", access_request.id)
    db.commit()
    return {"status": "rejected"}


@app.post("/api/v1/customers/{customer_id}/portal-users", status_code=201, tags=["customers"])
def create_customer_portal_user(
    customer_id: UUID,
    payload: CustomerPortalUserCreate,
    principal: Principal = Depends(require_roles("organization_admin")),
    db: Session = Depends(get_db),
):
    """Create a customer-scoped sign-in; credentials are handed to the customer by the admin."""
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == principal.organization_id,
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer account not found")
    if not customer.is_active:
        raise HTTPException(status_code=409, detail="This customer account is inactive")

    email = str(payload.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
        mfa_enabled=False,
    )
    db.add(user)
    try:
        # Membership RLS permits only the authenticated user. Switch the
        # transaction-local identity to the new user before inserting it.
        db.flush()
        set_identity_context(db, user.id)
        membership = Membership(
            user_id=user.id,
            organization_id=principal.organization_id,
            organization_slug=principal.membership.organization_slug,
            terminal_id=customer.terminal_id,
            customer_id=customer.id,
            role="customer",
            is_active=True,
        )
        db.add(membership)
        db.flush()
        audit(db, principal, "customer.portal_user_created", "customer", customer.id, customer.terminal_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc

    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "email": user.email,
        "role": "customer",
        "organization_slug": membership.organization_slug,
        "customer_name": customer.name,
    }


@app.get("/api/v1/containers", response_model=list[ContainerOut], tags=["containers"])
def list_containers(
    principal: principal_dep,
    db: db_dep,
    terminal_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=32),
):
    statement = select(Container).where(Container.organization_id == principal.organization_id)
    if terminal_id:
        ensure_terminal(db, principal, terminal_id)
        statement = statement.where(Container.terminal_id == terminal_id)
    elif principal.membership.terminal_id:
        statement = statement.where(Container.terminal_id == principal.membership.terminal_id)
    if principal.role == "customer" or principal.membership.customer_id:
        statement = statement.where(Container.customer_id == principal.membership.customer_id)
    if search:
        statement = statement.where(Container.container_number.ilike(f"%{search.strip()}%"))
    return list(db.scalars(statement.order_by(Container.created_at.desc()).limit(200)))


@app.post("/api/v1/containers", response_model=ContainerOut, status_code=201, tags=["containers"])
def create_container(payload: ContainerCreate, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    ensure_terminal(db, principal, payload.terminal_id)
    customer = db.scalar(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.organization_id == principal.organization_id,
            Customer.terminal_id == payload.terminal_id,
            Customer.is_active.is_(True),
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found for this terminal")
    container = Container(
        organization_id=principal.organization_id,
        terminal_id=payload.terminal_id,
        customer_id=customer.id,
        container_number=payload.container_number,
        size_feet=payload.size_feet,
        category=payload.category,
        is_empty=payload.is_empty,
        seal_number=payload.seal_number,
        cargo_description=payload.cargo_description,
    )
    db.add(container)
    try:
        db.flush()
        db.refresh(container)
        audit(db, principal, "container.created", "container", container.id, payload.terminal_id)
        db.commit()
        return container
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That container already exists in this organization") from exc


@app.get("/api/v1/visits", response_model=list[VisitOut], tags=["visits"])
def list_visits(principal: principal_dep, db: db_dep, terminal_id: UUID | None = None, status_filter: str | None = None):
    statement = select(ContainerVisit).where(ContainerVisit.organization_id == principal.organization_id)
    statement = _active_terminal_filter(statement, principal, terminal_id)
    if status_filter:
        statement = statement.where(ContainerVisit.status == status_filter)
    if principal.role == "customer" or principal.membership.customer_id:
        statement = statement.join(Container, Container.id == ContainerVisit.container_id).where(
            Container.customer_id == principal.membership.customer_id
        )
    return list(db.scalars(statement.order_by(ContainerVisit.created_at.desc()).limit(200)))


@app.post("/api/v1/visits", response_model=VisitOut, status_code=201, tags=["visits"])
def create_visit(payload: VisitCreate, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    ensure_terminal(db, principal, payload.terminal_id)
    existing = db.scalar(
        select(ContainerVisit).where(
            ContainerVisit.organization_id == principal.organization_id,
            ContainerVisit.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        if not _visit_matches_request(existing, payload):
            raise HTTPException(status_code=409, detail="Idempotency key was already used for another visit")
        return existing
    container = db.scalar(
        select(Container).where(
            Container.id == payload.container_id,
            Container.organization_id == principal.organization_id,
            Container.terminal_id == payload.terminal_id,
        ).with_for_update()
    )
    if container is None:
        raise HTTPException(status_code=404, detail="Container not found for this terminal")
    existing = db.scalar(
        select(ContainerVisit).where(
            ContainerVisit.organization_id == principal.organization_id,
            ContainerVisit.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        if not _visit_matches_request(existing, payload):
            raise HTTPException(status_code=409, detail="Idempotency key was already used for another visit")
        return existing
    active_visit = db.scalar(
        select(ContainerVisit.id).where(
            ContainerVisit.organization_id == principal.organization_id,
            ContainerVisit.terminal_id == payload.terminal_id,
            ContainerVisit.container_id == container.id,
            ContainerVisit.status.in_(("expected", "in_terminal")),
        ).limit(1)
    )
    if active_visit:
        raise HTTPException(status_code=409, detail="This container already has an active visit")
    if payload.vessel_call_id and db.scalar(
        select(VesselCall.id).where(
            VesselCall.id == payload.vessel_call_id,
            VesselCall.organization_id == principal.organization_id,
            VesselCall.terminal_id == payload.terminal_id,
        )
    ) is None:
        raise HTTPException(status_code=404, detail="Vessel call not found for this terminal")
    visit = ContainerVisit(
        organization_id=principal.organization_id,
        terminal_id=payload.terminal_id,
        container_id=container.id,
        vessel_call_id=payload.vessel_call_id,
        visit_reference=f"PF-{datetime.now(UTC):%y%m%d}-{secrets.token_hex(3).upper()}",
        direction=payload.direction,
        is_transshipment=payload.is_transshipment,
        status="expected",
        idempotency_key=payload.idempotency_key,
        created_by_id=principal.user.id,
    )
    db.add(visit)
    try:
        db.flush()
        record_visit_usage(db, visit, container)
        audit(db, principal, "visit.created", "container_visit", visit.id, visit.terminal_id)
        db.refresh(visit)
        db.commit()
        return visit
    except IntegrityError as exc:
        db.rollback()
        set_tenant_context(db, principal.organization_id)
        existing = db.scalar(
            select(ContainerVisit).where(
                ContainerVisit.organization_id == principal.organization_id,
                ContainerVisit.idempotency_key == payload.idempotency_key,
            )
        )
        if existing and _visit_matches_request(existing, payload):
            return existing
        raise HTTPException(status_code=409, detail="That visit request conflicts with an existing record") from exc


@app.post("/api/v1/gate/walk-ins", status_code=201, tags=["gate"])
def create_walk_in(payload: WalkInInput, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff", "transport_operator")), db: Session = Depends(get_db)):
    terminal = ensure_terminal(db, principal, payload.terminal_id)
    prior_event = db.scalar(
        select(CustodyEvent).where(
            CustodyEvent.organization_id == principal.organization_id,
            CustodyEvent.idempotency_key == payload.idempotency_key,
        )
    )
    if prior_event:
        return _walk_in_replay(db, principal, terminal, payload, prior_event)
    customer = db.scalar(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.organization_id == principal.organization_id,
            Customer.terminal_id == terminal.id,
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found for this terminal")
    if payload.vessel_call_id and db.scalar(select(VesselCall.id).where(
        VesselCall.id == payload.vessel_call_id,
        VesselCall.organization_id == principal.organization_id,
        VesselCall.terminal_id == terminal.id,
    )) is None:
        raise HTTPException(status_code=404, detail="Vessel call not found for this terminal")
    container = db.scalar(
        select(Container).where(
            Container.organization_id == principal.organization_id,
            Container.container_number == payload.container_number,
        ).with_for_update()
    )
    if container and (container.terminal_id != terminal.id or container.customer_id != customer.id):
        raise HTTPException(status_code=409, detail="This container is already registered to a different customer or terminal")
    prior_event = db.scalar(
        select(CustodyEvent).where(
            CustodyEvent.organization_id == principal.organization_id,
            CustodyEvent.idempotency_key == payload.idempotency_key,
        )
    )
    if prior_event:
        return _walk_in_replay(db, principal, terminal, payload, prior_event)
    if container:
        active_visit = db.scalar(
            select(ContainerVisit.id).where(
                ContainerVisit.organization_id == principal.organization_id,
                ContainerVisit.terminal_id == terminal.id,
                ContainerVisit.container_id == container.id,
                ContainerVisit.status.in_(("expected", "in_terminal")),
            ).limit(1)
        )
        if active_visit:
            raise HTTPException(status_code=409, detail="This container already has an active visit")
    try:
        if container is None:
            container = Container(
                organization_id=principal.organization_id,
                terminal_id=terminal.id,
                customer_id=customer.id,
                container_number=payload.container_number,
                size_feet=payload.size_feet,
                category=payload.category,
                is_empty=payload.is_empty,
            )
            db.add(container)
            db.flush()
        visit = ContainerVisit(
            organization_id=principal.organization_id,
            terminal_id=terminal.id,
            container_id=container.id,
            vessel_call_id=payload.vessel_call_id,
            visit_reference=f"PF-{datetime.now(UTC):%y%m%d}-{secrets.token_hex(3).upper()}",
            direction=payload.direction,
            is_transshipment=payload.is_transshipment,
            status="in_terminal",
            entry_mode=payload.entry_mode,
            custody_received_at=to_utc(payload.event_at),
            idempotency_key=payload.idempotency_key,
            created_by_id=principal.user.id,
        )
        db.add(visit)
        db.flush()
        event = CustodyEvent(
            organization_id=principal.organization_id,
            terminal_id=terminal.id,
            visit_id=visit.id,
            event_type="received",
            mode=payload.entry_mode,
            event_at=visit.custody_received_at,
            idempotency_key=payload.idempotency_key,
            actor_id=principal.user.id,
        )
        db.add(event)
        record_visit_usage(db, visit, container)
        audit(db, principal, "gate.walk_in_received", "container_visit", visit.id, terminal.id, {"mode": payload.entry_mode})
        db.flush()
        db.refresh(visit)
        db.refresh(event)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        set_tenant_context(db, principal.organization_id)
        prior_event = db.scalar(
            select(CustodyEvent).where(
                CustodyEvent.organization_id == principal.organization_id,
                CustodyEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if prior_event:
            return _walk_in_replay(db, principal, terminal, payload, prior_event)
        raise HTTPException(status_code=409, detail="That walk-in request conflicts with an existing record") from exc
    return {"visit": VisitOut.model_validate(visit), "custody_event_id": str(event.id), "duplicate": False}


@app.post("/api/v1/visits/{visit_id}/custody/receive", response_model=VisitOut, tags=["custody"])
def receive_custody(visit_id: UUID, payload: CustodyReceiveInput, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff", "transport_operator")), db: Session = Depends(get_db)):
    visit = _load_visit(db, principal, visit_id)
    duplicate = db.scalar(
        select(CustodyEvent).where(
            CustodyEvent.organization_id == principal.organization_id,
            CustodyEvent.idempotency_key == payload.idempotency_key,
        )
    )
    if duplicate:
        if duplicate.visit_id != visit.id or duplicate.event_type != "received" or duplicate.mode != payload.mode:
            raise HTTPException(status_code=409, detail="Idempotency key was used for another custody event")
        return visit
    if visit.custody_received_at is not None:
        raise HTTPException(status_code=409, detail="Custody has already been received for this visit")
    event_at = to_utc(payload.event_at)
    visit.custody_received_at = event_at
    visit.entry_mode = payload.mode
    visit.status = "in_terminal"
    event = CustodyEvent(
        organization_id=principal.organization_id,
        terminal_id=visit.terminal_id,
        visit_id=visit.id,
        event_type="received",
        mode=payload.mode,
        event_at=event_at,
        idempotency_key=payload.idempotency_key,
        external_reference=payload.external_reference,
        actor_id=principal.user.id,
    )
    db.add(event)
    audit(db, principal, "custody.received", "container_visit", visit.id, visit.terminal_id, {"mode": payload.mode})
    db.flush()
    db.refresh(visit)
    db.commit()
    return visit


@app.post("/api/v1/visits/{visit_id}/custody/release", tags=["custody"])
def release_custody(visit_id: UUID, payload: CustodyReleaseInput, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    visit = _load_visit(db, principal, visit_id)
    terminal = ensure_terminal(db, principal, visit.terminal_id)
    duplicate = db.scalar(
        select(CustodyEvent).where(
            CustodyEvent.organization_id == principal.organization_id,
            CustodyEvent.idempotency_key == payload.idempotency_key,
        )
    )
    if duplicate:
        if duplicate.visit_id != visit.id or duplicate.event_type != "released" or duplicate.mode != payload.mode:
            raise HTTPException(status_code=409, detail="Idempotency key was used for another custody event")
        invoice = db.scalar(
            select(OperationalInvoice)
            .join(OperationalInvoiceLine, OperationalInvoiceLine.invoice_id == OperationalInvoice.id)
            .where(OperationalInvoiceLine.visit_id == visit.id)
        )
        return {"visit": VisitOut.model_validate(visit), "invoice": InvoiceOut.model_validate(invoice) if invoice else None, "duplicate": True}
    if visit.custody_received_at is None:
        raise HTTPException(status_code=409, detail="Custody must be received before release")
    if visit.custody_released_at is not None:
        raise HTTPException(status_code=409, detail="Custody has already been released for this visit")
    event_at = to_utc(payload.event_at)
    if event_at < to_utc(visit.custody_received_at):
        raise HTTPException(status_code=422, detail="Release time cannot precede custody receipt")
    visit.custody_released_at = event_at
    visit.release_mode = payload.mode
    visit.status = "released"
    visit.yard_slot_id = None
    db.add(
        CustodyEvent(
            organization_id=principal.organization_id,
            terminal_id=visit.terminal_id,
            visit_id=visit.id,
            event_type="released",
            mode=payload.mode,
            event_at=event_at,
            idempotency_key=payload.idempotency_key,
            external_reference=payload.external_reference,
            actor_id=principal.user.id,
        )
    )
    container = db.get(Container, visit.container_id)
    customer = db.get(Customer, container.customer_id) if container else None
    if container is None or customer is None:
        raise HTTPException(status_code=404, detail="Container/customer record not found")
    invoice, created = generate_storage_invoice(db, principal, visit, container, customer, terminal)
    audit(db, principal, "custody.released", "container_visit", visit.id, visit.terminal_id, {"mode": payload.mode})
    db.flush()
    db.refresh(visit)
    if invoice:
        db.refresh(invoice)
    db.commit()
    return {"visit": VisitOut.model_validate(visit), "invoice": InvoiceOut.model_validate(invoice) if invoice else None, "invoice_created": created, "invoice_note": None if invoice else "No published tariff applied at custody receipt; operational invoice was not created."}


@app.get("/api/v1/yard/slots", response_model=list[YardSlotView], tags=["yard"])
def list_yard_slots(terminal_id: UUID, principal: principal_dep, db: db_dep):
    ensure_terminal(db, principal, terminal_id)
    slots = list(
        db.scalars(
            select(YardSlot).where(
                YardSlot.organization_id == principal.organization_id,
                YardSlot.terminal_id == terminal_id,
            ).order_by(YardSlot.block, YardSlot.bay, YardSlot.row, YardSlot.tier)
        )
    )
    active_visits = list(
        db.scalars(
            select(ContainerVisit).where(
                ContainerVisit.organization_id == principal.organization_id,
                ContainerVisit.terminal_id == terminal_id,
                ContainerVisit.status == "in_terminal",
                ContainerVisit.yard_slot_id.is_not(None),
            )
        )
    )
    visit_by_slot = {visit.yard_slot_id: visit for visit in active_visits}
    result = []
    for slot in slots:
        visit = visit_by_slot.get(slot.id)
        container = db.get(Container, visit.container_id) if visit else None
        data = YardSlotOut.model_validate(slot).model_dump()
        data.update(
            occupied=visit is not None,
            current_visit_id=visit.id if visit else None,
            current_container_number=container.container_number if container else None,
        )
        result.append(YardSlotView.model_validate(data))
    return result


@app.post("/api/v1/yard/slots", response_model=YardSlotOut, status_code=201, tags=["yard"])
def create_yard_slot(payload: YardSlotCreate, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager")), db: Session = Depends(get_db)):
    ensure_terminal(db, principal, payload.terminal_id)
    slot = YardSlot(organization_id=principal.organization_id, **payload.model_dump())
    db.add(slot)
    try:
        db.flush()
        audit(db, principal, "yard_slot.created", "yard_slot", slot.id, slot.terminal_id)
        db.refresh(slot)
        db.commit()
        return slot
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A slot with that code already exists in this terminal") from exc


@app.get("/api/v1/yard/suggestions", response_model=list[YardSuggestion], tags=["yard"])
def get_yard_suggestions(visit_id: UUID, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    visit = _load_visit(db, principal, visit_id)
    if visit.status != "in_terminal":
        raise HTTPException(status_code=409, detail="Yard allocation is available after custody receipt")
    container = db.get(Container, visit.container_id)
    items = yard_suggestions(db, principal.organization_id, visit.terminal_id, container.category, visit.id)
    return [YardSuggestion(slot_id=slot.id, code=slot.code, score=score, reason=reason) for slot, score, reason in items]


@app.post("/api/v1/yard/allocate", tags=["yard"])
def allocate_yard_slot(payload: YardAllocationInput, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    visit = _load_visit(db, principal, payload.visit_id)
    if visit.status != "in_terminal":
        raise HTTPException(status_code=409, detail="Only a container in terminal custody can be allocated")
    container = db.get(Container, visit.container_id)
    if payload.slot_id:
        slot = db.scalar(
            select(YardSlot).where(
                YardSlot.id == payload.slot_id,
                YardSlot.organization_id == principal.organization_id,
                YardSlot.terminal_id == visit.terminal_id,
                YardSlot.blocked.is_(False),
            )
        )
        if slot is None:
            raise HTTPException(status_code=404, detail="Available yard slot not found")
        if slot.container_category not in (container.category, "GENERAL"):
            raise HTTPException(status_code=422, detail="Slot category does not match this container")
    else:
        suggestions = yard_suggestions(db, principal.organization_id, visit.terminal_id, container.category, visit.id, limit=1)
        if not suggestions:
            raise HTTPException(status_code=409, detail="No compatible yard slot is available")
        slot = suggestions[0][0]
    occupant = db.scalar(
        select(ContainerVisit).where(
            ContainerVisit.organization_id == principal.organization_id,
            ContainerVisit.terminal_id == visit.terminal_id,
            ContainerVisit.yard_slot_id == slot.id,
            ContainerVisit.status == "in_terminal",
            ContainerVisit.id != visit.id,
        )
    )
    if occupant:
        raise HTTPException(status_code=409, detail="That yard slot is already occupied")
    old_slot_id = visit.yard_slot_id
    visit.yard_slot_id = slot.id
    movement = MovementEvent(
        organization_id=principal.organization_id,
        terminal_id=visit.terminal_id,
        visit_id=visit.id,
        from_slot_id=old_slot_id,
        to_slot_id=slot.id,
        movement_type="yard_in" if old_slot_id is None else "yard_rehandle",
        notes="Rule-based compatible slot selection" if payload.slot_id is None else "Manual slot selection",
        actor_id=principal.user.id,
    )
    db.add(movement)
    audit(db, principal, "yard.allocated", "container_visit", visit.id, visit.terminal_id, {"slot_id": str(slot.id)})
    db.flush()
    db.refresh(visit)
    db.refresh(slot)
    db.refresh(movement)
    db.commit()
    return {"visit": VisitOut.model_validate(visit), "slot": YardSlotOut.model_validate(slot), "movement": MovementOut.model_validate(movement)}


@app.get("/api/v1/visits/{visit_id}/movements", response_model=list[MovementOut], tags=["movements"])
def list_movements(visit_id: UUID, principal: principal_dep, db: db_dep):
    visit = _load_visit(db, principal, visit_id)
    if principal.role == "customer":
        raise HTTPException(status_code=403, detail="Movement history is available in the customer portal summary only")
    return list(
        db.scalars(
            select(MovementEvent).where(
                MovementEvent.organization_id == principal.organization_id,
                MovementEvent.visit_id == visit.id,
            ).order_by(MovementEvent.moved_at.desc())
        )
    )


@app.post("/api/v1/visits/{visit_id}/movements", response_model=MovementOut, status_code=201, tags=["movements"])
def create_movement(visit_id: UUID, payload: MovementInput, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    visit = _load_visit(db, principal, visit_id)
    if visit.status != "in_terminal":
        raise HTTPException(status_code=409, detail="Movement requires active terminal custody")
    old_slot_id = visit.yard_slot_id
    if payload.to_slot_id:
        slot = db.scalar(
            select(YardSlot).where(
                YardSlot.id == payload.to_slot_id,
                YardSlot.organization_id == principal.organization_id,
                YardSlot.terminal_id == visit.terminal_id,
                YardSlot.blocked.is_(False),
            )
        )
        if slot is None:
            raise HTTPException(status_code=404, detail="Yard slot not found")
        container = db.get(Container, visit.container_id)
        if slot.container_category not in (container.category, "GENERAL"):
            raise HTTPException(status_code=422, detail="Slot category does not match this container")
        occupant = db.scalar(
            select(ContainerVisit.id).where(
                ContainerVisit.organization_id == principal.organization_id,
                ContainerVisit.terminal_id == visit.terminal_id,
                ContainerVisit.yard_slot_id == slot.id,
                ContainerVisit.status == "in_terminal",
                ContainerVisit.id != visit.id,
            )
        )
        if occupant:
            raise HTTPException(status_code=409, detail="That yard slot is already occupied")
        visit.yard_slot_id = slot.id
    movement = MovementEvent(
        organization_id=principal.organization_id,
        terminal_id=visit.terminal_id,
        visit_id=visit.id,
        from_slot_id=old_slot_id,
        to_slot_id=payload.to_slot_id,
        movement_type=payload.movement_type,
        notes=payload.notes,
        actor_id=principal.user.id,
    )
    db.add(movement)
    audit(db, principal, "movement.recorded", "container_visit", visit.id, visit.terminal_id, {"movement_type": payload.movement_type})
    db.flush()
    db.refresh(movement)
    db.commit()
    return movement


@app.get("/api/v1/vessels", response_model=list[VesselCallOut], tags=["vessels"])
def list_vessels(principal: principal_dep, db: db_dep, terminal_id: UUID | None = None):
    statement = select(VesselCall).where(VesselCall.organization_id == principal.organization_id)
    if terminal_id:
        ensure_terminal(db, principal, terminal_id)
        statement = statement.where(VesselCall.terminal_id == terminal_id)
    elif principal.membership.terminal_id:
        statement = statement.where(VesselCall.terminal_id == principal.membership.terminal_id)
    return list(db.scalars(statement.order_by(VesselCall.eta.asc().nullslast()).limit(100)))


@app.post("/api/v1/vessels", response_model=VesselCallOut, status_code=201, tags=["vessels"])
def create_vessel(payload: VesselCallCreate, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    ensure_terminal(db, principal, payload.terminal_id)
    vessel = VesselCall(organization_id=principal.organization_id, **payload.model_dump())
    db.add(vessel)
    try:
        db.flush()
        audit(db, principal, "vessel_call.created", "vessel_call", vessel.id, vessel.terminal_id, {"voyage_number": vessel.voyage_number})
        db.refresh(vessel)
        db.commit()
        return vessel
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That voyage number is already scheduled for this terminal") from exc


@app.get("/api/v1/appointments", response_model=list[GateAppointmentOut], tags=["gate"])
def list_appointments(terminal_id: UUID, principal: principal_dep, db: db_dep):
    ensure_terminal(db, principal, terminal_id)
    statement = select(GateAppointment).where(
        GateAppointment.organization_id == principal.organization_id,
        GateAppointment.terminal_id == terminal_id,
    )
    if principal.role == "customer" or principal.membership.customer_id:
        statement = statement.where(GateAppointment.customer_id == principal.membership.customer_id)
    return list(db.scalars(statement.order_by(GateAppointment.planned_at.desc()).limit(100)))


@app.post("/api/v1/appointments", response_model=GateAppointmentOut, status_code=201, tags=["gate"])
def create_appointment(payload: GateAppointmentCreate, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff", "transport_operator")), db: Session = Depends(get_db)):
    ensure_terminal(db, principal, payload.terminal_id)
    customer = db.scalar(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.organization_id == principal.organization_id,
            Customer.terminal_id == payload.terminal_id,
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found for this terminal")
    appointment = GateAppointment(
        organization_id=principal.organization_id,
        terminal_id=payload.terminal_id,
        customer_id=customer.id,
        reference=f"GA-{datetime.now(UTC):%y%m%d}-{secrets.token_hex(3).upper()}",
        vehicle_number=payload.vehicle_number.upper(),
        planned_at=to_utc(payload.planned_at),
        notes=payload.notes,
    )
    db.add(appointment)
    db.flush()
    audit(db, principal, "gate.appointment_created", "gate_appointment", appointment.id, appointment.terminal_id)
    db.refresh(appointment)
    db.commit()
    return appointment


@app.get("/api/v1/tariffs", response_model=list[TariffOut], tags=["billing"])
def list_tariffs(terminal_id: UUID, principal: principal_dep, db: db_dep):
    ensure_terminal(db, principal, terminal_id)
    rows = db.execute(
        select(Tariff, TariffVersion).join(TariffVersion, TariffVersion.tariff_id == Tariff.id).where(
            Tariff.organization_id == principal.organization_id,
            Tariff.terminal_id == terminal_id,
        ).order_by(TariffVersion.created_at.desc())
    ).all()
    return [
        TariffOut(
            id=version.id,
            tariff_id=tariff.id,
            version_number=version.version_number,
            name=tariff.name,
            free_storage_days=version.free_storage_days,
            daily_rate=version.daily_rate,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            published_at=version.published_at,
        )
        for tariff, version in rows
    ]


@app.post("/api/v1/tariffs", response_model=TariffOut, status_code=201, tags=["billing"])
def create_tariff(payload: TariffCreate, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager")), db: Session = Depends(get_db)):
    ensure_terminal(db, principal, payload.terminal_id)
    tariff = Tariff(organization_id=principal.organization_id, terminal_id=payload.terminal_id, name=payload.name)
    db.add(tariff)
    db.flush()
    version = TariffVersion(
        organization_id=principal.organization_id,
        terminal_id=payload.terminal_id,
        tariff_id=tariff.id,
        version_number=1,
        free_storage_days=payload.free_storage_days,
        daily_rate=payload.daily_rate,
        effective_from=to_utc(payload.effective_from),
    )
    db.add(version)
    db.flush()
    audit(db, principal, "tariff.draft_created", "tariff_version", version.id, payload.terminal_id)
    db.refresh(version)
    db.commit()
    return TariffOut(
        id=version.id,
        tariff_id=tariff.id,
        version_number=version.version_number,
        name=tariff.name,
        free_storage_days=version.free_storage_days,
        daily_rate=version.daily_rate,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        published_at=version.published_at,
    )


@app.post("/api/v1/tariffs/versions/{version_id}/publish", response_model=TariffOut, tags=["billing"])
def publish_tariff(version_id: UUID, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager")), db: Session = Depends(get_db)):
    version = db.scalar(
        select(TariffVersion).where(
            TariffVersion.id == version_id,
            TariffVersion.organization_id == principal.organization_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Tariff version not found")
    if version.published_at is not None:
        raise HTTPException(status_code=409, detail="Published tariff versions are immutable")
    version.published_at = utc_now()
    tariff = db.get(Tariff, version.tariff_id)
    audit(db, principal, "tariff.published", "tariff_version", version.id, version.terminal_id)
    db.flush()
    db.refresh(version)
    db.commit()
    return TariffOut(
        id=version.id,
        tariff_id=tariff.id,
        version_number=version.version_number,
        name=tariff.name,
        free_storage_days=version.free_storage_days,
        daily_rate=version.daily_rate,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        published_at=version.published_at,
    )


@app.get("/api/v1/invoices", response_model=list[InvoiceOut], tags=["billing"])
def list_invoices(principal: principal_dep, db: db_dep, terminal_id: UUID | None = None):
    statement = select(OperationalInvoice).where(OperationalInvoice.organization_id == principal.organization_id)
    if terminal_id:
        ensure_terminal(db, principal, terminal_id)
        statement = statement.where(OperationalInvoice.terminal_id == terminal_id)
    elif principal.membership.terminal_id:
        statement = statement.where(OperationalInvoice.terminal_id == principal.membership.terminal_id)
    if principal.role == "customer" or principal.membership.customer_id:
        statement = statement.where(OperationalInvoice.customer_id == principal.membership.customer_id)
    rows = list(db.scalars(statement.order_by(OperationalInvoice.issued_at.desc()).limit(200)))
    return _invoices_with_visits(db, rows)


def _invoices_with_visits(db: Session, invoices: list[OperationalInvoice]) -> list[dict]:
    if not invoices:
        return []
    line_rows = db.execute(
        select(OperationalInvoiceLine.invoice_id, OperationalInvoiceLine.visit_id).where(
            OperationalInvoiceLine.invoice_id.in_([invoice.id for invoice in invoices])
        )
    )
    visit_ids: dict[UUID, list[UUID]] = {}
    for invoice_id, visit_id in line_rows:
        visit_ids.setdefault(invoice_id, []).append(visit_id)
    result = []
    for invoice in invoices:
        data = InvoiceOut.model_validate(invoice).model_dump()
        data["visit_ids"] = visit_ids.get(invoice.id, [])
        result.append(data)
    return result


@app.get("/api/v1/invoices/{invoice_id}", response_model=InvoiceDetailOut, tags=["billing"])
def get_invoice(invoice_id: UUID, principal: principal_dep, db: db_dep):
    invoice = db.scalar(
        select(OperationalInvoice).where(
            OperationalInvoice.id == invoice_id,
            OperationalInvoice.organization_id == principal.organization_id,
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Operational invoice not found")
    ensure_terminal(db, principal, invoice.terminal_id)
    _authorized_customer(principal, invoice.customer_id)
    lines = list(db.scalars(select(OperationalInvoiceLine).where(OperationalInvoiceLine.invoice_id == invoice.id)))
    data = InvoiceOut.model_validate(invoice).model_dump()
    data["lines"] = [InvoiceLineOut.model_validate(line) for line in lines]
    return InvoiceDetailOut.model_validate(data)


@app.post("/api/v1/invoices/generate/{visit_id}", tags=["billing"])
def generate_invoice_for_visit(visit_id: UUID, principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    visit = _load_visit(db, principal, visit_id)
    if visit.status != "released":
        raise HTTPException(status_code=409, detail="Operational storage invoice is created after custody release")
    container = db.get(Container, visit.container_id)
    customer = db.get(Customer, container.customer_id)
    terminal = ensure_terminal(db, principal, visit.terminal_id)
    invoice, created = generate_storage_invoice(db, principal, visit, container, customer, terminal)
    if invoice is None:
        raise HTTPException(status_code=409, detail="No published tariff applied at custody receipt")
    db.flush()
    db.refresh(invoice)
    db.commit()
    return {"invoice": InvoiceOut.model_validate(invoice), "created": created}


@app.get("/api/v1/portal/containers", tags=["customer portal"])
def portal_containers(principal: Principal = Depends(require_roles("customer", "transport_operator", "organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    if not principal.membership.customer_id:
        raise HTTPException(status_code=403, detail="A customer assignment is required for the customer portal")
    rows = db.execute(
        select(Container, ContainerVisit, YardSlot)
        .join(ContainerVisit, ContainerVisit.container_id == Container.id)
        .outerjoin(YardSlot, YardSlot.id == ContainerVisit.yard_slot_id)
        .where(
            Container.organization_id == principal.organization_id,
            Container.customer_id == principal.membership.customer_id,
        )
        .order_by(ContainerVisit.created_at.desc())
    ).all()
    return [
        {
            "container_number": container.container_number,
            "category": container.category,
            "is_empty": container.is_empty,
            "visit_reference": visit.visit_reference,
            "direction": visit.direction,
            "status": visit.status,
            "received_at": visit.custody_received_at,
            "released_at": visit.custody_released_at,
            "yard_slot": slot.code if slot else None,
            "release_mode": visit.release_mode,
        }
        for container, visit, slot in rows
    ]


@app.get("/api/v1/portal/invoices", response_model=list[InvoiceOut], tags=["customer portal"])
def portal_invoices(principal: Principal = Depends(require_roles("customer", "transport_operator", "organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db)):
    if not principal.membership.customer_id:
        raise HTTPException(status_code=403, detail="A customer assignment is required for the customer portal")
    rows = list(
        db.scalars(
            select(OperationalInvoice).where(
                OperationalInvoice.organization_id == principal.organization_id,
                OperationalInvoice.customer_id == principal.membership.customer_id,
            ).order_by(OperationalInvoice.issued_at.desc())
        )
    )
    return _invoices_with_visits(db, rows)


@app.get("/api/v1/dashboard/summary", tags=["analytics"])
def dashboard_summary(terminal_id: UUID, principal: principal_dep, db: db_dep):
    ensure_terminal(db, principal, terminal_id)
    if principal.membership.customer_id and principal.role == "customer":
        container_count = db.scalar(select(func.count(Container.id)).where(Container.organization_id == principal.organization_id, Container.terminal_id == terminal_id, Container.customer_id == principal.membership.customer_id)) or 0
        visit_count = db.scalar(select(func.count(ContainerVisit.id)).join(Container, Container.id == ContainerVisit.container_id).where(ContainerVisit.organization_id == principal.organization_id, ContainerVisit.terminal_id == terminal_id, Container.customer_id == principal.membership.customer_id)) or 0
        return {"scope": "customer", "containers": container_count, "visits": visit_count}
    terminal = ensure_terminal(db, principal, terminal_id)
    local_today_start = datetime.now(ZoneInfo(terminal.timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
    local_tomorrow_start = local_today_start + timedelta(days=1)
    counts = {
        "containers": db.scalar(select(func.count(Container.id)).where(Container.organization_id == principal.organization_id, Container.terminal_id == terminal_id)) or 0,
        "in_terminal": db.scalar(select(func.count(ContainerVisit.id)).where(ContainerVisit.organization_id == principal.organization_id, ContainerVisit.terminal_id == terminal_id, ContainerVisit.status == "in_terminal")) or 0,
        "expected": db.scalar(select(func.count(ContainerVisit.id)).where(ContainerVisit.organization_id == principal.organization_id, ContainerVisit.terminal_id == terminal_id, ContainerVisit.status == "expected")) or 0,
        "released_today": db.scalar(select(func.count(ContainerVisit.id)).where(
            ContainerVisit.organization_id == principal.organization_id,
            ContainerVisit.terminal_id == terminal_id,
            ContainerVisit.status == "released",
            ContainerVisit.custody_released_at >= local_today_start.astimezone(UTC),
            ContainerVisit.custody_released_at < local_tomorrow_start.astimezone(UTC),
        )) or 0,
        "available_slots": db.scalar(select(func.count(YardSlot.id)).where(
            YardSlot.organization_id == principal.organization_id,
            YardSlot.terminal_id == terminal_id,
            YardSlot.blocked.is_(False),
            ~YardSlot.id.in_(select(ContainerVisit.yard_slot_id).where(
                ContainerVisit.organization_id == principal.organization_id,
                ContainerVisit.terminal_id == terminal_id,
                ContainerVisit.status == "in_terminal",
                ContainerVisit.yard_slot_id.is_not(None),
            )),
        )) or 0,
        "open_invoices": db.scalar(select(func.count(OperationalInvoice.id)).where(OperationalInvoice.organization_id == principal.organization_id, OperationalInvoice.terminal_id == terminal_id, OperationalInvoice.status == "issued")) or 0,
    }
    return {"scope": "terminal", "demo_data": bool(db.scalar(select(Organization.is_demo).where(Organization.id == principal.organization_id))), **counts}


@app.get("/api/v1/activity", tags=["audit"])
def recent_activity(principal: Principal = Depends(require_roles("organization_admin", "terminal_manager", "port_staff")), db: Session = Depends(get_db), terminal_id: UUID | None = None):
    statement = select(AuditLog).where(AuditLog.organization_id == principal.organization_id)
    if terminal_id:
        ensure_terminal(db, principal, terminal_id)
        statement = statement.where(AuditLog.terminal_id == terminal_id)
    elif principal.membership.terminal_id:
        statement = statement.where(AuditLog.terminal_id == principal.membership.terminal_id)
    rows = list(db.scalars(statement.order_by(AuditLog.created_at.desc()).limit(30)))
    return [
        {"id": str(row.id), "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "details": row.details, "created_at": row.created_at}
        for row in rows
    ]


@app.get("/api/v1/subscription/usage", tags=["SaaS subscription"])
def subscription_usage(principal: principal_dep, db: db_dep):
    count = db.scalar(select(func.coalesce(func.sum(SaasUsageEvent.quantity), 0)).where(SaasUsageEvent.organization_id == principal.organization_id)) or 0
    return {
        "organization_id": str(principal.organization_id),
        "period": "all recorded visits",
        "billable_visit_count": int(count),
        "rule": "One idempotent event per container visit, including empty containers and transshipment.",
        "billing_status": "usage tracking only; no PortFlow subscription invoice or payment processing is configured",
    }


_frontend_dir = Path(__file__).resolve().parents[1] / "static"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

