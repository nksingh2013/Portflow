import secrets
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import (
    AuditLog,
    Container,
    ContainerVisit,
    Customer,
    OperationalInvoice,
    OperationalInvoiceLine,
    SaasUsageEvent,
    Tariff,
    TariffVersion,
    Terminal,
    YardSlot,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_terminal(session: Session, principal: Principal, terminal_id) -> Terminal:
    terminal = session.scalar(
        select(Terminal).where(
            Terminal.id == terminal_id,
            Terminal.organization_id == principal.organization_id,
            Terminal.is_active.is_(True),
        )
    )
    if terminal is None:
        raise HTTPException(status_code=404, detail="Terminal not found")
    if principal.membership.terminal_id and principal.membership.terminal_id != terminal.id:
        raise HTTPException(status_code=403, detail="This account is limited to another terminal")
    return terminal


def ensure_customer_scope(principal: Principal, customer_id) -> None:
    if principal.role == "customer" and principal.membership.customer_id != customer_id:
        raise HTTPException(status_code=403, detail="This customer account cannot access that record")


def audit(
    session: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: object,
    terminal_id=None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            organization_id=principal.organization_id,
            terminal_id=terminal_id,
            actor_id=principal.user.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details or {},
        )
    )


def record_visit_usage(session: Session, visit: ContainerVisit, container: Container) -> SaasUsageEvent:
    existing = session.scalar(select(SaasUsageEvent).where(SaasUsageEvent.visit_id == visit.id))
    if existing:
        return existing
    event = SaasUsageEvent(
        organization_id=visit.organization_id,
        terminal_id=visit.terminal_id,
        visit_id=visit.id,
        event_type="container_visit",
        idempotency_key=f"visit:{visit.id}",
        quantity=1,
        metadata_json={
            "empty": container.is_empty,
            "transshipment": visit.is_transshipment,
            "direction": visit.direction,
        },
    )
    session.add(event)
    return event


def _local_date(value: datetime, timezone_name: str):
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Terminal timezone is not recognized") from exc
    return to_utc(value).astimezone(timezone).date()


def storage_days(received_at: datetime, released_at: datetime, timezone_name: str) -> int:
    """Count calendar dates touched, including both custody event dates."""
    start = _local_date(received_at, timezone_name)
    end = _local_date(released_at, timezone_name)
    if end < start:
        raise HTTPException(status_code=422, detail="Release time cannot precede custody receipt")
    return (end - start).days + 1


def generate_storage_invoice(
    session: Session,
    principal: Principal,
    visit: ContainerVisit,
    container: Container,
    customer: Customer,
    terminal: Terminal,
) -> tuple[OperationalInvoice | None, bool]:
    """Create one immutable operational invoice snapshot from a published tariff."""
    existing = session.scalar(
        select(OperationalInvoice)
        .join(OperationalInvoiceLine, OperationalInvoiceLine.invoice_id == OperationalInvoice.id)
        .where(OperationalInvoiceLine.visit_id == visit.id)
    )
    if existing:
        return existing, False
    if not visit.custody_received_at or not visit.custody_released_at:
        return None, False

    received_at = to_utc(visit.custody_received_at)
    released_at = to_utc(visit.custody_released_at)
    tariff_version = session.scalar(
        select(TariffVersion)
        .join(Tariff, Tariff.id == TariffVersion.tariff_id)
        .where(
            TariffVersion.organization_id == principal.organization_id,
            TariffVersion.terminal_id == terminal.id,
            Tariff.is_active.is_(True),
            TariffVersion.published_at.is_not(None),
            TariffVersion.effective_from <= received_at,
            (TariffVersion.effective_to.is_(None) | (TariffVersion.effective_to >= received_at)),
        )
        .order_by(TariffVersion.effective_from.desc(), TariffVersion.version_number.desc())
    )
    if tariff_version is None:
        return None, False

    total_days = storage_days(received_at, released_at, terminal.timezone)
    billable_days = max(0, total_days - tariff_version.free_storage_days)
    rate = Decimal(tariff_version.daily_rate).quantize(Decimal("0.01"))
    amount = (rate * billable_days).quantize(Decimal("0.01"))
    invoice = OperationalInvoice(
        organization_id=principal.organization_id,
        terminal_id=terminal.id,
        customer_id=customer.id,
        invoice_number=f"OP-{utc_now():%Y%m%d}-{secrets.token_hex(3).upper()}",
        currency="INR",
        status="issued",
        subtotal=amount,
        tax_total=Decimal("0.00"),
        total=amount,
        snapshot={
            "charge_type": "storage",
            "visit_reference": visit.visit_reference,
            "container_number": container.container_number,
            "tariff_id": str(tariff_version.tariff_id),
            "tariff_version_id": str(tariff_version.id),
            "tariff_version_number": tariff_version.version_number,
            "timezone": terminal.timezone,
            "custody_received_at": received_at.isoformat(),
            "custody_released_at": released_at.isoformat(),
            "calendar_days": total_days,
            "free_storage_days": tariff_version.free_storage_days,
            "billable_days": billable_days,
            "daily_rate_inr": str(rate),
            "amount_inr": str(amount),
            "tax_configuration": "not configured",
        },
    )
    session.add(invoice)
    session.flush()
    line = OperationalInvoiceLine(
        organization_id=principal.organization_id,
        terminal_id=terminal.id,
        invoice_id=invoice.id,
        visit_id=visit.id,
        charge_type="storage",
        description=f"Storage · {billable_days} billable calendar day(s) · tariff v{tariff_version.version_number}",
        quantity=Decimal(billable_days),
        unit_rate=rate,
        amount=amount,
    )
    session.add(line)
    audit(
        session,
        principal,
        "invoice.issued",
        "operational_invoice",
        invoice.id,
        terminal.id,
        {"visit_id": str(visit.id), "tariff_version_id": str(tariff_version.id), "amount_inr": str(amount)},
    )
    return invoice, True


def yard_suggestions(
    session: Session,
    organization_id,
    terminal_id,
    category: str,
    exclude_visit_id=None,
    limit: int = 3,
) -> list[tuple[YardSlot, int, str]]:
    slots = list(
        session.scalars(
            select(YardSlot)
            .where(
                YardSlot.organization_id == organization_id,
                YardSlot.terminal_id == terminal_id,
                YardSlot.blocked.is_(False),
            )
            .order_by(YardSlot.block, YardSlot.bay, YardSlot.row, YardSlot.tier)
        )
    )
    occupied = set(
        session.scalars(
            select(ContainerVisit.yard_slot_id).where(
                ContainerVisit.organization_id == organization_id,
                ContainerVisit.terminal_id == terminal_id,
                ContainerVisit.status == "in_terminal",
                ContainerVisit.yard_slot_id.is_not(None),
                ContainerVisit.id != exclude_visit_id if exclude_visit_id else True,
            )
        )
    )
    candidates: list[tuple[YardSlot, int, str]] = []
    for slot in slots:
        if slot.id in occupied:
            continue
        if slot.container_category not in (category, "GENERAL"):
            continue
        exact = slot.container_category == category
        score = 100 if exact else 65
        reason = "Exact container category fit; slot is clear." if exact else "General capacity; slot is clear."
        candidates.append((slot, score, reason))
    candidates.sort(key=lambda item: (-item[1], item[0].block, item[0].bay, item[0].row, item[0].tier))
    return candidates[:limit]
