# Contributing

PortFlow is an early development MVP. Please keep operational events append-only, add tenant scope to every new business record, and avoid presenting stubs as working third-party integrations.

## Contribution record

- Contributor: [Team member name]
- Area: [API / UI / operations / documentation]
- Summary: [Work completed]
- Validation: [Commands and results]

## Review checklist

- [ ] Authorization is enforced server-side.
- [ ] Tenant-owned tables have `organization_id`, RLS policy coverage, and tenant-safe foreign keys.
- [ ] Tenant context is transaction-scoped and comes from verified membership.
- [ ] Financial records snapshot the published tariff version and preserve INR values as decimal amounts.
- [ ] Tests cover success, authorization failure, and duplicate/idempotent requests.
- [ ] No credentials or real customer data are committed.
