from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterInput(BaseModel):
    organization_name: str = Field(min_length=2, max_length=180)
    organization_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$", max_length=80)
    terminal_name: str = Field(min_length=2, max_length=180)
    terminal_code: str = Field(pattern=r"^[A-Za-z0-9-]{2,24}$", max_length=24)
    admin_name: str = Field(min_length=2, max_length=180)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class MFAConfirmInput(BaseModel):
    setup_token: str
    code: str = Field(min_length=6, max_length=8)


class MFAEnableInput(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    organization_name: str
    organization_slug: str
    user_name: str


class PublicMeta(BaseModel):
    demo_mode: bool
    google_login_enabled: bool = False
    currency: str = "INR"


class OrganizationOut(ORMModel):
    id: UUID
    slug: str
    name: str
    legal_name: str
    timezone: str
    currency: str
    is_demo: bool


class TerminalCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9-]{2,24}$", max_length=24)
    name: str = Field(min_length=2, max_length=180)
    timezone: str = "Asia/Kolkata"
    address: str = Field(default="", max_length=300)


class TerminalOut(ORMModel):
    id: UUID
    organization_id: UUID
    code: str
    name: str
    timezone: str
    address: str
    is_active: bool


class CustomerCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=180)
    email: EmailStr | None = None


class CustomerOut(ORMModel):
    id: UUID
    code: str
    name: str
    email: str
    terminal_id: UUID


class ContainerCreate(BaseModel):
    terminal_id: UUID
    customer_id: UUID
    container_number: str = Field(pattern=r"^[A-Za-z]{4}[0-9]{7}$", max_length=11)
    size_feet: Literal[20, 40, 45] = 40
    category: Literal["DRY", "REEFER", "HAZARDOUS", "OPEN_TOP", "FLAT_RACK"] = "DRY"
    is_empty: bool = False
    seal_number: str = Field(default="", max_length=40)
    cargo_description: str = Field(default="", max_length=300)

    @field_validator("container_number")
    @classmethod
    def normalize_container_number(cls, value: str) -> str:
        return value.upper()


class ContainerOut(ORMModel):
    id: UUID
    terminal_id: UUID
    customer_id: UUID
    container_number: str
    size_feet: int
    category: str
    is_empty: bool
    seal_number: str
    cargo_description: str


class VisitCreate(BaseModel):
    terminal_id: UUID
    container_id: UUID
    direction: Literal["import", "export"] = "import"
    vessel_call_id: UUID | None = None
    is_transshipment: bool = False
    idempotency_key: str = Field(min_length=8, max_length=120)


class VisitOut(ORMModel):
    id: UUID
    terminal_id: UUID
    container_id: UUID
    vessel_call_id: UUID | None
    yard_slot_id: UUID | None
    visit_reference: str
    direction: str
    is_transshipment: bool
    status: str
    entry_mode: str | None
    release_mode: str | None
    custody_received_at: datetime | None
    custody_released_at: datetime | None


class WalkInInput(BaseModel):
    terminal_id: UUID
    customer_id: UUID
    container_number: str = Field(pattern=r"^[A-Za-z]{4}[0-9]{7}$", max_length=11)
    size_feet: Literal[20, 40, 45] = 40
    category: Literal["DRY", "REEFER", "HAZARDOUS", "OPEN_TOP", "FLAT_RACK"] = "DRY"
    is_empty: bool = False
    direction: Literal["import", "export"] = "import"
    entry_mode: Literal["truck", "rail", "vessel"] = "truck"
    vessel_call_id: UUID | None = None
    is_transshipment: bool = False
    idempotency_key: str = Field(min_length=8, max_length=120)
    event_at: datetime | None = None

    @field_validator("container_number")
    @classmethod
    def normalize_container_number(cls, value: str) -> str:
        return value.upper()


