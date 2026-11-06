from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        # Closing the request session rolls back unfinished transactions and any
        # transaction-local tenant setting before this connection returns to pool.
        session.close()


def set_tenant_context(session: Session, organization_id: object) -> None:
    """Set RLS context transaction-locally after server-side membership checks."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, true)"),
            {"org_id": str(organization_id)},
        )
    session.info["organization_id"] = str(organization_id)


def set_identity_context(session: Session, user_id: object) -> None:
    """Allow a user to load only their own membership mapping during sign-in."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )
    session.info["user_id"] = str(user_id)


def require_tenant_context(session: Session, organization_id: object) -> None:
    """Fail closed in application services if a tenant context was not established."""
    expected = str(organization_id)
    if session.info.get("organization_id") != expected:
        raise PermissionError("Verified tenant context is required for this operation")
