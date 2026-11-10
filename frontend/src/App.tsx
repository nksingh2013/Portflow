import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Anchor,
  ArrowDownLeft,
  ArrowUpRight,
  Bell,
  Boxes,
  CalendarDays,
  Check,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  Container as ContainerIcon,
  FileText,
  Globe2,
  Mail,
  LayoutDashboard,
  LogOut,
  MapPin,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Ship,
  Truck,
  Users,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  type Appointment,
  type Container,
  type Customer,
  type CustomerPortalAccessRequest,
  type ContactInquiry,
  type DashboardSummary,
  type Invoice,
  type InvoiceDetail,
  type LiveContainerLocation,
  type PortCatalogEntry,
  type Session,
  type Tariff,
  type Terminal,
  type VesselCall,
  type Visit,
  type YardSlot,
  get,
  login,
  post,
  register,
  requestCustomerAccess,
  requestContact,
  sessionFromToken,
  setAccessToken,
} from "./api";
import { demoTerminal, demoTerminalId, isPresentationDemo } from "./demo";

type Screen = "overview" | "containers" | "gate" | "yard" | "vessels" | "billing" | "customers" | "portal" | "settings" | "locations" | "contact";
type ModalType = "walkin" | "visit" | "appointment" | "vessel" | "tariff" | "terminal" | "yard-slot" | "container" | "customer" | "customer-login" | "portal-request" | "receive" | "release" | "allocate" | null;
type Notice = { tone: "success" | "error" | "info"; text: string };
type LoginStage = "sign-in" | "register" | "customer-request" | "customer-request-sent" | "contact" | "contact-sent";

const navItems: { id: Screen; label: string; icon: LucideIcon; group: string }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, group: "WORKSPACE" },
  { id: "containers", label: "Container visits", icon: ContainerIcon, group: "OPERATIONS" },
  { id: "gate", label: "Gate & transport", icon: Truck, group: "OPERATIONS" },
  { id: "yard", label: "Yard plan", icon: Warehouse, group: "OPERATIONS" },
  { id: "vessels", label: "Vessel calls", icon: Ship, group: "OPERATIONS" },
  { id: "billing", label: "Billing", icon: CircleDollarSign, group: "MANAGEMENT" },
  { id: "customers", label: "Customers", icon: Users, group: "MANAGEMENT" },
  { id: "locations", label: "Locations", icon: MapPin, group: "OPERATIONS" },
  { id: "contact", label: "Contact inbox", icon: Mail, group: "MANAGEMENT" },
];

const money = (value: string | number | undefined) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value ?? 0));

const dateTime = (value?: string | null) =>
  value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";

const dateOnly = (value?: string | null) =>
  value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value)) : "—";

const initials = (name: string) => name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");

function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "amber" | "blue" | "red" }) {
  return <span className={`badge badge-${tone}`}><span className="badge-dot" />{children}</span>;
}

function ModalFrame({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-head"><div><span className="eyebrow">PORTFLOW WORKSPACE</span><h2 id="modal-title">{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={18} /></button></div>
        {children}
      </section>
    </div>
  );
}

