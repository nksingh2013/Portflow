"""Create clearly labeled demo records. Run explicitly; never in production startup."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pyotp
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, set_identity_context, set_tenant_context
from app.models import (
    Container,
    ContainerVisit,
    Customer,
    CustodyEvent,
    Membership,
    MovementEvent,
    Organization,
    SaasUsageEvent,
    Tariff,
    TariffVersion,
    Terminal,
    User,
    VesselCall,
    YardSlot,
)
from app.security import hash_password
from app.services import generate_storage_invoice
from app.auth import Principal


def seed_demo() -> None:
    if not settings.demo_mode:
        raise SystemExit("Demo seeding is disabled. Set PORTFLOW_DEMO_MODE=true only in a local or test environment.")
    admin_password = settings.demo_admin_password.get_secret_value() if settings.demo_admin_password else ""
    customer_password = settings.demo_customer_password.get_secret_value() if settings.demo_customer_password else ""
    mfa_secret = settings.demo_admin_mfa_secret.get_secret_value() if settings.demo_admin_mfa_secret else ""
    if not admin_password or not customer_password or not mfa_secret:
        raise SystemExit("Run scripts/bootstrap-env.ps1 first; it creates local-only demo credentials in .env.")

    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.email == settings.demo_admin_email.lower()))
        if admin:
            set_identity_context(db, admin.id)
            membership = db.scalar(select(Membership).where(Membership.user_id == admin.id))
            if membership:
                set_tenant_context(db, membership.organization_id)
                organization = db.get(Organization, membership.organization_id)
                print(f"Demo data already exists for {organization.name if organization else 'PortFlow Demo'}; no changes made.")
                print(f"Administrator login: {settings.demo_admin_email} · organization slug: portflow-demo")
                print("Demo passwords and MFA secret are stored only in the local .env file.")
                return

        organization_id = uuid4()
        terminal_id = uuid4()
        admin_id = uuid4()
        customer_user_id = uuid4()
        customer_id = uuid4()
        set_identity_context(db, admin_id)
        set_tenant_context(db, organization_id)

        organization = Organization(
            id=organization_id,
            slug="portflow-demo",
            name="PortFlow Demo Terminal Co.",
            legal_name="PortFlow Demo Terminal Co.",
            timezone="Asia/Kolkata",
            currency="INR",
            is_demo=True,
        )
        terminal = Terminal(
            id=terminal_id,
            organization_id=organization_id,
            code="MUM-01",
            name="Mumbai Gateway Terminal",
            timezone="Asia/Kolkata",
            address="Demo location · Mumbai, India",
        )
        customer = Customer(
            id=customer_id,
            organization_id=organization_id,
            terminal_id=terminal_id,
            code="WSL-001",
            name="Western Star Logistics",
            email=settings.demo_customer_email,
        )
        admin = User(
            id=admin_id,
            email=settings.demo_admin_email.lower(),
            display_name="PortFlow Demo Admin",
            password_hash=hash_password(admin_password),
            mfa_secret=mfa_secret,
            mfa_enabled=True,
        )
        admin_membership = Membership(
            id=uuid4(),
            user_id=admin_id,
            organization_id=organization_id,
            organization_slug=organization.slug,
            role="organization_admin",
        )
        # Flush organization + terminal first so the composite FK on customers
        # (terminal_id, organization_id) → terminals(id, organization_id) is
        # satisfied before the customer row is inserted.  Without declared ORM
        # relationships SQLAlchemy cannot infer this ordering automatically.
        db.add_all([organization, terminal])
        db.flush()

        # Insert each referenced row before rows that point to it.  The
        # customer row depends on the terminal; memberships depend on users.
        db.add(customer)
        db.flush()

        db.add(admin)
        db.flush()

        db.add(admin_membership)
        db.flush()

        vessel = VesselCall(
            organization_id=organization_id,
            terminal_id=terminal_id,
            vessel_name="MV Sagar Horizon",
            imo_number="",
            voyage_number="SH-042",
            berth="B-04",
            eta=datetime.now(UTC) + timedelta(days=1, hours=4),
            etd=datetime.now(UTC) + timedelta(days=2),
            status="scheduled",
        )
        tariff = Tariff(organization_id=organization_id, terminal_id=terminal_id, name="Standard import storage")
        db.add_all([vessel, tariff])
        db.flush()
        tariff_version = TariffVersion(
            organization_id=organization_id,
            terminal_id=terminal_id,
            tariff_id=tariff.id,
            version_number=1,
            free_storage_days=1,
            daily_rate=Decimal("850.00"),
            effective_from=datetime.now(UTC) - timedelta(days=120),
            published_at=datetime.now(UTC) - timedelta(days=120),
        )
        db.add(tariff_version)

        slots = []
        for block, bay in (("A", 1), ("A", 2), ("A", 3), ("B", 1), ("B", 2), ("R", 1)):
            slots.append(
                YardSlot(
                    organization_id=organization_id,
                    terminal_id=terminal_id,
                    code=f"{block}-{bay:02d}-01-01",
                    zone="REEFER" if block == "R" else "GENERAL",
                    block=block,
                    bay=bay,
                    row=1,
                    tier=1,
                    container_category="REEFER" if block == "R" else "GENERAL",
                )
            )
        db.add_all(slots)

        container_one = Container(
            organization_id=organization_id,
            terminal_id=terminal_id,
            customer_id=customer_id,
            container_number="HLCU1234567",
            size_feet=40,
            category="DRY",
            is_empty=False,
            seal_number="SL-448203",
            cargo_description="Packaged machinery · demo record",
        )
        container_two = Container(
            organization_id=organization_id,
            terminal_id=terminal_id,
            customer_id=customer_id,
            container_number="FCIU7654321",
            size_feet=20,
            category="DRY",
            is_empty=True,
            cargo_description="",
        )
        db.add_all([container_one, container_two])
        db.flush()

        active_visit = ContainerVisit(
            organization_id=organization_id,
            terminal_id=terminal_id,
            container_id=container_one.id,
            vessel_call_id=vessel.id,
            yard_slot_id=slots[0].id,
            visit_reference="PF-DEMO-0001",
            direction="import",
            status="in_terminal",
            entry_mode="vessel",
            custody_received_at=datetime.now(UTC) - timedelta(days=2),
            idempotency_key="seed:visit:demo-active",
            created_by_id=admin_id,
        )
        released_visit = ContainerVisit(
            organization_id=organization_id,
            terminal_id=terminal_id,
            container_id=container_two.id,
            vessel_call_id=vessel.id,
            visit_reference="PF-DEMO-0002",
            direction="export",
            is_transshipment=True,
            status="released",
            entry_mode="rail",
            release_mode="vessel_loading",
            custody_received_at=datetime.now(UTC) - timedelta(days=5),
            custody_released_at=datetime.now(UTC) - timedelta(days=2),
            idempotency_key="seed:visit:demo-released",
            created_by_id=admin_id,
        )
        db.add_all([active_visit, released_visit])
        db.flush()

        db.add_all([
            CustodyEvent(
                organization_id=organization_id,
                terminal_id=terminal_id,
                visit_id=active_visit.id,
                event_type="received",
                mode="vessel",
                event_at=active_visit.custody_received_at,
                idempotency_key="seed:custody:active:received",
                actor_id=admin_id,
            ),
            CustodyEvent(
                organization_id=organization_id,
                terminal_id=terminal_id,
                visit_id=released_visit.id,
                event_type="received",
                mode="rail",
                event_at=released_visit.custody_received_at,
                idempotency_key="seed:custody:released:received",
                actor_id=admin_id,
            ),
            CustodyEvent(
                organization_id=organization_id,
                terminal_id=terminal_id,
                visit_id=released_visit.id,
                event_type="released",
                mode="vessel_loading",
                event_at=released_visit.custody_released_at,
                idempotency_key="seed:custody:released:released",
                actor_id=admin_id,
            ),
            MovementEvent(
                organization_id=organization_id,
                terminal_id=terminal_id,
                visit_id=active_visit.id,
                to_slot_id=slots[0].id,
                movement_type="yard_in",
                notes="Seeded demo allocation",
                actor_id=admin_id,
            ),
        ])
        for visit, container_item in ((active_visit, container_one), (released_visit, container_two)):
            db.add(SaasUsageEvent(
                organization_id=organization_id,
                terminal_id=terminal_id,
                visit_id=visit.id,
                event_type="container_visit",
                idempotency_key=f"visit:{visit.id}",
                quantity=1,
                metadata_json={"empty": container_item.is_empty, "transshipment": visit.is_transshipment},
            ))

        set_identity_context(db, customer_user_id)
        customer_user = User(
            id=customer_user_id,
            email=settings.demo_customer_email.lower(),
            display_name="Western Star Customer",
            password_hash=hash_password(customer_password),
        )
        customer_membership = Membership(
            id=uuid4(),
            user_id=customer_user_id,
            organization_id=organization_id,
            organization_slug=organization.slug,
            terminal_id=terminal_id,
            customer_id=customer_id,
            role="customer",
        )
        # The customer membership has a foreign key to customer_user.
        db.add(customer_user)
        db.flush()

        db.add(customer_membership)
        db.flush()
        principal = Principal(user=admin, membership=admin_membership)
        generate_storage_invoice(db, principal, released_visit, container_two, customer, terminal)
        db.commit()

        print("PortFlow demo data created.")
        print(f"Organization: {organization.slug}")
        print(f"Admin login: {settings.demo_admin_email}")
        print(f"Customer portal login: {settings.demo_customer_email}")
        print("Passwords and the admin MFA secret are stored in local .env; values were not echoed.")
        print("Records are demo samples only. Do not use this seed outside local/test environments.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
