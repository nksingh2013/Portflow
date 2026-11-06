# Security and deployment notes

PortFlow is an early development MVP. Deploy only to an isolated development or test environment until the remaining items below are implemented, independently reviewed, and validated with terminal operators.

## Local environment

1. Run `scripts/bootstrap-env.ps1` to create a local `.env` with random secrets. The file is ignored by Git.
2. Start PostgreSQL, Redis, API, worker, and web services with `docker compose up --build`.
3. Apply the Alembic baseline automatically at API startup. The API and worker connect as the non-superuser `portflow_app` role. Never use the PostgreSQL administrator role for application traffic.
4. Run `docker compose run --rm api python -m app.seed_demo` to load clearly labeled sample data. Demo passwords and the administrator TOTP setup key are in the local `.env` file.
5. Open `/api/docs` on the local web origin for the versioned API schema.

The initial migration is a PostgreSQL migration. SQLite is used only by business-flow tests; it does not enforce PostgreSQL RLS or append-only triggers.

## Implemented safeguards

- Passwords are hashed with Argon2id. Administrator sign-in requires TOTP enrollment. Other roles may enable TOTP.
- Authorization is checked by the API. Tenant context is taken from a signed access token, checked against an active database membership, and set with transaction-local PostgreSQL settings.
- Tenant tables use forced PostgreSQL RLS. Composite foreign keys bind terminals, customers, visits, slots, invoices, and related records to the same organization and terminal.
- Custody, movement, audit, usage, operational invoice, and invoice-line records are append-only in PostgreSQL. Published tariff versions cannot be changed or deleted.
- Custody release and SaaS visit usage are idempotent. Calendar-day storage and the applicable tariff values are stored in the operational invoice snapshot.
- Document storage, Google sign-in, external vessel schedules, and email/SMS/WhatsApp delivery report unavailable until provider credentials and integrations are configured.

## Required before production

- Use HTTPS behind a hardened proxy; configure trusted proxy headers, strict host validation, CSRF protections for browser-authenticated flows, and secure cookie/session behavior if token storage changes.
- Store secrets in a managed secret service, rotate signing and database credentials, and configure least-privilege database roles and ownership. Test RLS with the deployed role and pooled connections, including missing and switched tenant context.
- Add MFA recovery and enrollment operations, login and API rate limits, account lockout controls, security monitoring, dependency scanning, and independent penetration testing.
- Configure private S3-compatible document storage with encryption, retention, malware scanning, access auditing, and short-lived signed downloads.
- Add tested encrypted backups, point-in-time recovery, restore exercises, monitoring, alerting, incident response, and business continuity procedures.
- Configure tax rules, invoice numbering, credit notes, retention, privacy terms, customer contracts, local legal review, and applicable maritime/port regulatory review. The MVP does not calculate configured tax or claim regulatory approval.
- Implement and contract-test real Google OAuth, port/terminal integrations, vessel schedule feeds, notification channels, payments, and any GPS features before describing them as available.
- Load-test multi-terminal operations and verify berth, cargo, shipment, transport-provider, gate, yard, billing, audit, and customer workflows with real terminal staff.

## Deployment status

Docker Compose is a local development setup, not a production deployment design. No live GPS, port-system integration, external message delivery, or payment processing is present. SaaS subscription invoices and usage records are separate from terminal operational invoices; no subscription payment provider is connected.