function App() {
  const [stage, setStage] = useState<LoginStage>("sign-in");
  const [session, setSession] = useState<Session | null>(() => isPresentationDemo ? {
    token: "public-sample-preview",
    role: "demo_viewer",
    organizationName: "PortFlow College Demo",
    organizationSlug: "portflow-college-demo",
    userName: "College Presenter",
    terminalId: demoTerminalId,
  } : null);
  const [screen, setScreen] = useState<Screen>("overview");
  const [meta, setMeta] = useState<{ demo_mode: boolean; google_login_enabled: boolean } | null>(
    () => isPresentationDemo ? { demo_mode: true, google_login_enabled: false } : null,
  );
  const [terminals, setTerminals] = useState<Terminal[]>(() => isPresentationDemo ? [demoTerminal] : []);
  const [terminalId, setTerminalId] = useState(() => isPresentationDemo ? demoTerminalId : "");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [containers, setContainers] = useState<Container[]>([]);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [portalRequests, setPortalRequests] = useState<CustomerPortalAccessRequest[]>([]);
  const [portCatalog, setPortCatalog] = useState<PortCatalogEntry[]>([]);
  const [liveLocations, setLiveLocations] = useState<LiveContainerLocation[]>([]);
  const [contactRequests, setContactRequests] = useState<ContactInquiry[]>([]);
  const [vessels, setVessels] = useState<VesselCall[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [slots, setSlots] = useState<YardSlot[]>([]);
  const [tariffs, setTariffs] = useState<Tariff[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceDetail | null>(null);
  const [invoiceDetailLoading, setInvoiceDetailLoading] = useState(false);
  const [portalContainers, setPortalContainers] = useState<Record<string, unknown>[]>([]);
  const [portalInvoices, setPortalInvoices] = useState<Invoice[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [modal, setModal] = useState<ModalType>(null);
  const [selectedVisit, setSelectedVisit] = useState<Visit | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [selectedPortalRequest, setSelectedPortalRequest] = useState<CustomerPortalAccessRequest | null>(null);
  const [yardChoices, setYardChoices] = useState<{ slot_id: string; code: string; score: number; reason: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const actionInFlightRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [loginError, setLoginError] = useState("");
  const [registerError, setRegisterError] = useState("");
  const beginAction = () => {
    if (actionInFlightRef.current) return false;
    actionInFlightRef.current = true;
    setBusy(true);
    return true;
  };

  const endAction = () => {
    actionInFlightRef.current = false;
    setBusy(false);
  };

  useEffect(() => {
    if (isPresentationDemo) return;
    get<{ demo_mode: boolean; google_login_enabled: boolean }>("/meta").then(setMeta).catch(() => setMeta(null));
  }, []);

  const loadWorkspace = useCallback(async (currentSession: Session, currentTerminal: string) => {
    if (!currentTerminal) return false;
    setLoading(true);
    try {
      if (currentSession.role === "customer" || (currentSession.customerId && currentSession.role === "transport_operator")) {
        const [portal, portalBills, dashboard] = await Promise.all([
          get<Record<string, unknown>[]>("/portal/containers"),
          get<Invoice[]>("/portal/invoices"),
          get<DashboardSummary>(`/dashboard/summary?terminal_id=${currentTerminal}`),
        ]);
        setPortalContainers(portal);
        setPortalInvoices(portalBills);
        setSummary(dashboard);
        return true;
      }
      const [dashboard, containerRows, visitRows, customerRows, vesselRows, appointmentRows, yardRows, tariffRows, invoiceRows] = await Promise.all([
        get<DashboardSummary>(`/dashboard/summary?terminal_id=${currentTerminal}`),
        get<Container[]>(`/containers?terminal_id=${currentTerminal}`),
        get<Visit[]>(`/visits?terminal_id=${currentTerminal}`),
        get<Customer[]>(`/customers?terminal_id=${currentTerminal}`),
        get<VesselCall[]>(`/vessels?terminal_id=${currentTerminal}`),
        get<Appointment[]>(`/appointments?terminal_id=${currentTerminal}`),
        get<YardSlot[]>(`/yard/slots?terminal_id=${currentTerminal}`),
        get<Tariff[]>(`/tariffs?terminal_id=${currentTerminal}`),
        get<Invoice[]>(`/invoices?terminal_id=${currentTerminal}`),
      ]);
      setSummary(dashboard);
      setContainers(containerRows);
      setVisits(visitRows);
      setCustomers(customerRows);
      setVessels(vesselRows);
      setAppointments(appointmentRows);
      setSlots(yardRows);
      setTariffs(tariffRows);
      setInvoices(invoiceRows);
      return true;
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not load the workspace" });
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (session && terminalId) void loadWorkspace(session, terminalId);
  }, [session, terminalId, loadWorkspace]);

  useEffect(() => {
    if (!session || session.role !== "organization_admin") {
      setPortalRequests([]);
      return;
    }
    let cancelled = false;
    const refreshRequests = async () => {
      try {
        const requests = await get<CustomerPortalAccessRequest[]>("/portal-access-requests");
        if (!cancelled) setPortalRequests(requests);
      } catch {
        if (!cancelled) setPortalRequests([]);
      }
    };
    void refreshRequests();
    const timer = window.setInterval(() => void refreshRequests(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [session?.role, session?.token]);

  useEffect(() => {
    if (!session || !terminalId) {
      setPortCatalog([]);
      setLiveLocations([]);
      return;
    }
    let cancelled = false;
    const refreshLocations = async () => {
      try {
        const [catalog, locations] = await Promise.all([
          get<PortCatalogEntry[]>("/ports/catalog"),
          get<LiveContainerLocation[]>(`/locations/containers?terminal_id=${terminalId}`),
        ]);
        if (!cancelled) {
          setPortCatalog(catalog);
          setLiveLocations(locations);
        }
      } catch (error) {
        if (!cancelled) setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not load port locations" });
      }
    };
    void refreshLocations();
    const timer = window.setInterval(() => void refreshLocations(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [session?.role, session?.token, terminalId]);

  useEffect(() => {
    if (!session || session.role !== "organization_admin") {
      setContactRequests([]);
      return;
    }
    let cancelled = false;
    const refreshContactRequests = async () => {
      try {
        const requests = await get<ContactInquiry[]>("/contact-requests");
        if (!cancelled) setContactRequests(requests);
      } catch {
        if (!cancelled) setContactRequests([]);
      }
    };
    void refreshContactRequests();
    const timer = window.setInterval(() => void refreshContactRequests(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [session?.role, session?.token]);

  const finishSignIn = async (tokenResponse: Awaited<ReturnType<typeof login>>) => {
    const next = sessionFromToken(tokenResponse);
    setAccessToken(next.token);
    const [profile, terminalRows] = await Promise.all([
      get<{ terminal_id?: string; customer_id?: string }>("/me"),
      get<Terminal[]>("/terminals"),
    ]);
    const selectedTerminal = profile.terminal_id ?? terminalRows[0]?.id ?? "";
    const enriched = { ...next, terminalId: selectedTerminal, customerId: profile.customer_id };
    setTerminals(terminalRows);
    setTerminalId(selectedTerminal);
    setSession(enriched);
    setScreen(profile.customer_id ? "portal" : "overview");
    setNotice({ tone: "success", text: `Welcome back, ${next.userName}.` });
    setLoginError("");
    setRegisterError("");
  };

  const handleSignIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!beginAction()) return;
    const form = new FormData(event.currentTarget);
    setLoginError("");
    try {
      const result = await login(String(form.get("email")), String(form.get("password")), String(form.get("organization")));
      await finishSignIn(result);
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Sign-in failed");
    } finally {
      endAction();
    }
  };

  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!beginAction()) return;
    const form = new FormData(event.currentTarget);
    setRegisterError("");
    try {
      const result = await register({
        organization_name: String(form.get("organization_name")),
        organization_slug: String(form.get("organization_slug")).toLowerCase().trim(),
        terminal_name: String(form.get("terminal_name")),
        terminal_code: String(form.get("terminal_code")).toUpperCase().trim(),
        admin_name: String(form.get("admin_name")),
        email: String(form.get("email")),
        password: String(form.get("password")),
      });
      await finishSignIn(result);
      setNotice({ tone: "success", text: `Workspace created. Save organization slug “${result.organization_slug}” for future sign-in.` });
    } catch (error) {
      setRegisterError(error instanceof Error ? error.message : "Registration failed");
    } finally {
      endAction();
    }
  };

  const handleCustomerAccessRequest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!beginAction()) return;
    const form = new FormData(event.currentTarget);
    setRegisterError("");
    try {
      await requestCustomerAccess({
        organization_slug: String(form.get("organization_slug")).trim().toLowerCase(),
        company_name: String(form.get("company_name")).trim(),
        contact_name: String(form.get("contact_name")).trim(),
        email: String(form.get("email")).trim(),
        message: String(form.get("message")).trim(),
      });
      setStage("customer-request-sent");
    } catch (error) {
      setRegisterError(error instanceof Error ? error.message : "Access request could not be sent");
    } finally {
      endAction();
    }
  };

  const handlePublicContactRequest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!beginAction()) return;
    const form = new FormData(event.currentTarget);
    setRegisterError("");
    try {
      await requestContact({
        organization_slug: String(form.get("organization_slug")).trim().toLowerCase(),
        contact_name: String(form.get("contact_name")).trim(),
        email: String(form.get("email")).trim(),
        subject: String(form.get("subject")).trim(),
        message: String(form.get("message")).trim(),
      });
      setStage("contact-sent");
    } catch (error) {
      setRegisterError(error instanceof Error ? error.message : "Contact request could not be sent");
    } finally {
      endAction();
    }
  };

  const signOut = () => {
    setAccessToken(null);
    setSession(null);
    setTerminalId("");
    setSummary(null);
    setNotice(null);
    setScreen("overview");
    setStage("sign-in");
  };

  const runAction = async (action: () => Promise<unknown>, success: string | ((result: unknown) => string)) => {
    if (session?.role === "demo_viewer") {
      setNotice({ tone: "info", text: "Read-only presentation demo · changes are disabled." });
      return;
    }
    if (!beginAction()) return;
    setNotice(null);
    try {
      const result = await action();
      const successMessage = typeof success === "function" ? success(result) : success;
      setNotice({ tone: "success", text: successMessage });
      setModal(null);
      setSelectedVisit(null);
      setSelectedCustomer(null);
      setSelectedPortalRequest(null);
      if (session?.role === "organization_admin" && selectedScreen === "customers") {
        try { setPortalRequests(await get<CustomerPortalAccessRequest[]>("/portal-access-requests")); } catch { /* Keep the last visible request list until the next poll. */ }
      }
      if (session?.role === "organization_admin" && selectedScreen === "settings") {
        try { setTerminals(await get<Terminal[]>("/terminals")); } catch { /* Keep the last visible terminal list until the next poll. */ }
      }
      if (session?.role === "organization_admin" && selectedScreen === "contact") {
        try { setContactRequests(await get<ContactInquiry[]>("/contact-requests")); } catch { /* Keep the last visible inbox until the next poll. */ }
      }
      if (session && terminalId) {
        const refreshed = await loadWorkspace(session, terminalId);
        if (!refreshed) {
          setNotice({ tone: "success", text: `${successMessage} The list could not refresh; reload to see the latest records.` });
        }
        try { setLiveLocations(await get<LiveContainerLocation[]>(`/locations/containers?terminal_id=${terminalId}`)); } catch { /* The polling refresh will retry without hiding the completed action. */ }
      }
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Action could not be completed" });
    } finally {
      endAction();
    }
  };

  const openAllocation = async (visit: Visit) => {
    if (session?.role === "demo_viewer") {
      setNotice({ tone: "info", text: "Read-only presentation demo · changes are disabled." });
      return;
    }
    if (!beginAction()) return;
    setNotice(null);
    try {
      const options = await get<typeof yardChoices>(`/yard/suggestions?visit_id=${visit.id}`);
      setSelectedVisit(visit);
      setYardChoices(options);
      setModal("allocate");
      if (!options.length) setNotice({ tone: "info", text: "No compatible clear yard slot is available." });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not suggest a yard slot" });
    } finally {
      endAction();
    }
  };

  const openInvoiceDetails = async (invoiceId: string) => {
    setInvoiceDetailLoading(true);
    setSelectedInvoice(null);
    try {
      const detail = await get<InvoiceDetail>(`/invoices/${invoiceId}`);
      setSelectedInvoice(detail);
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not load invoice details." });
    } finally {
      setInvoiceDetailLoading(false);
    }
  };

  const activeTerminal = terminals.find((terminal) => terminal.id === terminalId);
  const customerMap = useMemo(() => new Map(customers.map((customer) => [customer.id, customer])), [customers]);
  const containerMap = useMemo(() => new Map(containers.map((container) => [container.id, container])), [containers]);
  const visitRows = useMemo(() => visits.map((visit) => ({ visit, container: containerMap.get(visit.container_id), customer: containerMap.get(visit.container_id) ? customerMap.get(containerMap.get(visit.container_id)!.customer_id) : undefined })), [visits, containerMap, customerMap]);
  const filteredVisits = visitRows.filter(({ visit, container, customer }) => {
    const term = search.trim().toLowerCase();
    return !term || [visit.visit_reference, container?.container_number, customer?.name, visit.status].some((value) => value?.toLowerCase().includes(term));
  });
  const operator = session?.role !== "customer";
  const readOnlyDemo = session?.role === "demo_viewer";

  if (!session) {
    return (
      <AuthScreen
        stage={stage}
        busy={busy}
        error={stage === "sign-in" ? loginError : registerError}
        onSignIn={handleSignIn}
        onRegister={handleRegister}
        onCustomerAccessRequest={handleCustomerAccessRequest}
        onContactRequest={handlePublicContactRequest}
        onStageChange={(next) => { setStage(next); setLoginError(""); setRegisterError(""); }}
        demoMode={meta?.demo_mode ?? false}
      />
    );
  }

  const customerMode = session.role === "customer" || (!!session.customerId && session.role === "transport_operator");
  const selectedScreen: Screen = customerMode && screen === "overview" ? "portal" : screen;
  const nav = customerMode ? [
    { id: "portal" as Screen, label: "My containers", icon: ContainerIcon, group: "CUSTOMER" },
    { id: "billing" as Screen, label: "Invoices", icon: FileText, group: "CUSTOMER" },
    { id: "locations" as Screen, label: "Locations", icon: MapPin, group: "CUSTOMER" },
    { id: "contact" as Screen, label: "Contact us", icon: Mail, group: "CUSTOMER" },
  ] : navItems.map((item) => item.id === "contact" && session.role !== "organization_admin" ? { ...item, label: "Contact us" } : item);

  const openModal = (name: ModalType) => {
    if (readOnlyDemo) {
      setNotice({ tone: "info", text: "Read-only presentation demo · changes are disabled." });
      return;
    }
    setNotice(null);
    setModal(name);
  };
  const handleTerminalChange = (value: string) => {
    setTerminalId(value);
    setSession((current) => current ? { ...current, terminalId: value } : current);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenuOpen ? "sidebar-open" : ""}`}>
        <div className="brand"><div className="brand-mark"><Anchor size={20} strokeWidth={2.2} /></div><span>portflow</span><span className="brand-beta">OPS</span><button className="sidebar-close icon-button" onClick={() => setMobileMenuOpen(false)} aria-label="Close menu"><X size={17} /></button></div>
        <div className="workspace-picker"><div className="workspace-avatar">{initials(session.organizationName)}</div><div className="workspace-copy"><strong>{session.organizationName}</strong><span>Organization workspace</span></div><ChevronDown size={15} /></div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {nav.map((item, index) => {
            const previous = nav[index - 1];
            return <div key={item.id}>{(!previous || previous.group !== item.group) && <div className="nav-group-label">{item.group}</div>}<button className={`nav-link ${selectedScreen === item.id ? "nav-link-active" : ""}`} onClick={() => { setScreen(item.id); setMobileMenuOpen(false); }}><item.icon size={17} strokeWidth={1.8} /><span>{item.label}</span>{item.id === "gate" && summary?.expected ? <span className="nav-count">{summary.expected}</span> : item.id === "customers" && portalRequests.length ? <span className="nav-count">{portalRequests.length}</span> : item.id === "contact" && contactRequests.length ? <span className="nav-count">{contactRequests.length}</span> : null}</button></div>;
          })}
        </nav>
        <div className="sidebar-bottom">
          {!customerMode && <button className={`nav-link ${selectedScreen === "settings" ? "nav-link-active" : ""}`} onClick={() => { setScreen("settings"); setMobileMenuOpen(false); }}><Settings size={17} /><span>Organization setup</span></button>}
          <div className="sidebar-help"><div className="help-icon"><ShieldCheck size={16} /></div><div><strong>Tenant protected</strong><span>Access is role-scoped</span></div></div>
          <div className="profile-row"><div className="profile-avatar">{initials(session.userName)}</div><div className="profile-copy"><strong>{session.userName}</strong><span>{session.role.replaceAll("_", " ")}</span></div><button className="icon-button profile-logout" title="Sign out" onClick={signOut}><LogOut size={16} /></button></div>
        </div>
      </aside>
      {mobileMenuOpen && <button className="mobile-overlay" onClick={() => setMobileMenuOpen(false)} aria-label="Close navigation" />}

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu-button icon-button" onClick={() => setMobileMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="breadcrumb"><span>PortFlow</span><span className="breadcrumb-slash">/</span><strong>{customerMode ? "Customer portal" : nav.find((item) => item.id === selectedScreen)?.label ?? "Organization setup"}</strong></div>
          <div className="topbar-right">
            {operator && <label className="terminal-select"><MapPin size={15} /><select value={terminalId} onChange={(event) => handleTerminalChange(event.target.value)} aria-label="Select terminal">{terminals.map((terminal) => <option key={terminal.id} value={terminal.id}>{terminal.name}</option>)}</select><ChevronDown size={14} /></label>}
            <button className="top-icon-button" title="Notifications are not configured" disabled><Bell size={17} /></button>
            <div className="top-avatar">{initials(session.userName)}</div>
          </div>
        </header>

        <div className="page-content">
          {readOnlyDemo ? <div className="demo-banner demo-readonly-banner"><span className="demo-pulse" /><strong>READ-ONLY PRESENTATION</strong><span>Fictional sample data · changes are disabled</span><a href="/?login=1">Administrator sign in</a></div> : meta?.demo_mode && <div className="demo-banner"><span className="demo-pulse" /><strong>DEMO ENVIRONMENT</strong><span>No live port, email, or payment integrations</span></div>}
          {notice && <div className={`notice notice-${notice.tone}`}><span>{notice.text}</span><button onClick={() => setNotice(null)} aria-label="Dismiss message"><X size={15} /></button></div>}
          {session.role === "organization_admin" && portalRequests.length > 0 && selectedScreen !== "customers" && <div className="notice notice-info"><span>{portalRequests.length} customer access request{portalRequests.length === 1 ? "" : "s"} need review.</span><button className="text-button" onClick={() => setScreen("customers")}>Review requests <ArrowUpRight size={14} /></button></div>}
          {session.role === "organization_admin" && contactRequests.length > 0 && selectedScreen !== "contact" && <div className="notice notice-info"><span>{contactRequests.length} contact message{contactRequests.length === 1 ? "" : "s"} need review.</span><button className="text-button" onClick={() => setScreen("contact")}>Open inbox <ArrowUpRight size={14} /></button></div>}
          {loading && <div className="loading-line"><span />Refreshing terminal data…</div>}
          {selectedScreen === "overview" && !customerMode && <OverviewView summary={summary} rows={visitRows} vessels={vessels} slots={slots} onWalkIn={() => openModal("walkin")} onAppointment={() => openModal("appointment")} onNavigate={setScreen} />}
          {selectedScreen === "containers" && !customerMode && <ContainersView rows={filteredVisits} search={search} setSearch={setSearch} onRegister={() => openModal("container")} onWalkIn={() => openModal("walkin")} onCreateFirstVisit={() => openModal("visit")} onReceive={(visit) => { setSelectedVisit(visit); openModal("receive"); }} onRelease={(visit) => { setSelectedVisit(visit); openModal("release"); }} onAllocate={openAllocation} onNavigate={setScreen} />}
          {selectedScreen === "gate" && !customerMode && <GateView appointments={appointments} rows={filteredVisits} customers={customers} onWalkIn={() => openModal("walkin")} onAppointment={() => openModal("appointment")} onReceive={(visit) => { setSelectedVisit(visit); openModal("receive"); }} onRelease={(visit) => { setSelectedVisit(visit); openModal("release"); }} onAllocate={openAllocation} />}
          {selectedScreen === "yard" && !customerMode && <YardView slots={slots} visits={filteredVisits} canManage={session.role === "organization_admin" || session.role === "terminal_manager"} onAddSlot={() => openModal("yard-slot")} onAllocate={openAllocation} />}
          {selectedScreen === "vessels" && !customerMode && <VesselsView vessels={vessels} visits={visitRows} onAdd={() => openModal("vessel")} />}
          {selectedScreen === "billing" && (customerMode ? <CustomerBilling invoices={portalInvoices} /> : <BillingView tariffs={tariffs} invoices={invoices} visits={visits} onNewTariff={() => openModal("tariff")} onViewInvoice={(id) => void openInvoiceDetails(id)} onPublish={(id) => void runAction(() => post(`/tariffs/versions/${id}/publish`, {}), "Tariff version published and locked.")} onGenerate={(id) => void (async () => {
            try {
              const preview = await get<{ visit_reference: string; container_number: string; tariff_name: string; tariff_version: number; total_calendar_days: number; free_storage_days: number; billable_days: number; daily_rate: string; subtotal: string; tax_total: string; total: string; tax_note: string; zero_amount_reason: string | null }>(`/invoices/preview/${id}`);
              const details = [
                `Visit: ${preview.visit_reference}`,
                `Container: ${preview.container_number}`,
                `Tariff: ${preview.tariff_name} (v${preview.tariff_version})`,
                `Calendar days: ${preview.total_calendar_days}`,
                `Free days: ${preview.free_storage_days}`,
                `Billable days: ${preview.billable_days}`,
                `Daily rate: ${money(preview.daily_rate)}`,
                `Subtotal: ${money(preview.subtotal)}`,
                `Tax: ${money(preview.tax_total)} (not configured)`,
                `Total: ${money(preview.total)}`,
                preview.zero_amount_reason ? `Reason: ${preview.zero_amount_reason}` : "",
                "",
                "Generate and issue this invoice now?"
              ].filter(Boolean).join("\\n");
              if (window.confirm(details)) {
                await runAction(() => post(`/invoices/generate/${id}`, {}), "Operational invoice generated.");
              }
            } catch (error) {
              setNotice({ tone: "error", text: error instanceof Error ? error.message : "Could not preview this invoice." });
            }
          })()} />)}
          {selectedScreen === "customers" && !customerMode && <CustomersView customers={customers} visitRows={visitRows} portalRequests={session.role === "organization_admin" ? portalRequests : []} canManagePortal={session.role === "organization_admin"} onAdd={() => openModal("customer")} onApproveRequest={(request) => { setSelectedPortalRequest(request); openModal("portal-request"); }} onRejectRequest={(requestId) => void runAction(() => post(`/portal-access-requests/${requestId}/reject`, {}), "Customer access request declined.")} onCreatePortalLogin={(customer) => { setSelectedCustomer(customer); openModal("customer-login"); }} />}
          {selectedScreen === "portal" && customerMode && <PortalView rows={portalContainers} invoices={portalInvoices} />}
          {selectedScreen === "locations" && <LocationsView catalog={portCatalog} rows={liveLocations} />}
          {selectedScreen === "contact" && <ContactView
            isAdmin={session.role === "organization_admin"}
            organizationSlug={session.organizationSlug}
            requests={contactRequests}
            onResolve={(requestId) => void runAction(() => post(`/contact-requests/${requestId}/resolve`, {}), "Contact request marked resolved.")}
            onSubmit={(payload) => void runAction(() => post("/auth/contact-requests", payload), "Your message was saved to the organization inbox. Email delivery is not configured.")}
          />}
          {selectedScreen === "settings" && !customerMode && <SettingsView terminals={terminals} catalogCount={portCatalog.length} canImport={session.role === "organization_admin"} onAdd={() => openModal("terminal")} onImport={() => void runAction(
            () => post<{ created_count: number; skipped_count: number; total_catalog_count: number }>("/terminals/import-asian-ports", {}),
            (result) => `Added ${(result as { created_count: number }).created_count} ports; ${(result as { skipped_count: number }).skipped_count} already existed and were kept.`,
          )} />}
          <footer className="page-footer"><span>PortFlow Terminal Operations</span><span><ShieldCheck size={13} /> Tenant context verified · {activeTerminal?.timezone ?? "Asia/Kolkata"}</span><a href="/api/docs" target="_blank" rel="noreferrer">API reference ↗</a></footer>
        </div>
      </main>

      {invoiceDetailLoading && <div className="modal-backdrop"><section className="modal-card"><div className="modal-head"><h2>Loading invoice details…</h2></div><p className="form-hint">Fetching the saved invoice snapshot and linked visit lines.</p></section></div>}
      {selectedInvoice && <InvoiceDetailModal invoice={selectedInvoice} onClose={() => setSelectedInvoice(null)} />}
      {modal && <WorkspaceModal
        type={modal}
        busy={busy}
        terminals={terminals}
        customers={customers}
        containers={containers}
        vessels={vessels}
        selectedTerminal={terminalId}
        selectedVisit={selectedVisit}
        selectedCustomer={selectedCustomer}
        selectedPortalRequest={selectedPortalRequest}
        yardChoices={yardChoices}
        onClose={() => { if (!busy) { setModal(null); setSelectedVisit(null); setSelectedCustomer(null); setSelectedPortalRequest(null); } }}
        onSubmit={(type, form) => {
          const getValue = (name: string) => String(form.get(name) ?? "");
          const terminal = getValue("terminal_id") || terminalId;
          const customer = getValue("customer_id");
          const idempotency = `${type}-${crypto.randomUUID()}`;
          if (type === "walkin") return runAction(() => post("/gate/walk-ins", {
            terminal_id: terminal,
            customer_id: customer,
            container_number: getValue("container_number").toUpperCase(),
            size_feet: Number(getValue("size_feet")),
            category: getValue("category"),
            is_empty: form.get("is_empty") === "on",
            direction: getValue("direction"),
            entry_mode: getValue("entry_mode"),
            vessel_call_id: getValue("vessel_call_id") || null,
            is_transshipment: form.get("is_transshipment") === "on",
            idempotency_key: idempotency,
          }), "Walk-in custody recorded and visit opened.");
          if (type === "visit") return runAction(() => post("/visits", {
            terminal_id: terminal,
            container_id: getValue("container_id"),
            direction: getValue("direction"),
            vessel_call_id: getValue("vessel_call_id") || null,
            is_transshipment: form.get("is_transshipment") === "on",
            idempotency_key: idempotency,
          }), "First visit created for the registered container.");
          if (type === "appointment") return runAction(() => post("/appointments", { terminal_id: terminal, customer_id: customer, vehicle_number: getValue("vehicle_number").toUpperCase(), planned_at: new Date(getValue("planned_at")).toISOString(), notes: getValue("notes") }), "Gate appointment scheduled.");
          if (type === "vessel") return runAction(() => post("/vessels", { terminal_id: terminal, vessel_name: getValue("vessel_name"), imo_number: getValue("imo_number"), voyage_number: getValue("voyage_number"), berth: getValue("berth"), eta: getValue("eta") ? new Date(getValue("eta")).toISOString() : null, etd: getValue("etd") ? new Date(getValue("etd")).toISOString() : null }), "Manual vessel call added.");
          if (type === "tariff") return runAction(() => post("/tariffs", { terminal_id: terminal, name: getValue("name"), free_storage_days: Number(getValue("free_storage_days")), daily_rate: Number(getValue("daily_rate")), effective_from: new Date(getValue("effective_from")).toISOString() }), "Draft tariff version created. Publish it to make it active.");
          if (type === "terminal") return runAction(() => post("/terminals", { code: getValue("code").toUpperCase(), name: getValue("name"), timezone: getValue("timezone"), address: getValue("address") }), "Terminal added to the organization.");
          if (type === "yard-slot") return runAction(() => post("/yard/slots", { terminal_id: terminal, code: getValue("code").trim().toUpperCase(), zone: getValue("zone").trim().toUpperCase() || "GENERAL", block: getValue("block").trim().toUpperCase(), bay: Number(getValue("bay")), row: Number(getValue("row")), tier: Number(getValue("tier")), container_category: getValue("container_category") }), "Yard slot added. It is now available for compatible container allocation.");
          if (type === "customer") return runAction(() => post(`/customers?terminal_id=${terminal}`, { code: getValue("code").toUpperCase(), name: getValue("name"), email: getValue("email") || null }), "Customer account added to this terminal.");
          if (type === "customer-login" && selectedCustomer) return runAction(() => post(`/customers/${selectedCustomer.id}/portal-users`, { display_name: getValue("display_name"), email: getValue("email"), password: getValue("password") }), `Customer portal login created for ${getValue("email")}. Email delivery is not configured, so share the password directly. Sign-in organization: ${session.organizationSlug}.`);
          if (type === "portal-request" && selectedPortalRequest) return runAction(() => post(`/portal-access-requests/${selectedPortalRequest.id}/approve`, { customer_id: getValue("customer_id"), password: getValue("password") }), `Access approved for ${selectedPortalRequest.email}. Share the password securely. Sign-in organization: ${session.organizationSlug}. Customers do not need an authenticator code.`);
          if (type === "container") return runAction(() => post("/containers", { terminal_id: terminal, customer_id: customer, container_number: getValue("container_number").toUpperCase(), size_feet: Number(getValue("size_feet")), category: getValue("category"), is_empty: form.get("is_empty") === "on", seal_number: getValue("seal_number"), cargo_description: getValue("cargo_description") }), "Container registered.");
          if (type === "receive" && selectedVisit) return runAction(() => post(`/visits/${selectedVisit.id}/custody/receive`, { mode: getValue("mode"), idempotency_key: idempotency, external_reference: getValue("external_reference") }), "Custody receipt recorded.");
          if (type === "release" && selectedVisit) return runAction(() => post(`/visits/${selectedVisit.id}/custody/release`, { mode: getValue("mode"), idempotency_key: idempotency, external_reference: getValue("external_reference") }), "Custody released. Any applicable operational invoice is available in Billing.");
          if (type === "allocate" && selectedVisit) return runAction(() => post("/yard/allocate", { visit_id: selectedVisit.id, slot_id: getValue("slot_id") || null }), "Yard slot assigned and movement recorded.");
          return Promise.resolve();
        }}
      />}
    </div>
  );
}

function AuthScreen({
  stage,
  busy,
  error,
  onSignIn,
  onRegister,
  onCustomerAccessRequest,
  onContactRequest,
  onStageChange,
  demoMode,
}: {
  stage: LoginStage;
  busy: boolean;
  error: string;
  onSignIn: (event: FormEvent<HTMLFormElement>) => void;
  onRegister: (event: FormEvent<HTMLFormElement>) => void;
  onCustomerAccessRequest: (event: FormEvent<HTMLFormElement>) => void;
  onContactRequest: (event: FormEvent<HTMLFormElement>) => void;
  onStageChange: (stage: LoginStage) => void;
  demoMode: boolean;
}) {
  const [showPassword, setShowPassword] = useState(false);
  return (
    <div className="auth-page">
      <div className="auth-art">
        <div className="auth-brand"><div className="brand-mark"><Anchor size={21} /></div><span>portflow</span></div>
        <div className="auth-hero-copy"><span className="eyebrow auth-eyebrow">TERMINAL OPERATIONS, CONNECTED</span><h1>Every movement<br />in one clear view.</h1><p>Coordinate the yard, gate and vessel plan with a shared operational record for your team and customers.</p></div>
        <div className="port-illustration" aria-hidden="true"><div className="port-sun" /><div className="port-crane crane-one"><span /><i /><b /></div><div className="port-crane crane-two"><span /><i /><b /></div><div className="port-ship"><div className="ship-stack" /><div className="ship-body" /></div><div className="port-water water-one" /><div className="port-water water-two" /><div className="port-water water-three" /></div>
        <div className="auth-art-foot"><span>BUILT FOR COMPLEX PORT OPERATIONS</span><span>INDIA FIRST&nbsp; · &nbsp;INR NATIVE</span></div>
      </div>
      <div className="auth-panel">
        <div className="auth-panel-top"><span className="secure-label"><ShieldCheck size={14} /> SECURE WORKSPACE</span><a href="/api/docs" target="_blank" rel="noreferrer">API docs ↗</a></div>
        <div className="auth-form-wrap">
          {demoMode && <div className="auth-demo-tag"><span className="demo-pulse" /> DEMO ENVIRONMENT · No live port, email, or payment integrations</div>}
          {stage === "sign-in" && <>
            <span className="eyebrow">WELCOME TO PORTFLOW</span><h2>Sign in to your terminal</h2><p className="auth-subtitle">Use your organization account to open the operations workspace.</p>
            {error && <div className="form-error">{error}</div>}
            <form className="form-stack" onSubmit={onSignIn}>
              <Field label="Organization slug (if needed)" name="organization" placeholder="Leave blank if you have one organization" autoComplete="organization" />
              <Field label="Work email" name="email" type="email" placeholder="name@company.com" autoComplete="username" required />
              <div className="field"><label htmlFor="login-password">Password</label><div className="password-wrap"><input id="login-password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required /><button type="button" className="show-password" onClick={() => setShowPassword((value) => !value)}>{showPassword ? "Hide" : "Show"}</button></div></div>
              <button className="primary-button auth-submit" disabled={busy}>{busy ? <><span className="button-spinner" /> Signing in…</> : <>Continue <ArrowUpRight size={17} /></>}</button>
            </form>
            {demoMode && <a className="secondary-button demo-preview-link" href="/?demo=1">Open the read-only sample workspace <ArrowUpRight size={15} /></a>}
            <button className="provider-button" disabled title="Google OAuth is not configured"><span className="google-mark">G</span> Continue with Google <span className="provider-note">Not configured</span></button>
            <p className="auth-switch">Customer access? <button onClick={() => onStageChange("customer-request")}>Request a login</button></p>
            <p className="auth-switch">New to PortFlow? <button onClick={() => onStageChange("register")}>Set up an organization</button></p>
            <p className="auth-switch">Need help? <button onClick={() => onStageChange("contact")}>Contact us</button></p>
          </>}
          {stage === "register" && <>
            <button className="back-link" onClick={() => onStageChange("sign-in")}>← Back to sign in</button><span className="eyebrow">START YOUR WORKSPACE</span><h2>Create an organization</h2><p className="auth-subtitle">Create your workspace and continue with your email and password.</p>
            {error && <div className="form-error">{error}</div>}
            <form className="form-stack form-stack-compact" onSubmit={onRegister}>
              <Field label="Organization name" name="organization_name" placeholder="Western Coast Terminals" required />
              <div className="form-row"><Field label="Organization slug" name="organization_slug" placeholder="western-coast" required /><Field label="First terminal code" name="terminal_code" placeholder="MUM-01" required /></div>
              <Field label="First terminal name" name="terminal_name" placeholder="Mumbai Gateway Terminal" required />
              <Field label="Administrator name" name="admin_name" placeholder="Your name" required />
              <Field label="Work email" name="email" type="email" placeholder="name@company.com" required />
              <Field label="Password · 12 characters minimum" name="password" type="password" autoComplete="new-password" minLength={12} required />
              <button className="primary-button auth-submit" disabled={busy}>{busy ? <><span className="button-spinner" /> Creating…</> : <>Create workspace <ArrowUpRight size={17} /></>}</button>
            </form>
          </>}
          {stage === "customer-request" && <>
            <button className="back-link" onClick={() => onStageChange("sign-in")}>← Back to sign in</button><span className="eyebrow">CUSTOMER PORTAL</span><h2>Request customer access</h2><p className="auth-subtitle">Send your details to the organization administrator. They will review your request and contact you with login details.</p>
            {error && <div className="form-error">{error}</div>}
            <form className="form-stack form-stack-compact" onSubmit={onCustomerAccessRequest}>
              <Field label="Organization slug" name="organization_slug" placeholder="Ask your terminal contact for this" required autoComplete="organization" />
              <Field label="Company name" name="company_name" placeholder="Your logistics company" required />
              <Field label="Contact name" name="contact_name" placeholder="Your name" required autoComplete="name" />
              <Field label="Work email" name="email" type="email" placeholder="name@company.com" required autoComplete="email" />
              <Field label="Message (optional)" name="message" placeholder="What access do you need?" maxLength={500} />
              <div className="form-hint">No password is created yet. The administrator will approve the request, set a password and share it with you. Customers do not need an authenticator code.</div>
              <button className="primary-button auth-submit" disabled={busy}>{busy ? <><span className="button-spinner" /> Sending request…</> : <>Send request <ArrowUpRight size={17} /></>}</button>
            </form>
          </>}
          {stage === "customer-request-sent" && <>
            <span className="eyebrow">REQUEST SENT</span><h2>Your request is with the administrator</h2><p className="auth-subtitle">The administrator will see it in the Customers workspace and contact you to provide your sign-in details. This demo does not send automatic email notifications.</p><div className="form-hint"><ShieldCheck size={14} /> Customer sign-in does not require an authenticator code.</div><button className="secondary-button" onClick={() => onStageChange("sign-in")}>Back to sign in</button>
          </>}
          {stage === "contact" && <>
            <button className="back-link" onClick={() => onStageChange("sign-in")}>← Back to sign in</button><span className="eyebrow">CONTACT THE ORGANIZATION</span><h2>Send us a message</h2><p className="auth-subtitle">Your message will appear in the organization’s in-app inbox. Email delivery is not configured.</p>
            {error && <div className="form-error">{error}</div>}
            <form className="form-stack form-stack-compact" onSubmit={onContactRequest}>
              <Field label="Organization slug" name="organization_slug" placeholder="Ask your terminal contact" required autoComplete="organization" />
              <Field label="Your name" name="contact_name" placeholder="Your name" required autoComplete="name" />
              <Field label="Email address" name="email" type="email" placeholder="name@company.com" required autoComplete="email" />
              <Field label="Subject" name="subject" placeholder="How can we help?" required minLength={2} maxLength={180} />
              <div className="field"><label htmlFor="public-contact-message">Message</label><textarea id="public-contact-message" name="message" rows={4} required minLength={5} maxLength={2000} placeholder="Write your message" /></div>
              <button className="primary-button auth-submit" disabled={busy}>{busy ? <><span className="button-spinner" /> Sending…</> : <>Send message <ArrowUpRight size={17} /></>}</button>
            </form>
          </>}
          {stage === "contact-sent" && <>
            <span className="eyebrow">MESSAGE SAVED</span><h2>Your message is in the inbox</h2><p className="auth-subtitle">The organization administrator can now see your request in PortFlow. No email notification is sent until an email provider is configured.</p><button className="secondary-button" onClick={() => onStageChange("sign-in")}>Back to sign in</button>
          </>}
          <div className="auth-legal"><ShieldCheck size={14} /> Tenant access is checked by the server for every request.</div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, name, type = "text", placeholder, required, minLength, maxLength, min, defaultValue, inputMode, autoComplete }: { label: string; name: string; type?: string; placeholder?: string; required?: boolean; minLength?: number; maxLength?: number; min?: number; defaultValue?: string | number; inputMode?: "text" | "numeric" | "email" | "tel" | "url" | "search" | "decimal"; autoComplete?: string }) {
  return <div className="field"><label htmlFor={name}>{label}</label><input id={name} name={name} type={type} placeholder={placeholder} required={required} minLength={minLength} maxLength={maxLength} min={min} defaultValue={defaultValue} inputMode={inputMode} autoComplete={autoComplete} /></div>;
}

function OverviewView({ summary, rows, vessels, slots, onWalkIn, onAppointment, onNavigate }: { summary: DashboardSummary | null; rows: { visit: Visit; container?: Container; customer?: Customer }[]; vessels: VesselCall[]; slots: YardSlot[]; onWalkIn: () => void; onAppointment: () => void; onNavigate: (screen: Screen) => void }) {
  const activeRows = rows.filter((row) => row.visit.status === "in_terminal").slice(0, 5);
  const upcoming = vessels.filter((vessel) => vessel.status !== "completed").slice(0, 3);
  return <>
    <div className="page-heading"><div><div className="eyebrow">{new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "2-digit", month: "long", year: "numeric" }).format(new Date()).toUpperCase()} <span className="heading-dot" /> TERMINAL OVERVIEW</div><h1>Good day, operations team</h1><p>Monitor the yard, gate and vessel plan from one workspace.</p></div><div className="heading-actions"><button className="secondary-button" onClick={onAppointment}><CalendarDays size={16} /> Schedule gate visit</button><button className="primary-button" onClick={onWalkIn}><Plus size={17} /> Register walk-in</button></div></div>
    <div className="status-strip"><span className="status-indicator"><span /> Operations active</span><span className="strip-divider" /><span><Clock3 size={14} /> Data from the terminal record</span><button onClick={() => onNavigate("containers")}>Review visits <ArrowUpRight size={13} /></button></div>
    <div className="metric-grid">
      <MetricCard label="In terminal" value={summary?.in_terminal} detail="Visits in active custody" icon={ContainerIcon} accent="teal" onClick={() => onNavigate("containers")} />
      <MetricCard label="Expected at gate" value={summary?.expected} detail="Visits awaiting receipt" icon={Truck} accent="amber" onClick={() => onNavigate("gate")} />
      <MetricCard label="Yard slots" value={summary?.available_slots} detail={`${summary?.available_slots ?? 0} configured slots`} icon={Warehouse} accent="blue" onClick={() => onNavigate("yard")} />
      <MetricCard label="Operational invoices" value={summary?.open_invoices} detail="Issued to customers" icon={CircleDollarSign} accent="purple" onClick={() => onNavigate("billing")} />
    </div>
    <div className="overview-grid">
      <section className="panel active-panel"><div className="panel-heading"><div><span className="eyebrow">LIVE TERMINAL QUEUE</span><h2>Containers in custody</h2></div><button className="text-button" onClick={() => onNavigate("containers")}>View all <ArrowUpRight size={14} /></button></div>
        <div className="table-wrap"><table><thead><tr><th>CONTAINER</th><th>CUSTOMER</th><th>RECEIVED</th><th>YARD SLOT</th><th>STATUS</th></tr></thead><tbody>{activeRows.map(({ visit, container, customer }) => <tr key={visit.id}><td><div className="container-cell"><span className="container-glyph"><ContainerIcon size={14} /></span><div><strong>{container?.container_number ?? "—"}</strong><small>{container?.size_feet ?? "—"} ft · {container?.category ?? "—"}</small></div></div></td><td>{customer?.name ?? "—"}</td><td>{dateTime(visit.custody_received_at)}</td><td>{visit.yard_slot_id ? slots.find((slot) => slot.id === visit.yard_slot_id)?.code ?? "Assigned" : <span className="muted">Unallocated</span>}</td><td><Badge tone="green">In terminal</Badge></td></tr>)}{!activeRows.length && <EmptyTable columns={5} title="No containers in custody" detail="Record a gate, rail or vessel receipt to populate this queue." />}</tbody></table></div>
      </section>
      <section className="panel action-panel"><div className="panel-heading"><div><span className="eyebrow">QUICK ACTIONS</span><h2>Keep things moving</h2></div><span className="panel-kicker">OPERATIONS</span></div>
        <button className="quick-action" onClick={onWalkIn}><div className="quick-icon quick-teal"><Truck size={17} /></div><span><strong>Record a walk-in</strong><small>Start custody at truck, rail or vessel</small></span><ArrowUpRight size={15} /></button>
        <button className="quick-action" onClick={() => onNavigate("yard")}><div className="quick-icon quick-blue"><Warehouse size={17} /></div><span><strong>Allocate a yard slot</strong><small>Use category-matched suggestions</small></span><ArrowUpRight size={15} /></button>
        <button className="quick-action" onClick={() => onNavigate("billing")}><div className="quick-icon quick-orange"><FileText size={17} /></div><span><strong>Review billing</strong><small>Tariff versions and invoice snapshots</small></span><ArrowUpRight size={15} /></button>
        <div className="mini-callout"><ShieldCheck size={15} /><span>Custody events and billing snapshots are recorded with an audit trail.</span></div>
      </section>
      <section className="panel vessel-panel"><div className="panel-heading"><div><span className="eyebrow">MANUAL SCHEDULE</span><h2>Vessel calls</h2></div><button className="text-button" onClick={() => onNavigate("vessels")}>Open schedule <ArrowUpRight size={14} /></button></div>
        {upcoming.map((vessel) => <div className="vessel-row" key={vessel.id}><div className="vessel-icon"><Ship size={16} /></div><div className="vessel-meta"><strong>{vessel.vessel_name}</strong><span>{vessel.voyage_number} · {vessel.berth || "Berth pending"}</span></div><div className="vessel-eta"><small>ETA</small><strong>{dateOnly(vessel.eta)}</strong></div></div>)}
        {!upcoming.length && <EmptyInline title="No vessel calls scheduled" detail="Add a manual vessel call to begin planning." onClick={() => onNavigate("vessels")} />}
      </section>
      <section className="panel operations-note"><div className="note-icon"><Activity size={18} /></div><div><span className="eyebrow">OPERATIONAL RECORD</span><h2>{summary?.released_today ?? 0} release events today</h2><p>Truck gate-out, rail dispatch and vessel loading handovers are captured through one custody flow.</p></div><button className="text-button" onClick={() => onNavigate("containers")}>Open visits <ArrowUpRight size={14} /></button></section>
    </div>
  </>;
}

function MetricCard({ label, value, detail, icon: Icon, accent, onClick }: { label: string; value?: number | string; detail: string; icon: LucideIcon; accent: string; onClick?: () => void }) {
  const content = <><div className="metric-top"><span>{label}</span><span className="metric-icon"><Icon size={17} /></span></div><strong className="metric-value">{value ?? "—"}</strong><span className="metric-detail">{detail}</span>{onClick && <span className="metric-arrow"><ArrowUpRight size={15} /></span>}</>;
  return onClick ? <button className={`metric-card metric-${accent}`} onClick={onClick}>{content}</button> : <div className={`metric-card metric-${accent}`}>{content}</div>;
}

function ContainersView({ rows, search, setSearch, onRegister, onWalkIn, onCreateFirstVisit, onReceive, onRelease, onAllocate, onNavigate }: { rows: { visit: Visit; container?: Container; customer?: Customer }[]; search: string; setSearch: (value: string) => void; onRegister: () => void; onWalkIn: () => void; onCreateFirstVisit: () => void; onReceive: (visit: Visit) => void; onRelease: (visit: Visit) => void; onAllocate: (visit: Visit) => void; onNavigate: (screen: Screen) => void }) {
  return <>
    <PageTitle eyebrow="OPERATIONS / CONTAINER REGISTER" title="Container visits" subtitle="Follow each container from custody receipt through terminal movement to release." actions={<><button className="secondary-button" onClick={onRegister}><Plus size={16} /> Register container</button><button className="primary-button" onClick={onWalkIn}><Truck size={16} /> New walk-in</button></>} />
    <div className="summary-inline"><div><span className="summary-number">{rows.length}</span><span>visits shown</span></div><div className="summary-divider" /><div><span className="summary-number">{rows.filter((row) => row.visit.status === "in_terminal").length}</span><span>in custody</span></div><div className="summary-divider" /><div><span className="summary-number">{rows.filter((row) => row.visit.status === "expected").length}</span><span>expected</span></div><div className="summary-spacer" /><div className="search-control"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search containers or customers" /></div></div>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">VISIT LEDGER</span><h2>Movement and custody timeline</h2></div><span className="panel-kicker">{rows.length} RECORDS</span></div>
      <div className="table-wrap"><table><thead><tr><th>CONTAINER / VISIT</th><th>CUSTOMER</th><th>ROUTE</th><th>CUSTODY</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{rows.map(({ visit, container, customer }) => <tr key={visit.id}><td><div className="container-cell"><span className="container-glyph"><ContainerIcon size={14} /></span><div><strong>{container?.container_number ?? "—"}</strong><small>{visit.visit_reference} · {container?.size_feet ?? "—"} ft · {container?.category ?? "—"}</small></div></div></td><td><div className="table-primary">{customer?.name ?? "—"}</div>{container?.is_empty && <span className="table-subtle">Empty unit</span>}</td><td><span className="direction-label">{visit.direction === "import" ? <ArrowDownLeft size={13} /> : <ArrowUpRight size={13} />}{visit.direction}</span>{visit.is_transshipment && <span className="table-subtle">Transshipment</span>}</td><td><span className="table-primary">{visit.entry_mode ? visit.entry_mode : "Awaiting receipt"}</span><span className="table-subtle">{dateTime(visit.custody_received_at)}</span></td><td><Badge tone={visit.status === "in_terminal" ? "green" : visit.status === "released" ? "blue" : "amber"}>{visit.status.replaceAll("_", " ")}</Badge></td><td><VisitActions visit={visit} onReceive={onReceive} onRelease={onRelease} onAllocate={onAllocate} /></td></tr>)}{!rows.length && <EmptyTable columns={6} title="No container visits yet" detail="Choose an already registered container to create its first visit, or use New walk-in to register and receive one together." action={<button className="primary-button button-small" onClick={onCreateFirstVisit}><Plus size={14} /> Create first visit</button>} />}</tbody></table></div>
    </section>
    <div className="support-card"><div className="support-icon"><MapPin size={17} /></div><div><strong>Custody supported across three modes</strong><span>Truck gate-in, rail receipt and vessel discharge can start a visit. Release supports truck, rail and vessel handover.</span></div><button className="text-button" onClick={() => onNavigate("gate")}>Gate operations <ArrowUpRight size={14} /></button></div>
  </>;
}

function VisitActions({ visit, onReceive, onRelease, onAllocate }: { visit: Visit; onReceive: (visit: Visit) => void; onRelease: (visit: Visit) => void; onAllocate: (visit: Visit) => void }) {
  return <div className="row-actions">{visit.status === "expected" && <button className="text-button" onClick={() => onReceive(visit)}>Receive</button>}{visit.status === "in_terminal" && !visit.yard_slot_id && <button className="text-button" onClick={() => onAllocate(visit)}>Allocate</button>}{visit.status === "in_terminal" && <button className="text-button text-danger" onClick={() => onRelease(visit)}>Release</button>}{visit.status === "released" && <span className="table-subtle">{visit.release_mode?.replaceAll("_", " ") ?? "Released"}</span>}</div>;
}

function GateView({ appointments, rows, customers, onWalkIn, onAppointment, onReceive, onRelease, onAllocate }: { appointments: Appointment[]; rows: { visit: Visit; container?: Container; customer?: Customer }[]; customers: Customer[]; onWalkIn: () => void; onAppointment: () => void; onReceive: (visit: Visit) => void; onRelease: (visit: Visit) => void; onAllocate: (visit: Visit) => void }) {
  const expected = rows.filter(({ visit }) => visit.status === "expected");
  const inTerminal = rows.filter(({ visit }) => visit.status === "in_terminal");
  return <>
    <PageTitle eyebrow="OPERATIONS / GATE" title="Gate & transport" subtitle="Coordinate walk-in traffic and appointment-ready gate activity." actions={<><button className="secondary-button" onClick={onAppointment}><CalendarDays size={16} /> Schedule visit</button><button className="primary-button" onClick={onWalkIn}><Plus size={16} /> Record walk-in</button></>} />
    <div className="metric-grid metric-grid-three"><MetricCard label="Awaiting custody" value={expected.length} detail="Expected visits" icon={Clock3} accent="amber" /><MetricCard label="Custody active" value={inTerminal.length} detail="Inside the terminal" icon={Truck} accent="teal" /><MetricCard label="Customers" value={customers.length} detail="Assigned to this terminal" icon={Users} accent="blue" /></div>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">APPOINTMENT REGISTER</span><h2>Scheduled gate visits</h2></div><span className="panel-kicker">{appointments.length} APPOINTMENTS</span></div><div className="table-wrap"><table><thead><tr><th>REFERENCE</th><th>VEHICLE</th><th>CUSTOMER</th><th>PLANNED ARRIVAL</th><th>STATUS</th></tr></thead><tbody>{appointments.map((appointment) => <tr key={appointment.id}><td><div className="table-primary">{appointment.reference}</div></td><td>{appointment.vehicle_number}</td><td>{customers.find((customer) => customer.id === appointment.customer_id)?.name ?? "Assigned customer"}</td><td>{dateTime(appointment.planned_at)}</td><td><Badge tone={appointment.status === "arrived" ? "green" : "blue"}>{appointment.status}</Badge></td></tr>)}{!appointments.length && <EmptyTable columns={5} title="No appointments scheduled" detail="Appointments appear here after you schedule a vehicle visit." action={<button className="secondary-button button-small" onClick={onAppointment}><CalendarDays size={13} /> Schedule appointment</button>} />}</tbody></table></div></section>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">GATE QUEUE</span><h2>Upcoming and active container visits</h2></div><span className="panel-kicker">{rows.length} VISITS</span></div><div className="table-wrap"><table><thead><tr><th>CONTAINER / VISIT</th><th>ENTRY ROUTE</th><th>RECEIVED AT</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{rows.slice(0, 50).map(({ visit, container }) => <tr key={visit.id}><td><div className="container-cell"><span className="container-glyph"><ContainerIcon size={14} /></span><div><strong>{container?.container_number ?? "—"}</strong><small>{visit.visit_reference}</small></div></div></td><td>{visit.entry_mode ?? "Scheduled arrival"}</td><td>{dateTime(visit.custody_received_at)}</td><td><Badge tone={visit.status === "in_terminal" ? "green" : visit.status === "released" ? "blue" : "amber"}>{visit.status.replaceAll("_", " ")}</Badge></td><td><VisitActions visit={visit} onReceive={onReceive} onRelease={onRelease} onAllocate={onAllocate} /></td></tr>)}{!rows.length && <EmptyTable columns={5} title="Gate is clear" detail="Schedule an appointment or record a walk-in to begin." action={<button className="primary-button button-small" onClick={onWalkIn}><Plus size={14} /> Record a walk-in</button>} />}</tbody></table></div></section>
    <div className="integration-note"><CalendarDays size={16} /><span><strong>Appointment flow ready.</strong> Provider, vehicle, driver and live gate-device integrations are not connected in this MVP.</span></div>
  </>;
}

function YardView({ slots, visits, canManage, onAddSlot, onAllocate }: { slots: YardSlot[]; visits: { visit: Visit; container?: Container; customer?: Customer }[]; canManage: boolean; onAddSlot: () => void; onAllocate: (visit: Visit) => void }) {
  const active = visits.filter(({ visit }) => visit.status === "in_terminal");
  const blocks = [...new Set(slots.map((slot) => slot.block))];
  return <>
    <PageTitle eyebrow="OPERATIONS / YARD" title="Yard plan" subtitle="View structured slot occupancy and apply compatible allocation suggestions." actions={canManage ? <button className="primary-button" onClick={onAddSlot}><Plus size={16} /> Add yard slot</button> : <span className="readonly-pill"><ShieldCheck size={14} /> Slot layout from terminal setup</span>} />
    <div className="yard-summary"><div><span className="yard-summary-label">SLOTS</span><strong>{slots.length}</strong></div><div><span className="yard-summary-label">OCCUPIED</span><strong>{slots.filter((slot) => slot.occupied).length}</strong></div><div><span className="yard-summary-label">CLEAR</span><strong>{slots.filter((slot) => !slot.occupied && !slot.blocked).length}</strong></div><div className="yard-legend"><span><i className="legend-square legend-clear" /> Available</span><span><i className="legend-square legend-occupied" /> Occupied</span><span><i className="legend-square legend-blocked" /> Blocked</span></div></div>
    {slots.length ? <div className="yard-grid">{blocks.map((block) => <section className="panel block-panel" key={block}><div className="block-title"><div><span className="eyebrow">YARD BLOCK</span><h2>{block}</h2></div><span className="panel-kicker">{slots.filter((slot) => slot.block === block).length} POSITIONS</span></div><div className="slot-grid">{slots.filter((slot) => slot.block === block).map((slot) => <div key={slot.id} className={`slot-tile ${slot.blocked ? "slot-blocked" : slot.occupied ? "slot-occupied" : "slot-clear"}`} title={slot.current_container_number ? `${slot.current_container_number} · ${slot.code}` : `${slot.code} · ${slot.container_category}`}><span>{slot.code}</span><small>{slot.current_container_number ?? slot.container_category}</small></div>)}</div></section>)}</div> : <section className="panel data-panel"><div className="empty-state"><div className="empty-icon"><Warehouse size={20} /></div><strong>No yard slots configured for this terminal</strong><span>Add the terminal’s real block and position codes. Compatible clear slots will then appear in allocation suggestions.</span>{canManage && <button className="primary-button button-small" onClick={onAddSlot}><Plus size={14} /> Configure first slot</button>}</div></section>}
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">ACTIVE CUSTODY</span><h2>Unallocated container visits</h2></div><span className="panel-kicker">{active.filter(({ visit }) => !visit.yard_slot_id).length} TO PLACE</span></div><div className="allocation-list">{active.filter(({ visit }) => !visit.yard_slot_id).map(({ visit, container, customer }) => <div className="allocation-row" key={visit.id}><span className="container-glyph"><ContainerIcon size={14} /></span><div className="allocation-meta"><strong>{container?.container_number ?? "—"}</strong><span>{customer?.name ?? "—"} · {container?.category ?? "—"} · {visit.visit_reference}</span></div><button className="secondary-button button-small" onClick={() => onAllocate(visit)}>Suggest slot <ArrowUpRight size={14} /></button></div>)}{!active.filter(({ visit }) => !visit.yard_slot_id).length && <EmptyInline title="No unallocated visits" detail="All in-custody visits have a yard slot, or the yard is empty." />}</div></section>
    <div className="integration-note"><Warehouse size={16} /><span><strong>Rule-based smart assist.</strong> Suggestions rank clear slots by compatible container category. Connect equipment telemetry and verified yard constraints before production use.</span></div>
  </>;
}

function VesselsView({ vessels, visits, onAdd }: { vessels: VesselCall[]; visits: { visit: Visit; container?: Container; customer?: Customer }[]; onAdd: () => void }) {
  return <>
    <PageTitle eyebrow="OPERATIONS / VESSEL PLAN" title="Vessel calls" subtitle="Maintain a manual schedule of vessel arrivals, berth assignments and connected visits." actions={<button className="primary-button" onClick={onAdd}><Plus size={16} /> Add vessel call</button>} />
    <div className="vessel-cards">{vessels.map((vessel) => <div className="vessel-card" key={vessel.id}><div className="vessel-card-top"><div className="vessel-icon vessel-icon-large"><Ship size={20} /></div><Badge tone="blue">{vessel.status}</Badge></div><h2>{vessel.vessel_name}</h2><p>Voyage {vessel.voyage_number}{vessel.imo_number ? ` · IMO ${vessel.imo_number}` : ""}</p><div className="vessel-card-divider" /><div className="vessel-card-stats"><div><small>ETA</small><strong>{dateTime(vessel.eta)}</strong></div><div><small>ETD</small><strong>{dateTime(vessel.etd)}</strong></div><div><small>BERTH</small><strong>{vessel.berth || "Unassigned"}</strong></div></div><span className="vessel-card-foot">{visits.filter(({ visit }) => visit.vessel_call_id === vessel.id).length} linked container visits</span></div>)}{!vessels.length && <EmptyCard title="No vessel calls yet" detail="Add a manual vessel schedule to coordinate upcoming discharge and loading." action={<button className="primary-button button-small" onClick={onAdd}><Plus size={14} /> Add vessel</button>} />}</div>
    <div className="integration-note"><Ship size={16} /><span><strong>Manual schedule only.</strong> AIS, carrier schedules, berth planning and port-community-system connections require external credentials and validation.</span></div>
  </>;
}

function BillingView({ tariffs, invoices, visits, onNewTariff, onPublish, onGenerate, onViewInvoice }: { tariffs: Tariff[]; invoices: Invoice[]; visits: Visit[]; onNewTariff: () => void; onPublish: (id: string) => void; onGenerate: (id: string) => void; onViewInvoice: (id: string) => void }) {
  const invoicedVisits = new Set(invoices.flatMap((invoice) => invoice.visit_ids ?? []));
  const releasable = visits.filter((visit) => visit.status === "released" && !invoicedVisits.has(visit.id));
  const billingCandidates = releasable.map((visit) => {
    const receivedAt = visit.custody_received_at ? Date.parse(visit.custody_received_at) : Number.NaN;
    const applicableTariff = tariffs
      .filter((tariff) => {
        if (!tariff.published_at || !Number.isFinite(receivedAt)) return false;
        const effectiveFrom = Date.parse(tariff.effective_from);
        const effectiveTo = tariff.effective_to ? Date.parse(tariff.effective_to) : Number.POSITIVE_INFINITY;
        return Number.isFinite(effectiveFrom) && effectiveFrom <= receivedAt && effectiveTo >= receivedAt;
      })
      .sort((a, b) => Date.parse(b.effective_from) - Date.parse(a.effective_from))[0];
    return { visit, applicableTariff };
  });
  const eligibleVisits = billingCandidates.filter(({ applicableTariff }) => Boolean(applicableTariff));
  const blockedVisits = billingCandidates.filter(({ applicableTariff }) => !applicableTariff);
  const issuedTotal = invoices.reduce((total, invoice) => total + Number(invoice.total), 0);
  return <>
    <PageTitle eyebrow="MANAGEMENT / FINANCE" title="Operational billing" subtitle="Published tariff versions feed immutable, INR-denominated operational invoice snapshots." actions={<button className="primary-button" onClick={onNewTariff}><Plus size={16} /> New tariff version</button>} />
    <div className="metric-grid metric-grid-three"><MetricCard label="Issued invoices" value={invoices.length} detail="Terminal operation invoices" icon={FileText} accent="blue" /><div className="metric-card metric-green"><div className="metric-top"><span>Issued total</span><span className="metric-icon"><CircleDollarSign size={17} /></span></div><strong className="metric-value money-value">{money(issuedTotal)}</strong><span className="metric-detail">From invoice records</span></div><MetricCard label="Published tariffs" value={tariffs.filter((tariff) => tariff.published_at).length} detail="Immutable published versions" icon={ShieldCheck} accent="teal" /></div>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">TERMINAL RATES</span><h2>Tariff versions</h2></div><span className="panel-kicker">CALENDAR-DAY STORAGE</span></div><div className="table-wrap"><table><thead><tr><th>NAME / VERSION</th><th>FREE DAYS</th><th>DAILY RATE</th><th>EFFECTIVE FROM</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{tariffs.map((tariff) => <tr key={tariff.id}><td><div className="table-primary">{tariff.name}</div><span className="table-subtle">Version {tariff.version_number}</span></td><td>{tariff.free_storage_days} days</td><td>{money(tariff.daily_rate)}</td><td>{dateOnly(tariff.effective_from)}</td><td>{tariff.published_at ? <Badge tone="green">Published</Badge> : <Badge tone="amber">Draft</Badge>}</td><td>{tariff.published_at ? <span className="table-subtle">Locked</span> : <button className="text-button" onClick={() => onPublish(tariff.id)}>Publish</button>}</td></tr>)}{!tariffs.length && <EmptyTable columns={6} title="No tariffs configured" detail="Create a draft tariff, review the free period and publish the version." action={<button className="primary-button button-small" onClick={onNewTariff}><Plus size={14} /> Create tariff</button>} />}</tbody></table></div></section>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">CUSTOMER BILLING</span><h2>Operational invoices</h2></div><span className="panel-kicker">PORTFLOW SUBSCRIPTION INVOICES ARE SEPARATE</span></div><div className="table-wrap"><table><thead><tr><th>INVOICE</th><th>ISSUED</th><th>CHARGES</th><th>TAX</th><th>TOTAL</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{invoices.map((invoice) => <tr key={invoice.id}><td><div className="table-primary">{invoice.invoice_number}</div><span className="table-subtle">Terminal operations</span></td><td>{dateOnly(invoice.issued_at)}</td><td>{money(invoice.subtotal)}</td><td>{money(invoice.tax_total)}</td><td><strong>{money(invoice.total)}</strong></td><td><Badge tone={invoice.status === "paid" ? "green" : "amber"}>{invoice.status}</Badge></td><td><button className="text-button" onClick={() => onViewInvoice(invoice.id)}>View details</button></td></tr>)}{!invoices.length && <EmptyTable columns={7} title="No operational invoices" detail="Invoices are created from released visits using a published tariff." />}</tbody></table></div>{releasable.length > 0 && <div className="invoice-queue"><div><strong>{releasable.length} released visit{releasable.length === 1 ? "" : "s"} without an invoice</strong><span>{eligibleVisits.length} eligible for billing · {blockedVisits.length} blocked by tariff/date validation.</span></div>{eligibleVisits.slice(0, 4).map(({ visit, applicableTariff }) => <div key={visit.id}><button className="button-small secondary-button" onClick={() => onGenerate(visit.id)}>Generate {visit.visit_reference}</button><span className="table-subtle"> {applicableTariff?.name} · {money(applicableTariff?.daily_rate)}/day</span></div>)}{blockedVisits.slice(0, 4).map(({ visit }) => <div className="billing-note" key={visit.id}><ShieldCheck size={15} /><span><strong>{visit.visit_reference} — generation unavailable.</strong> No published tariff covers this visit's custody receipt date ({dateOnly(visit.custody_received_at)}). Verify the approved tariff history; no rate has been assumed.</span></div>)}</div>}</section>
    <div className="billing-note"><ShieldCheck size={16} /><span>Invoice lines snapshot the tariff version and calendar-day calculation. Tax is not configured in this MVP. No PortFlow subscription payments are processed.</span></div>
  </>;
}

function CustomersView({ customers, visitRows, portalRequests, canManagePortal, onAdd, onApproveRequest, onRejectRequest, onCreatePortalLogin }: { customers: Customer[]; visitRows: { visit: Visit; container?: Container; customer?: Customer }[]; portalRequests: CustomerPortalAccessRequest[]; canManagePortal: boolean; onAdd: () => void; onApproveRequest: (request: CustomerPortalAccessRequest) => void; onRejectRequest: (requestId: string) => void; onCreatePortalLogin: (customer: Customer) => void }) {
  return <>
    <PageTitle eyebrow="MANAGEMENT / CUSTOMER ACCOUNTS" title="Customer visibility" subtitle="Customer organizations see only their assigned container visits and operational invoices." actions={<><span className="readonly-pill"><ShieldCheck size={14} /> Tenant and customer scoped</span><button className="primary-button" onClick={onAdd}><Plus size={16} /> Add customer</button></>} />
    {canManagePortal && portalRequests.length > 0 && <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">CUSTOMER ONBOARDING</span><h2>Pending portal access requests</h2></div><Badge tone="amber">{portalRequests.length} waiting</Badge></div><div className="table-wrap"><table><thead><tr><th>COMPANY / CONTACT</th><th>REQUEST</th><th>RECEIVED</th><th>ACTION</th></tr></thead><tbody>{portalRequests.map((request) => <tr key={request.id}><td><div className="table-primary">{request.company_name}</div><span className="table-subtle">{request.contact_name} · {request.email}</span></td><td>{request.message || "Customer portal access"}</td><td>{dateTime(request.created_at)}</td><td><div className="table-actions"><button className="primary-button button-small" onClick={() => onApproveRequest(request)}>Review & grant</button><button className="text-button" onClick={() => onRejectRequest(request.id)}>Decline</button></div></td></tr>)}</tbody></table></div></section>}
    <div className="customer-grid">{customers.map((customer) => {
      const customerVisits = visitRows.filter((row) => row.customer?.id === customer.id);
      return <section className="panel customer-card" key={customer.id}><div className="customer-card-top"><div className="customer-avatar">{initials(customer.name)}</div><Badge tone="green">Active</Badge></div><h2>{customer.name}</h2><p>{customer.code}</p><div className="customer-stats"><div><strong>{customerVisits.length}</strong><span>Visits</span></div><div><strong>{customerVisits.filter(({ visit }) => visit.status === "in_terminal").length}</strong><span>In custody</span></div><div><strong>{customerVisits.filter(({ visit }) => visit.status === "released").length}</strong><span>Released</span></div></div><div className="customer-email">{customer.email || "No portal email assigned"}</div>{canManagePortal && <button className="secondary-button button-small" onClick={() => onCreatePortalLogin(customer)}>Create portal login <ArrowUpRight size={14} /></button>}</section>;
    })}{!customers.length && <EmptyCard title="No customer accounts" detail="Add customers through the API or load the clearly labeled demo seed." />}</div>
    <div className="integration-note"><Users size={16} /><span><strong>Customer onboarding.</strong> Visitors can request access from the sign-in page. Requests appear here for organization admins; email notifications are not configured, so contact the customer directly after approving.</span></div>
  </>;
}

function PortalView({ rows, invoices }: { rows: Record<string, unknown>[]; invoices: Invoice[] }) {
  return <>
    <PageTitle eyebrow="CUSTOMER SPACE / CONTAINER VISIBILITY" title="Your terminal activity" subtitle="Track custody status, yard location and issued operational invoices for your assigned customer account." actions={<span className="readonly-pill"><ShieldCheck size={14} /> Customer-scoped access</span>} />
    <div className="metric-grid metric-grid-three"><MetricCard label="Container visits" value={rows.length} detail="Assigned to your company" icon={ContainerIcon} accent="teal" /><MetricCard label="In terminal" value={rows.filter((row) => row.status === "in_terminal").length} detail="Current custody" icon={Warehouse} accent="blue" /><MetricCard label="Invoices" value={invoices.length} detail="Operational billing only" icon={FileText} accent="purple" /></div>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">CONTAINER TRACKING</span><h2>Visit status</h2></div><span className="panel-kicker">LIVE FROM THE TERMINAL RECORD</span></div><div className="table-wrap"><table><thead><tr><th>CONTAINER</th><th>VISIT</th><th>DIRECTION</th><th>YARD LOCATION</th><th>LAST CUSTODY EVENT</th><th>STATUS</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${String(row.visit_reference)}-${index}`}><td><div className="container-cell"><span className="container-glyph"><ContainerIcon size={14} /></span><div><strong>{String(row.container_number)}</strong><small>{String(row.category)}{row.is_empty ? " · Empty" : ""}</small></div></div></td><td>{String(row.visit_reference)}</td><td>{String(row.direction)}</td><td>{row.yard_slot ? String(row.yard_slot) : "—"}</td><td>{dateTime(row.released_at as string | null) !== "—" ? dateTime(row.released_at as string) : dateTime(row.received_at as string | null)}</td><td><Badge tone={row.status === "in_terminal" ? "green" : row.status === "released" ? "blue" : "amber"}>{String(row.status).replaceAll("_", " ")}</Badge></td></tr>)}{!rows.length && <EmptyTable columns={6} title="No container activity yet" detail="Once your terminal records a visit for your account, it will appear here." />}</tbody></table></div></section>
    <CustomerBilling invoices={invoices} />
  </>;
}

function InvoiceDetailModal({ invoice, onClose }: { invoice: InvoiceDetail; onClose: () => void }) {
  const snapshot = invoice.snapshot ?? {};
  const value = (key: string) => {
    const item = snapshot[key];
    return item === null || item === undefined || item === "" ? "—" : String(item);
  };
  const visitReference = value("visit_reference");
  const containerNumber = value("container_number");
  const tariffName = value("tariff_name");
  const tariffVersion = value("tariff_version_number");
  const linkedVisit = invoice.visit_ids?.[0] ?? invoice.lines?.[0]?.visit_id;
  return <ModalFrame title={`Invoice · ${invoice.invoice_number}`} onClose={onClose}>
    <div className="modal-form">
      <div className="metric-grid metric-grid-three">
        <MetricCard label="Subtotal" value={money(invoice.subtotal)} detail="Storage charges" icon={FileText} accent="blue" />
        <MetricCard label="Tax" value={money(invoice.tax_total)} detail="Tax configuration" icon={ShieldCheck} accent="teal" />
        <MetricCard label="Total" value={money(invoice.total)} detail={invoice.currency} icon={CircleDollarSign} accent="green" />
      </div>
      <div className="panel data-panel">
        <div className="panel-heading"><div><span className="eyebrow">INVOICE SNAPSHOT</span><h2>Visit and tariff details</h2></div><Badge tone={invoice.status === "paid" ? "green" : "amber"}>{invoice.status}</Badge></div>
        <div className="terminal-list">
          <div className="terminal-row"><div><strong>Visit reference</strong><span>{visitReference}</span></div></div>
          <div className="terminal-row"><div><strong>Container</strong><span>{containerNumber}</span></div></div>
          <div className="terminal-row"><div><strong>Tariff</strong><span>{tariffName}{tariffVersion !== "—" ? ` · Version ${tariffVersion}` : ""}</span></div></div>
          <div className="terminal-row"><div><strong>Custody received</strong><span>{dateTime(value("custody_received_at"))}</span></div></div>
          <div className="terminal-row"><div><strong>Custody released</strong><span>{dateTime(value("custody_released_at"))}</span></div></div>
          <div className="terminal-row"><div><strong>Terminal timezone</strong><span>{value("timezone")}</span></div></div>
          <div className="terminal-row"><div><strong>Calendar days</strong><span>{value("calendar_days")}</span></div></div>
          <div className="terminal-row"><div><strong>Free storage days</strong><span>{value("free_storage_days")}</span></div></div>
          <div className="terminal-row"><div><strong>Billable days</strong><span>{value("billable_days")}</span></div></div>
          <div className="terminal-row"><div><strong>Daily rate</strong><span>{money(value("daily_rate_inr"))}</span></div></div>
        </div>
      </div>
      <div className="panel data-panel">
        <div className="panel-heading"><div><span className="eyebrow">CHARGE BREAKDOWN</span><h2>Invoice lines</h2></div></div>
        <div className="table-wrap"><table><thead><tr><th>DESCRIPTION</th><th>QTY</th><th>RATE</th><th>AMOUNT</th></tr></thead><tbody>{invoice.lines.map((line) => <tr key={line.id}><td><div className="table-primary">{line.description}</div><span className="table-subtle">{line.charge_type} · Visit {line.visit_id.slice(0, 8)}</span></td><td>{line.quantity}</td><td>{money(line.unit_rate)}</td><td><strong>{money(line.amount)}</strong></td></tr>)}{!invoice.lines.length && <EmptyTable columns={4} title="No invoice lines found" detail="This invoice has no linked charge lines. Check the saved invoice snapshot." />}</tbody></table></div>
      </div>
      {linkedVisit && <div className="billing-note"><ShieldCheck size={15} /><span>Linked visit ID: {linkedVisit}</span></div>}
      {invoice.total === "0.00" && <div className="billing-note"><ShieldCheck size={15} /><span>{value("billable_days") === "0" ? "Zero amount is consistent with the saved snapshot: all calendar days were within the free storage allowance." : "This invoice is zero-valued. Compare the saved line amount and snapshot before treating it as correct."}</span></div>}
      <div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>Close</button></div>
    </div>
  </ModalFrame>;
}

function CustomerBilling({ invoices }: { invoices: Invoice[] }) {
  return <section className="panel data-panel customer-invoices"><div className="panel-heading"><div><span className="eyebrow">OPERATIONAL BILLING</span><h2>Issued invoices</h2></div><span className="panel-kicker">INR</span></div><div className="table-wrap"><table><thead><tr><th>INVOICE</th><th>ISSUED</th><th>SUBTOTAL</th><th>TAX</th><th>TOTAL</th></tr></thead><tbody>{invoices.map((invoice) => <tr key={invoice.id}><td><div className="table-primary">{invoice.invoice_number}</div></td><td>{dateOnly(invoice.issued_at)}</td><td>{money(invoice.subtotal)}</td><td>{money(invoice.tax_total)}</td><td><strong>{money(invoice.total)}</strong></td></tr>)}{!invoices.length && <EmptyTable columns={5} title="No invoices issued" detail="New operational invoices will appear here after custody release and tariff calculation." />}</tbody></table></div></section>;
}

function SettingsView({ terminals, catalogCount, canImport, onAdd, onImport }: { terminals: Terminal[]; catalogCount: number; canImport: boolean; onAdd: () => void; onImport: () => void }) {
  return <>
    <PageTitle eyebrow="ORGANIZATION / SETUP" title="Organization setup" subtitle="Manage the terminals available to members of this organization." actions={<>{canImport && <button className="secondary-button" onClick={onImport}><MapPin size={16} /> Add Asian major ports</button>}<button className="primary-button" onClick={onAdd}><Plus size={16} /> Add terminal</button></>} />
    {canImport && <div className="billing-note port-import-note"><Globe2 size={16} /><span>Curated directory: {catalogCount} major commercial ports across Asia, with local time zones. Import skips existing terminals and keeps them unchanged.</span></div>}
    <div className="setup-grid"><section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">TERMINAL NETWORK</span><h2>Configured terminals</h2></div><span className="panel-kicker">{terminals.length} LOCATIONS</span></div><div className="terminal-list">{terminals.map((terminal) => <div className="terminal-row" key={terminal.id}><div className="terminal-pin"><MapPin size={17} /></div><div><strong>{terminal.name}</strong><span>{terminal.code} · {terminal.timezone}</span>{terminal.address && <small>{terminal.address}</small>}</div><Badge tone="green">Active</Badge></div>)}{!terminals.length && <EmptyInline title="No terminal configured" detail="Create a terminal location to set up yard, gate and billing operations." />}</div></section>
      <section className="panel security-panel"><div className="security-icon"><ShieldCheck size={20} /></div><span className="eyebrow">SECURITY BASELINE</span><h2>Server-verified tenant access</h2><p>Each request resolves an active membership and sets tenant context for the database transaction. PostgreSQL RLS policies fail closed when that context is absent.</p><div className="security-check"><Check size={15} /><span>Email and password sign-in · authenticator disabled</span></div><div className="security-check"><Check size={15} /><span>Argon2id password hashes</span></div><div className="security-check"><Check size={15} /><span>Terminal-scoped staff access</span></div><div className="security-check"><Check size={15} /><span>Audit records for operational actions</span></div><span className="security-footnote">This demo uses password-only sign-in. Do not use it for real operational data; production should add MFA, non-owner database credentials, TLS, backups and key rotation.</span></section></div>
  </>;
}

function LocationsView({ catalog, rows }: { catalog: PortCatalogEntry[]; rows: LiveContainerLocation[] }) {
  const [search, setSearch] = useState("");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, []);
  const term = search.trim().toLowerCase();
  const ports = catalog.filter((port) => !term || [port.name, port.city, port.country, port.region].some((value) => value.toLowerCase().includes(term)));
  const formatPortTime = (timezone: string) => {
    try { return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: timezone }).format(now); }
    catch { return "Time zone unavailable"; }
  };
  return <>
    <PageTitle eyebrow="LOCATIONS / CONTAINER MOVEMENT" title="Port & container locations" subtitle="See the latest recorded terminal location and local time for ports in the Asian commercial directory." actions={<span className="readonly-pill"><Clock3 size={14} /> Port-local times</span>} />
    <div className="billing-note location-limitation"><Activity size={16} /><span>Container positions come from the latest gate and yard records. GPS/AIS tracking is not connected, so updates depend on terminal staff recording movements.</span></div>
    <section className="panel data-panel location-panel"><div className="panel-heading"><div><span className="eyebrow">LATEST OPERATIONAL RECORD</span><h2>Container locations</h2></div><span className="panel-kicker">{rows.length} CONTAINERS</span></div><div className="table-wrap"><table><thead><tr><th>CONTAINER / CUSTOMER</th><th>PORT / TERMINAL</th><th>RECORDED LOCATION</th><th>STATUS</th><th>LAST UPDATED</th></tr></thead><tbody>{rows.map((row) => <tr key={row.visit_id}><td><div className="container-cell"><span className="container-glyph"><ContainerIcon size={14} /></span><div><strong>{row.container_number}</strong><small>{row.customer_name}</small></div></div></td><td><div className="table-primary">{row.port_name}</div><span className="table-subtle">{row.port_address || "Address not set"}</span></td><td>{row.current_location}</td><td><Badge tone={row.status === "in_terminal" ? "green" : row.status === "released" ? "blue" : "amber"}>{row.status.replaceAll("_", " ")}</Badge></td><td><div className="table-primary">{dateTime(row.last_updated_at)}</div><span className="table-subtle">{formatPortTime(row.timezone)}</span></td></tr>)}{!rows.length && <EmptyTable columns={5} title="No container location records" detail="Once a visit is recorded for this terminal, its latest gate or yard location will appear here." />}</tbody></table></div></section>
    <section className="panel data-panel port-directory"><div className="panel-heading"><div><span className="eyebrow">ASIA / MAJOR COMMERCIAL PORTS</span><h2>Port directory</h2></div><span className="panel-kicker">{ports.length} OF {catalog.length}</span></div><div className="summary-inline"><div className="search-control"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search port, city or country" /></div></div><div className="port-grid">{ports.map((port) => <article className="port-card" key={port.code}><div className="port-card-icon"><MapPin size={16} /></div><div className="port-card-main"><strong>{port.name}</strong><span>{port.city}, {port.country}</span></div><div className="port-card-time"><small>{port.region} · {port.timezone}</small><strong>{formatPortTime(port.timezone)}</strong></div></article>)}{!ports.length && <EmptyInline title="No matching ports" detail="Try another port, city, or country name." />}</div></section>
  </>;
}