class CustodyReceiveInput(BaseModel):
    mode: Literal["truck", "rail", "vessel"]
    idempotency_key: str = Field(min_length=8, max_length=120)
    event_at: datetime | None = None
    external_reference: str = Field(default="", max_length=100)


class CustodyReleaseInput(BaseModel):
    mode: Literal["truck_gate_out", "rail_dispatch", "vessel_loading"]
    idempotency_key: str = Field(min_length=8, max_length=120)
    event_at: datetime | None = None
    external_reference: str = Field(default="", max_length=100)


class YardSlotCreate(BaseModel):
    terminal_id: UUID
    code: str = Field(min_length=2, max_length=40)
    zone: str = Field(default="GENERAL", max_length=30)
    block: str = Field(min_length=1, max_length=20)
    bay: int = Field(ge=1, le=999)
    row: int = Field(ge=1, le=99)
    tier: int = Field(ge=1, le=20)
    container_category: str = Field(default="DRY", max_length=24)


class YardSlotOut(ORMModel):
    id: UUID
    terminal_id: UUID
    code: str
    zone: str
    block: str
    bay: int
    row: int
    tier: int
    container_category: str
    blocked: bool


class YardSlotView(YardSlotOut):
    occupied: bool
    current_visit_id: UUID | None = None
    current_container_number: str | None = None


class YardSuggestion(BaseModel):
    slot_id: UUID
    code: str
    score: int
    reason: str


class YardAllocationInput(BaseModel):
    visit_id: UUID
    slot_id: UUID | None = None


class MovementInput(BaseModel):
    movement_type: Literal["yard_in", "yard_rehandle", "inspection", "scale", "handover"]
    to_slot_id: UUID | None = None
    notes: str = Field(default="", max_length=300)


class MovementOut(ORMModel):
    id: UUID
    visit_id: UUID
    from_slot_id: UUID | None
    to_slot_id: UUID | None
    movement_type: str
    notes: str
    moved_at: datetime


class VesselCallCreate(BaseModel):
    terminal_id: UUID
    vessel_name: str = Field(min_length=2, max_length=180)
    imo_number: str = Field(default="", max_length=12)
    voyage_number: str = Field(min_length=2, max_length=40)
    berth: str = Field(default="", max_length=40)
    eta: datetime | None = None
    etd: datetime | None = None


class VesselCallOut(ORMModel):
    id: UUID
    terminal_id: UUID
    vessel_name: str
    imo_number: str
    voyage_number: str
    berth: str
    eta: datetime | None
    etd: datetime | None
    status: str


class TariffCreate(BaseModel):
    terminal_id: UUID
    name: str = Field(min_length=2, max_length=120)
    free_storage_days: int = Field(ge=0, le=365)
    daily_rate: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    effective_from: datetime


class TariffOut(ORMModel):
    id: UUID
    tariff_id: UUID
    version_number: int
    name: str
    free_storage_days: int
    daily_rate: Decimal
    effective_from: datetime
    effective_to: datetime | None
    published_at: datetime | None


class InvoiceLineOut(ORMModel):
    id: UUID
    visit_id: UUID
    charge_type: str
    description: str
    quantity: Decimal
    unit_rate: Decimal
    amount: Decimal


class InvoiceOut(ORMModel):
    id: UUID
    customer_id: UUID
    invoice_number: str
    currency: str
    status: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    snapshot: dict
    issued_at: datetime
    visit_ids: list[UUID] = Field(default_factory=list)


class InvoiceDetailOut(InvoiceOut):
    lines: list[InvoiceLineOut]


class GateAppointmentCreate(BaseModel):
    terminal_id: UUID
    customer_id: UUID
    vehicle_number: str = Field(min_length=4, max_length=24)
    planned_at: datetime
    notes: str = Field(default="", max_length=300)


class GateAppointmentOut(ORMModel):
    id: UUID
    terminal_id: UUID
    customer_id: UUID
    reference: str
    vehicle_number: str
    planned_at: datetime
    status: str
    notes: str
