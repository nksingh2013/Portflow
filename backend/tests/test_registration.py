from sqlalchemy import select

from app.models import Membership, Organization, User


def test_registration_retries_with_available_slug_when_requested_slug_is_taken(client, database):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "College Demo",
            "organization_slug": database["organization"].slug,
            "terminal_name": "Demo Terminal",
            "terminal_code": "COL-01",
            "admin_name": "Demo Owner",
            "email": "college-owner@example.com",
            "password": "college-demo-password-123",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["organization_slug"].startswith(f"{database['organization'].slug}-")
    assert payload["access_token"]
    assert payload["role"] == "organization_admin"

    # Existing admins who previously enrolled no longer need a code.
    with database["factory"]() as session:
        user = session.scalar(select(User).where(User.email == "college-owner@example.com"))
        user.mfa_secret = "legacy-secret"
        user.mfa_enabled = True
        session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={
            "username": "college-owner@example.com",
            "password": "college-demo-password-123",
        },
    )
    assert login.status_code == 200
    assert login.json()["access_token"]
    assert client.post("/api/v1/auth/mfa/confirm", json={}).status_code == 404
    assert client.post("/api/v1/auth/mfa/setup", json={}).status_code == 404

    with database["factory"]() as session:
        user = session.scalar(select(User).where(User.email == "college-owner@example.com"))
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id))
        organization = session.get(Organization, membership.organization_id)
        assert membership.organization_slug == payload["organization_slug"]
        assert organization.slug == payload["organization_slug"]
