# PortFlow — PRD, Architecture, and Delivery Plan

## Product brief

PortFlow is an India-first, INR-billed, multi-tenant SaaS Terminal Operating System for terminal operators and logistics companies. This initial milestone is a local, runnable vertical slice for a single demo organization with multiple terminals. It supports staff operations and a customer-facing visibility view. It is a development MVP, not a production-ready commercial system.

### MVP capabilities

- Sign in with email and password; establish organization and terminal access from the authenticated user. Keep Google OAuth and MFA behind clearly documented provider interfaces; do not claim either is live until configured and tested.
- Create organizations, terminals, users, structured yard slots, vessels, containers, and container visits.
- Record immutable custody and movement events for truck, rail, and vessel handoffs. Custody release supports truck gate-out, rail dispatch, and vessel loading/operational handover.
- Allocate a container to an available yard slot with an explainable rule-based suggestion. Support manual vessel schedules, walk-in gate operations, and appointment-ready structures.
- Snapshot a published tariff version into operational charge and invoice lines. Calculate storage from custody receipt to custody release using calendar days and configurable free days. Keep operational invoices separate from PortFlow SaaS subscriptions.
- Count at most one idempotent SaaS usage event per container visit, including empty containers and transshipment visits.
- Expose scoped REST endpoints at `/api/v1`, OpenAPI docs, audit records, and a customer visibility view.

### Important scope boundaries

Import/export, customer portal visibility, transport providers, generated/uploaded documents, notification providers (email/SMS/WhatsApp), analytics, and payment provider integrations should have honest extension points. This milestone does not claim live GPS, live port integrations, payment processing, or regulatory approval.

## Architecture

- **Frontend:** React + TypeScript + Vite, responsive operator console and customer view.
- **Backend:** Python FastAPI modular monolith, versioned REST API at `/api/v1`, Pydantic schemas, SQLAlchemy 2, Alembic migrations.
- **Data:** PostgreSQL UUIDs, organization ownership on tenant records, composite tenant-aware relationships where applicable, PostgreSQL RLS, and audit/event records. Establish `app.current_organization_id` with transaction-scoped `SET LOCAL` only after server-side identity verification; reset context through transaction completion and test pooled-connection isolation.
- **Auth:** Argon2id password hashing; server-side authorization; admin MFA required before production access. Demo auth and any development seed credentials must be explicitly labeled and never reused in production.
- **Operations:** Redis and worker interface, private S3-compatible document-storage interface, Docker Compose for local development. External integrations remain stubs until credentials and contract tests exist.
- **Billing:** immutable published tariff versions and invoice snapshots; operational billing and PortFlow subscription billing have separate entities and APIs.

## Phased delivery

1. **Plan and inspect:** preserve existing assignment files; record this PRD/architecture/task plan before implementation.
2. **Foundation:** establish app structure, environment-based settings, database session and RLS helpers, API health/docs, auth primitives, tenant-aware base models, Alembic baseline, and Docker Compose.
3. **Operational slice:** organization/terminal setup, containers and visits, custody/movement event flows, yard structure and allocation, manual vessel calls, tariff publication, operational charges/invoices, customer visibility, audit trail, and idempotent SaaS visit usage.
4. **User experience:** responsive professional console wired to real API/demo data; every primary action has a working path or is clearly marked unavailable; demo data labeled.
5. **Verification and handoff:** run backend tests and frontend build, fix failures, verify API/migrations/Docker configuration as available, document setup, security, deployment, legal, and operational validation prerequisites.

## Acceptance checks for this milestone

- A developer can start the stack from documented environment variables and Docker Compose.
- API schema is available at `/docs`; database migration and deterministic demo seed are included.
- Tenant context cannot be chosen by an untrusted client; RLS is fail-closed and transaction-scoped.
- A visit can be received by truck, rail, or vessel, moved/allocated, and released through truck, rail, or vessel handover; duplicate custody or usage requests are idempotent or rejected safely.
- Storage uses terminal-local calendar dates between custody receipt and release, then applies the versioned free-period/tariff snapshot.
- Customer views are limited to explicitly assigned customer records; invoice types and tenant records cannot cross organizations.
- Local tests/builds pass, or any blocked check is reported with the exact environment limitation.
