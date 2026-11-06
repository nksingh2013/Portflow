from uuid import uuid4

from sqlalchemy import select

from app.models import Customer, Membership, Organization, Terminal, User
from app.security import verify_password


def _promote_to_admin(database):
    with database["factory"]() as session:
        membership = session.scalar(select(Membership).where(Membership.user_id == database["user"].id))
        membership.role = "organization_admin"
        membership.terminal_id = None
        session.commit()


def test_admin_creates_customer_scoped_portal_login(client, database):
    _promote_to_admin(database)
    password = "customer-demo-password-123"

    response = client.post(
        f"/api/v1/customers/{database['customer'].id}/portal-users",
        json={"display_name": "Customer Contact", "email": "portal@example.com", "password": password},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["email"] == "portal@example.com"
    assert payload["role"] == "customer"
    assert payload["organization_slug"] == database["organization"].slug
    assert payload["customer_name"] == database["customer"].name
    assert "password" not in payload

    login_response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "portal@example.com",
            "password": password,
            "organization_slug": database["organization"].slug,
        },
    )
    assert login_response.status_code == 200, login_response.text
    assert login_response.json()["role"] == "customer"

    with database["factory"]() as session:
        user = session.scalar(select(User).where(User.email == "portal@example.com"))
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id))
        assert verify_password(password, user.password_hash)
        assert membership.role == "customer"
        assert membership.organization_id == database["organization"].id
        assert membership.organization_slug == database["organization"].slug
        assert membership.terminal_id == database["terminal"].id
        assert membership.customer_id == database["customer"].id
        assert user.mfa_enabled is False


def test_terminal_manager_cannot_create_customer_portal_login(client, database):
    response = client.post(
        f"/api/v1/customers/{database['customer'].id}/portal-users",
        json={"display_name": "Customer Contact", "email": "portal@example.com", "password": "customer-demo-password-123"},
    )

    assert response.status_code == 403
    with database["factory"]() as session:
        assert session.scalar(select(User.id).where(User.email == "portal@example.com")) is None


def test_admin_cannot_create_portal_login_for_another_organization(client, database):
    _promote_to_admin(database)
    other_org = Organization(id=uuid4(), slug="other-tenant", name="Other Tenant", legal_name="Other Tenant")
    other_terminal = Terminal(id=uuid4(), organization_id=other_org.id, code="OTH-01", name="Other Terminal")
    other_customer = Customer(id=uuid4(), organization_id=other_org.id, terminal_id=other_terminal.id, code="OTHER-01", name="Other Customer")
    with database["factory"]() as session:
        session.add_all([other_org, other_terminal, other_customer])
        session.commit()

    response = client.post(
        f"/api/v1/customers/{other_customer.id}/portal-users",
        json={"display_name": "Customer Contact", "email": "portal@example.com", "password": "customer-demo-password-123"},
    )

    assert response.status_code == 404, response.text
    with database["factory"]() as session:
        assert session.scalar(select(User.id).where(User.email == "portal@example.com")) is None
