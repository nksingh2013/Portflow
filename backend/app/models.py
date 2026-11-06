from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    legal_name: Mapped[str] = mapped_column(String(240), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Terminal(Base):
    __tablename__ = "terminals"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_terminal_org_code"),
        UniqueConstraint("id", "organization_id", name="uq_terminal_id_org"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(180))
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")
    address: Mapped[str] = mapped_column(String(300), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(180))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_customer_org_code"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_customer_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_customer_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(180))
    email: Mapped[str] = mapped_column(String(320), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class CustomerPortalRequest(Base):
    __tablename__ = "customer_portal_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id", "terminal_id"],
            ["customers.id", "customers.organization_id", "customers.terminal_id"],
            name="fk_portal_request_customer_tenant",
        ),
        CheckConstraint("status in ('pending','approved','rejected')", name="ck_portal_request_status"),
        Index(
            "uq_pending_portal_request_org_email",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index("ix_portal_request_org_status_created", "organization_id", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    company_name: Mapped[str] = mapped_column(String(180))
    contact_name: Mapped[str] = mapped_column(String(180))
    email: Mapped[str] = mapped_column(String(320))
    message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    terminal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class Membership(Base):
    """Identity mapping queried only after a signed token identifies its user."""
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_membership_terminal_tenant"),
        ForeignKeyConstraint(["customer_id", "organization_id", "terminal_id"], ["customers.id", "customers.organization_id", "customers.terminal_id"], name="fk_membership_customer_tenant"),
        CheckConstraint(
            "role in ('platform_super_admin','organization_admin','terminal_manager','port_staff','transport_operator','customer')",
            name="ck_membership_role",
        ),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    organization_slug: Mapped[str] = mapped_column(String(80))
    terminal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class YardSlot(Base):
    __tablename__ = "yard_slots"
    __table_args__ = (
        UniqueConstraint("organization_id", "terminal_id", "code", name="uq_yard_slot_code"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_yard_slot_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_yard_slot_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(40))
    zone: Mapped[str] = mapped_column(String(30), default="GENERAL")
    block: Mapped[str] = mapped_column(String(20))
    bay: Mapped[int] = mapped_column(Integer)
    row: Mapped[int] = mapped_column(Integer)
    tier: Mapped[int] = mapped_column(Integer)
    container_category: Mapped[str] = mapped_column(String(24), default="DRY")
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class VesselCall(Base):
    __tablename__ = "vessel_calls"
    __table_args__ = (
        UniqueConstraint("organization_id", "terminal_id", "voyage_number", name="uq_vessel_voyage"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_vessel_call_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_vessel_call_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    vessel_name: Mapped[str] = mapped_column(String(180))
    imo_number: Mapped[str] = mapped_column(String(12), default="")
    voyage_number: Mapped[str] = mapped_column(String(40))
    berth: Mapped[str] = mapped_column(String(40), default="")
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    etd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    created_at: Mapped[datetime] = created_at_column()


class Container(Base):
    __tablename__ = "containers"
    __table_args__ = (
        UniqueConstraint("organization_id", "container_number", name="uq_container_org_number"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_container_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_container_terminal_tenant"),
        ForeignKeyConstraint(["customer_id", "organization_id", "terminal_id"], ["customers.id", "customers.organization_id", "customers.terminal_id"], name="fk_container_customer_tenant"),
        CheckConstraint("size_feet in (20, 40, 45)", name="ck_container_size"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    container_number: Mapped[str] = mapped_column(String(16), index=True)
    size_feet: Mapped[int] = mapped_column(Integer, default=40)
    category: Mapped[str] = mapped_column(String(24), default="DRY")
    is_empty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seal_number: Mapped[str] = mapped_column(String(40), default="")
    cargo_description: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = created_at_column()


class ContainerVisit(Base):
    __tablename__ = "container_visits"
    __table_args__ = (
        UniqueConstraint("organization_id", "visit_reference", name="uq_visit_reference"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_visit_idempotency"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_visit_id_org_terminal"),
        Index(
            "uq_active_visit_yard_slot",
            "organization_id",
            "terminal_id",
            "yard_slot_id",
            unique=True,
            postgresql_where=text("status = 'in_terminal' AND yard_slot_id IS NOT NULL"),
            sqlite_where=text("status = 'in_terminal' AND yard_slot_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_visit_terminal_tenant"),
        ForeignKeyConstraint(["container_id", "organization_id", "terminal_id"], ["containers.id", "containers.organization_id", "containers.terminal_id"], ondelete="CASCADE", name="fk_visit_container_tenant"),
        ForeignKeyConstraint(["vessel_call_id", "organization_id", "terminal_id"], ["vessel_calls.id", "vessel_calls.organization_id", "vessel_calls.terminal_id"], name="fk_visit_vessel_tenant"),
        ForeignKeyConstraint(["yard_slot_id", "organization_id", "terminal_id"], ["yard_slots.id", "yard_slots.organization_id", "yard_slots.terminal_id"], name="fk_visit_yard_slot_tenant"),
        ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_visit_created_by"),
        Index("ix_visits_org_terminal_status", "organization_id", "terminal_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    container_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    vessel_call_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    yard_slot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    visit_reference: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(12), default="import")
    is_transshipment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="expected")
    entry_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    release_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    custody_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    custody_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()


class CustodyEvent(Base):
    __tablename__ = "custody_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_custody_idempotency"),
        UniqueConstraint("visit_id", "event_type", name="uq_custody_visit_event_type"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_custody_terminal_tenant"),
        ForeignKeyConstraint(["visit_id", "organization_id", "terminal_id"], ["container_visits.id", "container_visits.organization_id", "container_visits.terminal_id"], ondelete="CASCADE", name="fk_custody_visit_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(20))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    external_reference: Mapped[str] = mapped_column(String(100), default="")
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created_at_column()


class MovementEvent(Base):
    __tablename__ = "movement_events"
    __table_args__ = (
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_movement_terminal_tenant"),
        ForeignKeyConstraint(["visit_id", "organization_id", "terminal_id"], ["container_visits.id", "container_visits.organization_id", "container_visits.terminal_id"], ondelete="CASCADE", name="fk_movement_visit_tenant"),
        ForeignKeyConstraint(["from_slot_id", "organization_id", "terminal_id"], ["yard_slots.id", "yard_slots.organization_id", "yard_slots.terminal_id"], name="fk_movement_from_slot_tenant"),
        ForeignKeyConstraint(["to_slot_id", "organization_id", "terminal_id"], ["yard_slots.id", "yard_slots.organization_id", "yard_slots.terminal_id"], name="fk_movement_to_slot_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    from_slot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    to_slot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(24))
    notes: Mapped[str] = mapped_column(String(300), default="")
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GateAppointment(Base):
    __tablename__ = "gate_appointments"
    __table_args__ = (
        UniqueConstraint("organization_id", "reference", name="uq_gate_appointment_ref"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_appointment_terminal_tenant"),
        ForeignKeyConstraint(["customer_id", "organization_id", "terminal_id"], ["customers.id", "customers.organization_id", "customers.terminal_id"], name="fk_appointment_customer_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    reference: Mapped[str] = mapped_column(String(32))
    vehicle_number: Mapped[str] = mapped_column(String(24))
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = created_at_column()


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_tariff_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_tariff_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class TariffVersion(Base):
    __tablename__ = "tariff_versions"
    __table_args__ = (
        UniqueConstraint("tariff_id", "version_number", name="uq_tariff_version"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_tariff_version_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_tariff_version_terminal_tenant"),
        ForeignKeyConstraint(["tariff_id", "organization_id", "terminal_id"], ["tariffs.id", "tariffs.organization_id", "tariffs.terminal_id"], ondelete="CASCADE", name="fk_tariff_version_tariff_tenant"),
        CheckConstraint("daily_rate >= 0", name="ck_tariff_daily_rate_nonnegative"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    tariff_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    free_storage_days: Mapped[int] = mapped_column(Integer, default=0)
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class OperationalInvoice(Base):
    __tablename__ = "operational_invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_operational_invoice_number"),
        UniqueConstraint("id", "organization_id", "terminal_id", name="uq_operational_invoice_id_org_terminal"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_operational_invoice_terminal_tenant"),
        ForeignKeyConstraint(["customer_id", "organization_id", "terminal_id"], ["customers.id", "customers.organization_id", "customers.terminal_id"], name="fk_operational_invoice_customer_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    invoice_number: Mapped[str] = mapped_column(String(36))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="issued")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperationalInvoiceLine(Base):
    __tablename__ = "operational_invoice_lines"
    __table_args__ = (
        UniqueConstraint("visit_id", name="uq_invoice_line_visit"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_invoice_line_terminal_tenant"),
        ForeignKeyConstraint(["invoice_id", "organization_id", "terminal_id"], ["operational_invoices.id", "operational_invoices.organization_id", "operational_invoices.terminal_id"], ondelete="CASCADE", name="fk_invoice_line_invoice_tenant"),
        ForeignKeyConstraint(["visit_id", "organization_id", "terminal_id"], ["container_visits.id", "container_visits.organization_id", "container_visits.terminal_id"], name="fk_invoice_line_visit_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    charge_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(240))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class SaasUsageEvent(Base):
    __tablename__ = "saas_usage_events"
    __table_args__ = (
        UniqueConstraint("visit_id", name="uq_saas_usage_visit"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_saas_usage_idempotency"),
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_saas_usage_terminal_tenant"),
        ForeignKeyConstraint(["visit_id", "organization_id", "terminal_id"], ["container_visits.id", "container_visits.organization_id", "container_visits.terminal_id"], ondelete="CASCADE", name="fk_saas_usage_visit_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(32), default="container_visit")
    idempotency_key: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created_at_column()


class SaasSubscriptionInvoice(Base):
    """PortFlow's own subscription invoices, separate from terminal operations."""
    __tablename__ = "saas_subscription_invoices"
    __table_args__ = (UniqueConstraint("organization_id", "invoice_number", name="uq_saas_invoice_number"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(36))
    plan_name: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_audit_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created_at_column()


class DocumentRecord(Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_document_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    owner_type: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[str] = mapped_column(String(80))
    storage_key: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(240))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(["terminal_id", "organization_id"], ["terminals.id", "terminals.organization_id"], name="fk_notification_terminal_tenant"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    terminal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    provider_reference: Mapped[str] = mapped_column(String(120), default="")
    payload_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created_at_column()
