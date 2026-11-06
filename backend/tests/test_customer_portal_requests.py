from uuid import UUID

from sqlalchemy import select

from app.models import CustomerPortalRequest, Membership, User
from app.security import verify_password


def _promote_to_admin(database):
    with database["factory"]() as session:
        membership = session.scalar(select(Membership).where(Membership.user_id == database["user"].id))
        membership.role = "organization_admin"
        membership.terminal_id = None
        session.commit()


def test_customer_request_is_visible_to_admin_and_approval_creates_customer_login(client, database):
    response = client.post(
        "/api/v1/auth/customer-requests",
        json={
            "organization_slug": database["organization"].slug,
            "company_name": "New Logistics",
            "contact_name": "Customer Contact",
            "email": "new-customer@example.com",
            "message": "Please enable our customer portal.",
        },
    )

    assert response.status_code == 201, response.text
    request_id = response.json()["request_id"]
    request_uuid = UUID(request_id)

    with database["factory"]() as session:
        saved_request = session.get(CustomerPortalRequest, request_uuid)
        assert saved_request.status == "pending"
        assert saved_request.email == "new-customer@example.com"

    _promote_to_admin(database)
    requests = client.get("/api/v1/portal-access-requests")
    assert requests.status_code == 200
    assert [item["id"] for item in requests.json()] == [request_id]

    password = "customer-login-password-123"
    approved = client.post(
        f"/api/v1/portal-access-requests/{request_id}/approve",
        json={"customer_id": str(database["customer"].id), "password": password},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["email"] == "new-customer@example.com"
    assert approved.json()["role"] == "customer"

    with database["factory"]() as session:
        user = session.scalar(select(User).where(User.email == "new-customer@example.com"))
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id))
        saved_request = session.get(CustomerPortalRequest, request_uuid)
        assert verify_password(password, user.password_hash)
        assert user.mfa_enabled is False
        assert membership.role == "customer"
        assert membership.customer_id == database["customer"].id
        assert saved_request.status == "approved"
        assert saved_request.customer_id == database["customer"].id

    login_response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "new-customer@example.com",
            "password": password,
            "organization_slug": database["organization"].slug,
        },
    )
    assert login_response.status_code == 200, login_response.text
    assert login_response.json()["role"] == "customer"


def test_customer_access_request_requires_a_real_organization_slug(client):
    response = client.post(
        "/api/v1/auth/customer-requests",
        json={
            "organization_slug": "unknown-workspace",
            "company_name": "New Logistics",
            "contact_name": "Customer Contact",
            "email": "new-customer@example.com",
            "message": "",
        },
    )
    assert response.status_code == 404


def test_non_admin_cannot_view_customer_access_requests(client):
    response = client.get("/api/v1/portal-access-requests")
    assert response.status_code == 403