function ContactView({ isAdmin, organizationSlug, requests, onResolve, onSubmit }: {
  isAdmin: boolean;
  organizationSlug: string;
  requests: ContactInquiry[];
  onResolve: (requestId: string) => void;
  onSubmit: (payload: { organization_slug: string; contact_name: string; email: string; subject: string; message: string }) => void;
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    onSubmit({
      organization_slug: organizationSlug,
      contact_name: String(form.get("contact_name")).trim(),
      email: String(form.get("email")).trim(),
      subject: String(form.get("subject")).trim(),
      message: String(form.get("message")).trim(),
    });
  };
  if (isAdmin) return <>
    <PageTitle eyebrow="MANAGEMENT / CUSTOMER MESSAGES" title="Contact inbox" subtitle="Messages sent by visitors and customer accounts are stored here for administrator review." actions={<span className="readonly-pill"><Mail size={14} /> {requests.length} open</span>} />
    <div className="billing-note"><ShieldCheck size={16} /><span>Requests are visible in this inbox. Email sending and automatic email alerts are not configured.</span></div>
    <section className="panel data-panel"><div className="panel-heading"><div><span className="eyebrow">ORGANIZATION INBOX</span><h2>Open messages</h2></div><span className="panel-kicker">{requests.length} OPEN</span></div><div className="table-wrap"><table><thead><tr><th>CONTACT</th><th>SUBJECT / MESSAGE</th><th>RECEIVED</th><th>ACTION</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td><div className="table-primary">{request.contact_name}</div><span className="table-subtle">{request.email}</span></td><td><div className="table-primary">{request.subject}</div><span className="table-subtle contact-message-text">{request.message}</span></td><td>{dateTime(request.created_at)}</td><td><button className="secondary-button button-small" onClick={() => onResolve(request.id)}><Check size={14} /> Mark resolved</button></td></tr>)}{!requests.length && <EmptyTable columns={4} title="Inbox is clear" detail="New contact requests will appear here for review." />}</tbody></table></div></section>
  </>;
  return <>
    <PageTitle eyebrow="CUSTOMER SUPPORT" title="Contact us" subtitle="Send a message to your PortFlow organization administrator." actions={<span className="readonly-pill"><ShieldCheck size={14} /> Private organization inbox</span>} />
    <div className="contact-form-layout"><section className="panel contact-form-panel"><div className="panel-heading"><div><span className="eyebrow">SEND A MESSAGE</span><h2>How can we help?</h2></div><span className="panel-kicker">{organizationSlug}</span></div><form className="form-stack workspace-contact-form" onSubmit={submit}>
      <Field label="Your name" name="contact_name" required minLength={2} maxLength={180} autoComplete="name" />
      <Field label="Email address" name="email" type="email" required autoComplete="email" />
      <Field label="Subject" name="subject" required minLength={2} maxLength={180} />
      <div className="field"><label htmlFor="workspace-contact-message">Message</label><textarea id="workspace-contact-message" name="message" rows={6} required minLength={5} maxLength={2000} placeholder="Write your message" /></div>
      <button className="primary-button"><Mail size={15} /> Send message</button>
    </form></section><aside className="panel contact-info-panel"><div className="security-icon"><Mail size={19} /></div><span className="eyebrow">IN-APP REQUEST</span><h2>Admin can review it here</h2><p>Your message is saved inside this organization’s PortFlow inbox. No message is emailed automatically.</p></aside></div>
  </>;
}

