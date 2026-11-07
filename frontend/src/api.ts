import { demoResponse, isPresentationDemo } from "./demo";

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  role: string;
  organization_name: string;
  organization_slug: string;
  user_name: string;
};

export type Session = {
  token: string;
  role: string;
  organizationName: string;
  organizationSlug: string;
  userName: string;
  terminalId?: string;
  customerId?: string;
};

export type Terminal = {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  timezone: string;
  address: string;
  is_active: boolean;
};

export type Customer = {
  id: string;
  code: string;
  name: string;
  email: string;
  terminal_id: string;
};

export type CustomerPortalAccessRequest = {
  id: string;
  company_name: string;
  contact_name: string;
  email: string;
  message: string;
  status: string;
  created_at: string;
};

export type ContactInquiry = {
  id: string;
  contact_name: string;
  email: string;
  subject: string;
  message: string;
  status: "open" | "resolved";
  created_at: string;
};

export type PortCatalogEntry = {
  code: string;
  name: string;
  city: string;
  country: string;
  region: string;
  timezone: string;
};

export type LiveContainerLocation = {
  visit_id: string;
  container_number: string;
  customer_name: string;
  terminal_id: string;
  port_name: string;
  port_address: string;
  timezone: string;
  yard_slot: string | null;
  status: string;
  current_location: string;
  last_updated_at: string;
};

export type Container = {
  id: string;
  terminal_id: string;
  customer_id: string;
  container_number: string;
  size_feet: number;
  category: string;
  is_empty: boolean;
  seal_number: string;
  cargo_description: string;
};

export type Visit = {
  id: string;
  terminal_id: string;
  container_id: string;
  vessel_call_id?: string | null;
  yard_slot_id?: string | null;
  visit_reference: string;
  direction: string;
  is_transshipment: boolean;
  status: string;
  entry_mode?: string | null;
  release_mode?: string | null;
  custody_received_at?: string | null;
  custody_released_at?: string | null;
};

export type YardSlot = {
  id: string;
  terminal_id: string;
  code: string;
  zone: string;
  block: string;
  bay: number;
  row: number;
  tier: number;
  container_category: string;
  blocked: boolean;
  occupied: boolean;
  current_visit_id?: string | null;
  current_container_number?: string | null;
};

export type VesselCall = {
  id: string;
  terminal_id: string;
  vessel_name: string;
  imo_number: string;
  voyage_number: string;
  berth: string;
  eta?: string | null;
  etd?: string | null;
  status: string;
};

export type Appointment = {
  id: string;
  terminal_id: string;
  customer_id: string;
  reference: string;
  vehicle_number: string;
  planned_at: string;
  status: string;
  notes: string;
};

export type Tariff = {
  id: string;
  tariff_id: string;
  version_number: number;
  name: string;
  free_storage_days: number;
  daily_rate: string;
  effective_from: string;
  effective_to?: string | null;
  published_at?: string | null;
};

export type Invoice = {
  id: string;
  customer_id: string;
  invoice_number: string;
  currency: string;
  status: string;
  subtotal: string;
  tax_total: string;
  total: string;
  snapshot: Record<string, unknown>;
  issued_at: string;
  visit_ids: string[];
};

export type DashboardSummary = {
  scope: string;
  demo_data?: boolean;
  containers?: number;
  in_terminal?: number;
  expected?: number;
  released_today?: number;
  available_slots?: number;
  open_invoices?: number;
  visits?: number;
};

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = typeof payload?.detail === "string"
      ? payload.detail
      : response.status >= 500 && init.method && init.method.toUpperCase() !== "GET"
        ? "The server did not confirm the save. Check the current list before retrying; the record may already have been created."
        : `Request failed (${response.status})`;
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function post<T>(path: string, body: unknown): Promise<T> {
  if (isPresentationDemo) return Promise.reject(new Error("This presentation demo is read-only."));
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function get<T>(path: string): Promise<T> {
  if (isPresentationDemo) return Promise.resolve(demoResponse(path) as T);
  return request<T>(path);
}

export async function login(email: string, password: string, organizationSlug: string) {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  form.set("organization_slug", organizationSlug);
  const response = await fetch("/api/v1/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: form,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Sign-in failed (${response.status})`);
  }
  return (await response.json()) as TokenResponse;
}

export async function register(payload: {
  organization_name: string;
  organization_slug: string;
  terminal_name: string;
  terminal_code: string;
  admin_name: string;
  email: string;
  password: string;
}) {
  const response = await fetch("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.detail ?? `Registration failed (${response.status})`);
  }
  return (await response.json()) as TokenResponse;
}

export async function requestCustomerAccess(payload: {
  organization_slug: string;
  company_name: string;
  contact_name: string;
  email: string;
  message: string;
}) {
  const response = await fetch("/api/v1/auth/customer-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.detail ?? `Access request failed (${response.status})`);
  }
  return (await response.json()) as { status: string; request_id: string; message: string };
}

export async function requestContact(payload: {
  organization_slug: string;
  contact_name: string;
  email: string;
  subject: string;
  message: string;
}) {
  const response = await fetch("/api/v1/auth/contact-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.detail ?? `Contact request failed (${response.status})`);
  }
  return (await response.json()) as { status: string; request_id: string; message: string };
}

export function sessionFromToken(token: TokenResponse): Session {
  return {
    token: token.access_token,
    role: token.role,
    organizationName: token.organization_name,
    organizationSlug: token.organization_slug,
    userName: token.user_name,
  };
}
