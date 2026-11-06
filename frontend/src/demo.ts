import type {
  Appointment,
  Container,
  Customer,
  DashboardSummary,
  Invoice,
  Tariff,
  Terminal,
  VesselCall,
  Visit,
  YardSlot,
} from "./api";

export const isPresentationDemo = typeof window !== "undefined"
  && new URLSearchParams(window.location.search).get("demo") === "1";

export const demoTerminalId = "00000000-0000-4000-8000-000000000001";

export const demoTerminal: Terminal = {
  id: demoTerminalId,
  organization_id: "00000000-0000-4000-8000-000000000000",
  code: "MUM-01",
  name: "Mumbai Gateway Terminal",
  timezone: "Asia/Kolkata",
  address: "Sample location · Mumbai, India",
  is_active: true,
};

const customers: Customer[] = [
  { id: "00000000-0000-4000-8000-000000000011", code: "WSL-001", name: "Western Star Logistics", email: "ops@westernstar.example", terminal_id: demoTerminalId },
  { id: "00000000-0000-4000-8000-000000000012", code: "BLT-002", name: "BlueLine Traders", email: "logistics@blueline.example", terminal_id: demoTerminalId },
  { id: "00000000-0000-4000-8000-000000000013", code: "MCI-003", name: "Meridian Cargo India", email: "desk@meridiancargo.example", terminal_id: demoTerminalId },
];

const containers: Container[] = [
  { id: "00000000-0000-4000-8000-000000000021", terminal_id: demoTerminalId, customer_id: customers[0].id, container_number: "TGHU4829168", size_feet: 40, category: "DRY", is_empty: false, seal_number: "SAMPLE-1048", cargo_description: "Packaged machinery · sample record" },
  { id: "00000000-0000-4000-8000-000000000022", terminal_id: demoTerminalId, customer_id: customers[1].id, container_number: "MEDU1542078", size_feet: 20, category: "REEFER", is_empty: false, seal_number: "SAMPLE-2081", cargo_description: "Chilled produce · sample record" },
  { id: "00000000-0000-4000-8000-000000000023", terminal_id: demoTerminalId, customer_id: customers[2].id, container_number: "CMAU3321480", size_feet: 40, category: "DRY", is_empty: true, seal_number: "", cargo_description: "Empty return · sample record" },
  { id: "00000000-0000-4000-8000-000000000024", terminal_id: demoTerminalId, customer_id: customers[0].id, container_number: "FSCU7612043", size_feet: 40, category: "HAZARDOUS", is_empty: false, seal_number: "SAMPLE-7612", cargo_description: "General sample cargo" },
];

const vesselId = "00000000-0000-4000-8000-000000000031";
const visits: Visit[] = [
  { id: "00000000-0000-4000-8000-000000000041", terminal_id: demoTerminalId, container_id: containers[0].id, vessel_call_id: vesselId, yard_slot_id: "00000000-0000-4000-8000-000000000051", visit_reference: "PF-DEMO-0001", direction: "import", is_transshipment: false, status: "in_terminal", entry_mode: "truck", custody_received_at: "2026-11-06T09:20:00+05:30" },
  { id: "00000000-0000-4000-8000-000000000042", terminal_id: demoTerminalId, container_id: containers[1].id, vessel_call_id: vesselId, yard_slot_id: null, visit_reference: "PF-DEMO-0002", direction: "import", is_transshipment: true, status: "expected", entry_mode: null, custody_received_at: null },
  { id: "00000000-0000-4000-8000-000000000043", terminal_id: demoTerminalId, container_id: containers[2].id, vessel_call_id: null, yard_slot_id: null, visit_reference: "PF-DEMO-0003", direction: "export", is_transshipment: false, status: "released", entry_mode: "rail", release_mode: "rail_dispatch", custody_received_at: "2026-11-05T11:10:00+05:30", custody_released_at: "2026-11-06T16:45:00+05:30" },
  { id: "00000000-0000-4000-8000-000000000044", terminal_id: demoTerminalId, container_id: containers[3].id, vessel_call_id: null, yard_slot_id: "00000000-0000-4000-8000-000000000052", visit_reference: "PF-DEMO-0004", direction: "import", is_transshipment: false, status: "in_terminal", entry_mode: "vessel", custody_received_at: "2026-11-06T14:30:00+05:30" },
];

const vessels: VesselCall[] = [
  { id: vesselId, terminal_id: demoTerminalId, vessel_name: "MV Sagar Horizon", imo_number: "IMO 9384756", voyage_number: "SH-042", berth: "B-04", eta: "2026-11-08T06:00:00+05:30", etd: "2026-11-09T18:00:00+05:30", status: "scheduled" },
  { id: "00000000-0000-4000-8000-000000000032", terminal_id: demoTerminalId, vessel_name: "MV Coastal Meridian", imo_number: "IMO 9273645", voyage_number: "CM-118", berth: "B-02", eta: "2026-11-06T04:00:00+05:30", etd: "2026-11-06T22:00:00+05:30", status: "completed" },
];

