# PortFlow

PortFlow is an India-first maritime Terminal Operating System starter for terminal operators and logistics companies. This repository contains a local development MVP: a FastAPI API, React + TypeScript operator/customer UI, PostgreSQL with RLS migrations, deterministic demo seed, and Docker Compose services.

**Status:** Development MVP. It is not production-ready and has no live port, GPS, payment, email, SMS, WhatsApp, or regulatory integrations.

## Start locally with Docker

Requirements: Docker Desktop with Compose support and PowerShell.

```powershell
.\scripts\bootstrap-env.ps1
docker compose up --build
```

Open the operator console at <http://localhost:8080> and API docs at <http://localhost:8080/api/docs>. The seed is optional and is not run automatically. To load clearly marked demo data:

```powershell
docker compose run --rm api python -m app.seed_demo
```

The bootstrap script writes generated demo passwords and the administrator MFA setup key into the local `.env` file. Read them from that file to sign in and enroll the administrator in an authenticator app. The seed command does not print secret values. Never use demo credentials in production.

## API and local development

- API base: `/api/v1`
- OpenAPI UI: `/api/docs`; schema: `/api/openapi.json`
- Backend source: `backend/app`
- Frontend source: `frontend/src`
- Alembic migrations: `backend/alembic/versions`
- RLS requires the non-superuser `portflow_app` role created by the Postgres init script. Do not connect the API as the database superuser.

The bootstrap script generates local secrets and creates `.env`; it never checks secrets into Git. To run the backend outside Docker, create a virtual environment, install `backend/requirements.txt`, set `PORTFLOW_DATABASE_URL` to a local PostgreSQL URL, then run Alembic and Uvicorn from `backend`. For the frontend, use a Node.js installation with pnpm and run `pnpm install` then `pnpm dev` from `frontend`.

## Demo flow

After seeding, sign in as the printed organization administrator (include the current TOTP code) to see the operator workspace. The customer portal uses a separate printed customer login. Demo content is labeled throughout the UI. All dashboard values come from API queries over stored records.

The first vertical slice supports organizations/terminals, customer accounts, containers/visits, truck/rail/vessel custody receipt, movements, yard slot suggestions/allocation, manual vessel calls, gate appointments and walk-ins, published storage tariffs, operational invoices, customer visibility, audit events, and idempotent per-visit SaaS usage events.

## Security and commercial readiness

- Passwords use Argon2id. JWT secret, database passwords, and demo credentials come from environment variables.
- Admin MFA uses TOTP in this milestone. Google OAuth has an explicit provider interface but is not configured.
- Tenant context comes from a signed identity token and a verified active database membership, then uses transaction-scoped `SET LOCAL`. RLS policies are fail-closed; table ownership and database superuser access bypass ordinary RLS protections, so production app credentials must remain non-owner and non-superuser.
- Published tariff versions and custody/movement events are append-only from API routes. Invoice lines preserve a JSON snapshot of the tariff calculation.
- Operational invoices are separate from PortFlow SaaS subscription/usage records. Usage counts one event per visit, including empty containers and transshipment.
- Configure a real private S3-compatible bucket, TLS, backups, monitoring, key rotation, rate limits, external auth providers, tax/legal treatment, retention, and incident response before production. Validate operational workflows with terminal users and local counsel; this software makes no regulatory-compliance claim.

## Delivery plan

See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the PRD, security architecture, scope boundaries, and acceptance checks. See [docs/SECURITY_AND_DEPLOYMENT.md](docs/SECURITY_AND_DEPLOYMENT.md) for deployment prerequisites. Team-member names are intentionally placeholders in contribution materials.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Run backend tests and frontend production build before opening a pull request. Use demo data only in local/test environments.
