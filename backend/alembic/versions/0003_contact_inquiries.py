"""In-app contact requests and inbox.

Revision ID: 0003_contact_inquiries
Revises: 0002_customer_portal_requests
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "0003_contact_inquiries"
down_revision = "0002_customer_portal_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_inquiries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_name", sa.String(length=180), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('open','resolved')", name="ck_contact_inquiry_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_inquiries_organization_id", "contact_inquiries", ["organization_id"])
    op.create_index(
        "ix_contact_inquiry_org_status_created",
        "contact_inquiries",
        ["organization_id", "status", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(text("ALTER TABLE contact_inquiries ENABLE ROW LEVEL SECURITY"))
        op.execute(text("ALTER TABLE contact_inquiries FORCE ROW LEVEL SECURITY"))
        op.execute(text("""
            CREATE POLICY organization_isolation ON contact_inquiries
            USING (organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
            WITH CHECK (organization_id = nullif(current_setting('app.current_organization_id', true), '')::uuid)
        """))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(text("DROP POLICY IF EXISTS organization_isolation ON contact_inquiries"))
        op.execute(text("ALTER TABLE contact_inquiries DISABLE ROW LEVEL SECURITY"))
    op.drop_index("ix_contact_inquiry_org_status_created", table_name="contact_inquiries")
    op.drop_index("ix_contact_inquiries_organization_id", table_name="contact_inquiries")
    op.drop_table("contact_inquiries")
