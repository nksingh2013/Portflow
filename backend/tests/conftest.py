from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

os.environ.setdefault("PORTFLOW_JWT_SECRET", "test-only-secret-which-is-long-enough-to-meet-settings")

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal
from app.db import get_db
from app.main import app
from app.models import Base, Customer, Membership, Organization, Tariff, TariffVersion, Terminal, User
from app.security import hash_password


@pytest.fixture()
def database() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    org = Organization(id=uuid4(), slug="test-terminal", name="Test Terminal", legal_name="Test Terminal Ltd")
    terminal = Terminal(id=uuid4(), organization_id=org.id, code="TST-01", name="Test Terminal", timezone="Asia/Kolkata")
    customer = Customer(id=uuid4(), organization_id=org.id, terminal_id=terminal.id, code="CUST-01", name="Test Logistics", email="ops@example.test")
    user = User(id=uuid4(), email="manager@example.test", display_name="Terminal Manager", password_hash=hash_password("test-password-that-is-long"))
    membership = Membership(id=uuid4(), user_id=user.id, organization_id=org.id, organization_slug=org.slug, terminal_id=terminal.id, customer_id=None, role="terminal_manager")
    tariff = Tariff(id=uuid4(), organization_id=org.id, terminal_id=terminal.id, name="Standard storage")
    tariff_version = TariffVersion(
        id=uuid4(), organization_id=org.id, terminal_id=terminal.id, tariff_id=tariff.id,
        version_number=1, free_storage_days=1, daily_rate=Decimal("80.00"),
        effective_from=datetime(2020, 1, 1, tzinfo=UTC), published_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    with factory() as session:
        session.add_all([org, terminal, customer, user, membership, tariff, tariff_version])
        session.commit()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    def override_principal(db: Session = Depends(get_db)) -> Principal:
        return Principal(user=db.get(User, user.id), membership=db.get(Membership, membership.id))

    app.dependency_overrides[get_db] = override_db
    from app.auth import get_current_principal
    app.dependency_overrides[get_current_principal] = override_principal
    try:
        yield {"engine": engine, "factory": factory, "organization": org, "terminal": terminal, "customer": customer, "user": user}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(database: dict) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
