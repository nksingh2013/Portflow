"""Customer portal access requests.

Revision ID: 0002_customer_portal_requests
Revises: 0001_initial_rls
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "0002_customer_portal_requests"
down_revision = "0001_initial_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_portal_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=180), nullable=False),
        sa.Column("contact_name", sa.String(length=180), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("message", sa.String(length=500), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("terminal_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('pending','approved','rejected')", name="ck_portal_request_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id", "terminal_id"],
            ["customers.id", "customers.organization_id", "customers.terminal_id"],
            name="fk_portal_request_customer_tenant",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_portal_requests_organization_id", "customer_portal_requests", ["organization_id"])
    op.create_index(
        "ix_portal_request_org_status_created",
        "customer_portal_requests",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "uq_pending_portal_request_org_email",
        "customer_portal_requests",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=text("status = 'pending'"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(text("ALTER TABLE customer_portal_requests ENABLE ROW LEVEL SECURITY"))
        op.execute(text("ALTER TABLE customer_portal_requests FORCE ROW LEVEL SECURITY"))
        op.execute(text("""
            CREATE POLICY organization_isolation ON customer_portal_requests
            USING (organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
            WITH CHECK (organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
        """))
        op.execute(text("""
            CREATE POLICY organization_public_slug_lookup ON organizations
            FOR SELECT
            USING (slug = nullif(current_setting('app.public_organization_slug', true), ''))
        """))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(text("DROP POLICY IF EXISTS organization_public_slug_lookup ON organizations"))
        op.execute(text("DROP POLICY IF EXISTS organization_isolation ON customer_portal_requests"))
        op.execute(text("ALTER TABLE customer_portal_requests DISABLE ROW LEVEL SECURITY"))
    op.drop_index("uq_pending_portal_request_org_email", table_name="customer_portal_requests")
    op.drop_index("ix_portal_request_org_status_created", table_name="customer_portal_requests")
    op.drop_index("ix_customer_portal_requests_organization_id", table_name="customer_portal_requests")
    op.drop_table("customer_portal_requests")
