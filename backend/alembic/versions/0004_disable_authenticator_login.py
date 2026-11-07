"""Clear legacy authenticator secrets after switching to password-only demo login.

Revision ID: 0004_disable_authenticator_login
Revises: 0003_contact_inquiries
Create Date: 2026-11-07
"""
from alembic import op
from sqlalchemy import text


revision = "0004_disable_authenticator_login"
down_revision = "0003_contact_inquiries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MFA is no longer supported by the college demo. Remove stored TOTP secrets
    # and disable the legacy flag without touching accounts or other user data.
    op.execute(text("UPDATE users SET mfa_secret = NULL, mfa_enabled = FALSE"))


def downgrade() -> None:
    # Secret values cannot and should not be restored after being cleared.
    pass
