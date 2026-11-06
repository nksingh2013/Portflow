"""Initial PortFlow schema, tenant RLS, and append-only events.

Revision ID: 0001_initial_rls
Revises:
Create Date: 2026-11-05
"""
from alembic import op
from sqlalchemy import text

from app.models import Base

revision = "0001_initial_rls"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "terminals",
    "customers",
    "yard_slots",
    "vessel_calls",
    "containers",
    "container_visits",
    "custody_events",
    "movement_events",
    "gate_appointments",
    "tariffs",
    "tariff_versions",
    "operational_invoices",
    "operational_invoice_lines",
    "saas_usage_events",
    "saas_subscription_invoices",
    "audit_logs",
    "documents",
    "notification_deliveries",
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[table for table in Base.metadata.sorted_tables if table.name != "customer_portal_requests"],
    )
    if bind.dialect.name != "postgresql":
        return

    op.execute(text("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY"))
    op.execute(text("ALTER TABLE organizations FORCE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY organization_isolation ON organizations
        USING (id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
        WITH CHECK (id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
    """))

    # Membership lookup is constrained by a server-signed user identity before
    # tenant selection; it can reveal only the authenticated user's own rows.
    op.execute(text("ALTER TABLE memberships ENABLE ROW LEVEL SECURITY"))
    op.execute(text("ALTER TABLE memberships FORCE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY membership_self_lookup ON memberships
        USING (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)
        WITH CHECK (
            user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            AND organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid
        )
    """))

    for table in TENANT_TABLES:
        op.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(text(f"""
            CREATE POLICY organization_isolation ON "{table}"
            USING (organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
            WITH CHECK (organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
        """))

    op.execute(text("""
        CREATE FUNCTION portflow_reject_immutable_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_TABLE_NAME = 'tariff_versions' THEN
            IF OLD.published_at IS NOT NULL THEN
              RAISE EXCEPTION 'Published tariff versions are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'PortFlow operational records are append-only';
        END;
        $$
    """))
    for table in ("custody_events", "movement_events", "audit_logs", "saas_usage_events", "operational_invoices", "operational_invoice_lines"):
        op.execute(text(f"""
            CREATE TRIGGER portflow_append_only_{table}
            BEFORE UPDATE OR DELETE ON "{table}"
            FOR EACH ROW EXECUTE FUNCTION portflow_reject_immutable_change()
        """))
    op.execute(text("""
        CREATE TRIGGER portflow_published_tariff_immutable
        BEFORE UPDATE OR DELETE ON tariff_versions
        FOR EACH ROW EXECUTE FUNCTION portflow_reject_immutable_change()
    """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("custody_events", "movement_events", "audit_logs", "saas_usage_events", "operational_invoices", "operational_invoice_lines"):
            op.execute(text(f'DROP TRIGGER IF EXISTS portflow_append_only_{table} ON "{table}"'))
        op.execute(text("DROP TRIGGER IF EXISTS portflow_published_tariff_immutable ON tariff_versions"))
        op.execute(text("DROP FUNCTION IF EXISTS portflow_reject_immutable_change()"))
        for table in (*TENANT_TABLES, "memberships", "organizations"):
            op.execute(text(f'DROP POLICY IF EXISTS organization_isolation ON "{table}"'))
            op.execute(text(f'DROP POLICY IF EXISTS membership_self_lookup ON "{table}"'))
            op.execute(text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    Base.metadata.drop_all(bind=bind)