function PageTitle({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle: string; actions?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>{actions && <div className="heading-actions">{actions}</div>}</div>;
}

function EmptyTable({ columns, title, detail, action }: { columns: number; title: string; detail: string; action?: ReactNode }) {
  return <tr><td colSpan={columns}><div className="empty-state"><div className="empty-icon"><Boxes size={20} /></div><strong>{title}</strong><span>{detail}</span>{action}</div></td></tr>;
}

function EmptyInline({ title, detail, onClick }: { title: string; detail: string; onClick?: () => void }) {
  return <div className="empty-inline"><div className="empty-icon"><Ship size={18} /></div><strong>{title}</strong><span>{detail}</span>{onClick && <button className="text-button" onClick={onClick}>Get started <ArrowUpRight size={14} /></button>}</div>;
}

function EmptyCard({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="empty-card"><div className="empty-icon"><Boxes size={20} /></div><strong>{title}</strong><span>{detail}</span>{action}</div>;
}

function WorkspaceModal({ type, busy, terminals, customers, containers, vessels, selectedTerminal, selectedVisit, selectedCustomer, selectedPortalRequest, yardChoices, onClose, onSubmit }: {
  type: Exclude<ModalType, null>;
  busy: boolean;
  terminals: Terminal[];
  customers: Customer[];
  containers: Container[];
  vessels: VesselCall[];
  selectedTerminal: string;
  selectedVisit: Visit | null;
  selectedCustomer: Customer | null;
  selectedPortalRequest: CustomerPortalAccessRequest | null;
  yardChoices: { slot_id: string; code: string; score: number; reason: string }[];
  onClose: () => void;
  onSubmit: (type: Exclude<ModalType, null>, form: FormData) => Promise<void>;
}) {
  const [containerSearch, setContainerSearch] = useState("");
  const [selectedContainerId, setSelectedContainerId] = useState("");
  const titles: Record<Exclude<ModalType, null>, string> = { walkin: "Register a walk-in", visit: "Create first visit", appointment: "Schedule a gate visit", vessel: "Add vessel call", tariff: "Create tariff version", terminal: "Add terminal", "yard-slot": "Configure a yard slot", container: "Register container", customer: "Add customer account", "customer-login": "Create customer portal login", "portal-request": "Approve customer access", receive: "Record custody receipt", release: "Release custody", allocate: "Allocate yard slot" };
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); void onSubmit(type, new FormData(event.currentTarget)); };
  const terminalField = <div className="field"><label htmlFor="terminal_id">Terminal</label><select id="terminal_id" name="terminal_id" defaultValue={selectedTerminal} required>{terminals.map((terminal) => <option key={terminal.id} value={terminal.id}>{terminal.name}</option>)}</select></div>;
  const customerField = <div className="field"><label htmlFor="customer_id">Customer</label><select id="customer_id" name="customer_id" required defaultValue=""><option value="" disabled>Select a customer</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></div>;
  const terminalContainers = containers.filter((container) => container.terminal_id === selectedTerminal);
  const matchingContainers = terminalContainers.filter((container) => {
    const term = containerSearch.trim().toLowerCase();
    const customerName = customers.find((customer) => customer.id === container.customer_id)?.name ?? "";
    return !term || container.container_number.toLowerCase().includes(term) || customerName.toLowerCase().includes(term);
  });
  const categoryField = <div className="field"><label htmlFor="category">Container category</label><select name="category" id="category" defaultValue="DRY"><option>DRY</option><option>REEFER</option><option>HAZARDOUS</option><option>OPEN_TOP</option><option>FLAT_RACK</option></select></div>;
  const sizeField = <div className="field"><label htmlFor="size_feet">Size</label><select name="size_feet" id="size_feet" defaultValue="40"><option value="20">20 ft</option><option value="40">40 ft</option><option value="45">45 ft</option></select></div>;
  const checkbox = (name: string, label: string) => <label className="checkbox-field"><input type="checkbox" name={name} /><span>{label}</span></label>;
  const footer = <div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary-button" disabled={busy}>{busy ? <><span className="button-spinner" /> Saving…</> : <>{type === "customer-login" ? "Create login" : type === "portal-request" ? "Grant access" : "Save record"} <ArrowUpRight size={15} /></>}</button></div>;
  return <ModalFrame title={titles[type]} onClose={onClose}>
    {type === "allocate" ? <div className="yard-choice-list">{yardChoices.map((choice) => <form key={choice.slot_id} onSubmit={(event) => { event.preventDefault(); const data = new FormData(); data.set("slot_id", choice.slot_id); void onSubmit("allocate", data); }}><div><strong>{choice.code}</strong><span>{choice.reason}</span></div><Badge tone="green">Score {choice.score}</Badge><button className="secondary-button button-small" disabled={busy}>Assign <ArrowUpRight size={13} /></button></form>)}{!yardChoices.length && <div className="empty-inline"><strong>No clear compatible slot</strong><span>Clear a slot or review the category setup before allocating {selectedVisit?.visit_reference}.</span></div>}</div> : (
      <form className="modal-form" onSubmit={submit}>
        {(type === "walkin" || type === "appointment" || type === "vessel" || type === "tariff" || type === "terminal" || type === "yard-slot" || type === "container" || type === "customer") && terminalField}
        {(type === "walkin" || type === "appointment" || type === "container" || type === "portal-request") && customerField}
        {type === "visit" && <>
          <div className="form-hint"><ShieldCheck size={14} /> Select an already registered container for {terminals.find((terminal) => terminal.id === selectedTerminal)?.name ?? "this terminal"}. This creates a visit only; it does not register another container.</div>
          <div className="field"><label htmlFor="container_search">Search registered containers</label><input id="container_search" type="search" value={containerSearch} onChange={(event) => { setContainerSearch(event.target.value); setSelectedContainerId(""); }} placeholder="Container number or customer" /></div>
          <div className="field"><label htmlFor="container_id">Existing container</label><select id="container_id" name="container_id" value={selectedContainerId} onChange={(event) => setSelectedContainerId(event.target.value)} required><option value="" disabled>Select a container</option>{matchingContainers.map((container) => <option key={container.id} value={container.id}>{container.container_number} · {container.size_feet} ft · {customers.find((customer) => customer.id === container.customer_id)?.name ?? "Customer"}</option>)}</select>{!matchingContainers.length && <div className="form-hint">{terminalContainers.length ? "No registered containers match this search." : "No registered containers are available for this terminal yet."}</div>}</div>
          <div className="field"><label htmlFor="direction">Direction</label><select name="direction" id="direction" defaultValue="import"><option value="import">Import</option><option value="export">Export</option></select></div>
          <div className="field"><label htmlFor="vessel_call_id">Vessel call (optional)</label><select name="vessel_call_id" id="vessel_call_id" defaultValue=""><option value="">No vessel call linked</option>{vessels.map((vessel) => <option key={vessel.id} value={vessel.id}>{vessel.vessel_name} · {vessel.voyage_number}</option>)}</select></div>
          {checkbox("is_transshipment", "Transshipment visit · one SaaS usage count")}
        </>}
        {(type === "walkin" || type === "container") && <Field label="Container number" name="container_number" placeholder="ABCU1234567" minLength={11} maxLength={11} required />}
        {(type === "walkin" || type === "container") && <div className="form-row">{sizeField}{categoryField}</div>}
        {(type === "walkin" || type === "container") && checkbox("is_empty", "Empty container")}
        {type === "walkin" && <><div className="form-row"><div className="field"><label htmlFor="direction">Direction</label><select name="direction" id="direction"><option value="import">Import</option><option value="export">Export</option></select></div><div className="field"><label htmlFor="entry_mode">Custody receipt mode</label><select name="entry_mode" id="entry_mode"><option value="truck">Truck gate-in</option><option value="rail">Rail receipt</option><option value="vessel">Vessel discharge</option></select></div></div><div className="field"><label htmlFor="vessel_call_id">Vessel call (optional)</label><select name="vessel_call_id" id="vessel_call_id" defaultValue=""><option value="">No vessel call linked</option>{vessels.map((vessel) => <option key={vessel.id} value={vessel.id}>{vessel.vessel_name} · {vessel.voyage_number}</option>)}</select></div>{checkbox("is_transshipment", "Transshipment visit · one SaaS usage count")}</>}
        {type === "container" && <><Field label="Seal number" name="seal_number" placeholder="Optional" /><Field label="Cargo description" name="cargo_description" placeholder="Optional cargo summary" /></>}
        {type === "appointment" && <><Field label="Vehicle registration" name="vehicle_number" placeholder="MH 01 AB 1234" required /><Field label="Scheduled arrival" name="planned_at" type="datetime-local" required /><Field label="Notes" name="notes" placeholder="Optional visit notes" /></>}
        {type === "vessel" && <><Field label="Vessel name" name="vessel_name" placeholder="MV Sagar Horizon" required /><div className="form-row"><Field label="Voyage number" name="voyage_number" placeholder="SH-042" required /><Field label="IMO number" name="imo_number" placeholder="Optional" /></div><Field label="Berth" name="berth" placeholder="B-04" /><div className="form-row"><Field label="ETA" name="eta" type="datetime-local" /><Field label="ETD" name="etd" type="datetime-local" /></div></>}
        {type === "tariff" && <><Field label="Tariff name" name="name" placeholder="Standard storage · import" required /><div className="form-row"><Field label="Free calendar days" name="free_storage_days" type="number" placeholder="3" required minLength={0} /><Field label="Daily rate (INR)" name="daily_rate" type="number" placeholder="850.00" required minLength={0} /></div><Field label="Effective from" name="effective_from" type="datetime-local" required /><div className="form-hint"><ShieldCheck size={14} /> Publishing locks this version. Invoice snapshots preserve its rate and calculation.</div></>}
        {type === "terminal" && <><Field label="Terminal code" name="code" placeholder="MUM-02" required /><Field label="Terminal name" name="name" placeholder="North Yard Annex" required /><div className="field"><label htmlFor="timezone">Timezone</label><select name="timezone" id="timezone" defaultValue="Asia/Kolkata"><option value="Asia/Kolkata">Asia/Kolkata (IST)</option><option value="UTC">UTC</option></select></div><Field label="Address" name="address" placeholder="Optional terminal address" /></>}
        {type === "yard-slot" && <><div className="form-row"><Field label="Slot code" name="code" placeholder="A-01-01-01" required /><Field label="Block" name="block" placeholder="A" required /></div><div className="form-row"><Field label="Bay" name="bay" type="number" placeholder="1" min={1} required /><Field label="Row" name="row" type="number" placeholder="1" min={1} required /><Field label="Tier" name="tier" type="number" placeholder="1" min={1} required /></div><div className="form-row"><div className="field"><label htmlFor="container_category">Container category</label><select id="container_category" name="container_category" defaultValue="DRY"><option>DRY</option><option>REEFER</option><option>HAZARDOUS</option><option>OPEN_TOP</option><option>FLAT_RACK</option><option>GENERAL</option></select></div><Field label="Zone" name="zone" placeholder="GENERAL" defaultValue="GENERAL" /></div><div className="form-hint"><ShieldCheck size={14} /> Use your actual yard location code and coordinates. Only clear slots with a matching category or GENERAL can be assigned.</div></>}
        {type === "customer" && <><Field label="Customer code" name="code" placeholder="WSL-001" required /><Field label="Customer organization" name="name" placeholder="Western Star Logistics" required /><Field label="Portal email (optional)" name="email" type="email" placeholder="operations@customer.in" /></>}
        {type === "customer-login" && <><div className="form-hint"><ShieldCheck size={14} /> This sign-in will see only {selectedCustomer?.name ?? "this customer"}’s containers and invoices. Use the original website link and your organization slug to sign in.</div><Field label="Customer contact name" name="display_name" placeholder="Customer user" required autoComplete="name" /><Field label="Login email" name="email" type="email" placeholder={selectedCustomer?.email || "name@company.com"} required autoComplete="username" /><Field label="Password · 12 characters minimum" name="password" type="password" required minLength={12} autoComplete="new-password" /><div className="form-hint">Email invitations and password reset are not configured. Share the email and password privately with the customer.</div></>}
        {type === "portal-request" && <><div className="modal-context"><span className="container-glyph"><Users size={14} /></span><div><strong>{selectedPortalRequest?.company_name}</strong><span>{selectedPortalRequest?.contact_name} · {selectedPortalRequest?.email}</span></div></div><div className="form-hint"><ShieldCheck size={14} /> Link this request to the correct customer record. Set a password, then send the email, organization slug and password to the customer privately.</div><Field label="Password · 12 characters minimum" name="password" type="password" required minLength={12} autoComplete="new-password" /></>}
        {(type === "receive" || type === "release") && <><div className="modal-context"><span className="container-glyph"><ContainerIcon size={14} /></span><div><strong>{selectedVisit?.visit_reference}</strong><span>Container visit · {selectedVisit?.status.replaceAll("_", " ")}</span></div></div><div className="field"><label htmlFor="mode">Custody handover mode</label><select id="mode" name="mode" defaultValue={type === "receive" ? "truck" : "truck_gate_out"}>{type === "receive" ? <><option value="truck">Truck gate-in</option><option value="rail">Rail receipt</option><option value="vessel">Vessel discharge</option></> : <><option value="truck_gate_out">Truck gate-out</option><option value="rail_dispatch">Rail dispatch</option><option value="vessel_loading">Vessel loading / operational handover</option></>}</select></div><Field label="External reference (optional)" name="external_reference" placeholder="Gate ticket, manifest or dispatch reference" /><div className="form-hint"><ShieldCheck size={14} /> This event is appended to the custody record with an idempotency key.</div></>}
        {footer}
      </form>
    )}
  </ModalFrame>;
}

export default App;