const appointments: Appointment[] = [
  { id: "00000000-0000-4000-8000-000000000061", terminal_id: demoTerminalId, customer_id: customers[0].id, reference: "GA-DEMO-1042", vehicle_number: "MH 01 AB 4829", planned_at: "2026-11-07T10:30:00+05:30", status: "scheduled", notes: "Sample import delivery" },
  { id: "00000000-0000-4000-8000-000000000062", terminal_id: demoTerminalId, customer_id: customers[1].id, reference: "GA-DEMO-1043", vehicle_number: "MH 04 CD 2078", planned_at: "2026-11-07T13:00:00+05:30", status: "arrived", notes: "Sample reefer collection" },
  { id: "00000000-0000-4000-8000-000000000063", terminal_id: demoTerminalId, customer_id: customers[2].id, reference: "GA-DEMO-1044", vehicle_number: "MH 12 EF 1480", planned_at: "2026-11-08T09:15:00+05:30", status: "scheduled", notes: "Empty container return" },
];

const slots: YardSlot[] = [
  { id: "00000000-0000-4000-8000-000000000051", terminal_id: demoTerminalId, code: "A-01-02-1", zone: "IMPORT", block: "A", bay: 1, row: 2, tier: 1, container_category: "DRY", blocked: false, occupied: true, current_visit_id: visits[0].id, current_container_number: containers[0].container_number },
  { id: "00000000-0000-4000-8000-000000000052", terminal_id: demoTerminalId, code: "B-03-01-1", zone: "HAZMAT", block: "B", bay: 3, row: 1, tier: 1, container_category: "HAZARDOUS", blocked: false, occupied: true, current_visit_id: visits[3].id, current_container_number: containers[3].container_number },
  { id: "00000000-0000-4000-8000-000000000053", terminal_id: demoTerminalId, code: "A-02-01-1", zone: "IMPORT", block: "A", bay: 2, row: 1, tier: 1, container_category: "DRY", blocked: false, occupied: false },
  { id: "00000000-0000-4000-8000-000000000054", terminal_id: demoTerminalId, code: "R-01-01-1", zone: "REEFER", block: "R", bay: 1, row: 1, tier: 1, container_category: "REEFER", blocked: false, occupied: false },
  { id: "00000000-0000-4000-8000-000000000055", terminal_id: demoTerminalId, code: "E-01-01-1", zone: "EXPORT", block: "E", bay: 1, row: 1, tier: 1, container_category: "DRY", blocked: false, occupied: false },
  { id: "00000000-0000-4000-8000-000000000056", terminal_id: demoTerminalId, code: "A-04-02-1", zone: "IMPORT", block: "A", bay: 4, row: 2, tier: 1, container_category: "DRY", blocked: true, occupied: false },
  { id: "00000000-0000-4000-8000-000000000057", terminal_id: demoTerminalId, code: "B-02-03-1", zone: "HAZMAT", block: "B", bay: 2, row: 3, tier: 1, container_category: "HAZARDOUS", blocked: false, occupied: false },
];

const tariffs: Tariff[] = [
  { id: "00000000-0000-4000-8000-000000000071", tariff_id: "00000000-0000-4000-8000-000000000070", version_number: 2, name: "Standard import storage", free_storage_days: 3, daily_rate: "850.00", effective_from: "2026-10-01T00:00:00+05:30", published_at: "2026-09-20T12:00:00+05:30" },
  { id: "00000000-0000-4000-8000-000000000072", tariff_id: "00000000-0000-4000-8000-000000000070", version_number: 3, name: "Export storage · proposed", free_storage_days: 2, daily_rate: "720.00", effective_from: "2026-11-15T00:00:00+05:30" },
];

const invoices: Invoice[] = [
  { id: "00000000-0000-4000-8000-000000000081", customer_id: customers[2].id, invoice_number: "PF-INV-DEMO-0003", currency: "INR", status: "paid", subtotal: "2550.00", tax_total: "0.00", total: "2550.00", snapshot: { note: "Fictional college presentation sample" }, issued_at: "2026-11-06T17:00:00+05:30", visit_ids: [visits[2].id] },
];

const summary: DashboardSummary = {
  scope: "terminal",
  demo_data: true,
  containers: containers.length,
  in_terminal: visits.filter((visit) => visit.status === "in_terminal").length,
  expected: visits.filter((visit) => visit.status === "expected").length,
  released_today: 1,
  available_slots: slots.filter((slot) => !slot.blocked && !slot.occupied).length,
  open_invoices: 1,
  visits: visits.length,
};

export function demoResponse(path: string): unknown {
  const route = path.split("?", 1)[0];
  switch (route) {
    case "/terminals": return [demoTerminal];
    case "/dashboard/summary": return summary;
    case "/containers": return containers;
    case "/visits": return visits;
    case "/customers": return customers;
    case "/vessels": return vessels;
    case "/appointments": return appointments;
    case "/yard/slots": return slots;
    case "/tariffs": return tariffs;
    case "/invoices": return invoices;
    default: return [];
  }
}
