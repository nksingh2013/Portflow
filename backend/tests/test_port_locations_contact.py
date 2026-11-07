from uuid import UUID

from sqlalchemy import func, select

from app.models import ContactInquiry, Terminal
from app.port_catalog import ASIAN_MAJOR_PORTS


def _promote_to_admin(database):
    from app.models import Membership

    with database["factory"]() as session:
        membership = session.scalar(select(Membership).where(Membership.user_id == database["user"].id))
        membership.role = "organization_admin"
        membership.terminal_id = None
        session.commit()


def test_asian_port_import_is_idempotent_and_keeps_existing_terminal(client, database):
    _promote_to_admin(database)

    first = client.post("/api/v1/terminals/import-asian-ports", json={})
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["total_catalog_count"] == len(ASIAN_MAJOR_PORTS)
    assert result["created_count"] == len(ASIAN_MAJOR_PORTS)
    assert result["skipped_count"] == 0

    second = client.post("/api/v1/terminals/import-asian-ports", json={})
    assert second.status_code == 200, second.text
    assert second.json()["created_count"] == 0
    assert second.json()["skipped_count"] == len(ASIAN_MAJOR_PORTS)

    with database["factory"]() as session:
        assert session.scalar(select(func.count(Terminal.id))) == len(ASIAN_MAJOR_PORTS) + 1
        original = session.get(Terminal, database["terminal"].id)
        assert original.name == "Test Terminal"
        assert original.timezone == "Asia/Kolkata"


def test_port_catalog_is_public_and_contains_timezones(client):
    response = client.get("/api/v1/ports/catalog")
    assert response.status_code == 200
    ports = response.json()
    assert len(ports) == len(ASIAN_MAJOR_PORTS)
    assert {"name", "city", "country", "region", "timezone"} <= ports[0].keys()
    assert any(port["name"] == "Port of Singapore" and port["timezone"] == "Asia/Singapore" for port in ports)


def test_container_location_uses_latest_terminal_record(client, database):
    response = client.post("/api/v1/gate/walk-ins", json={
        "terminal_id": str(database["terminal"].id),
        "customer_id": str(database["customer"].id),
        "container_number": "ABCD7654321",
        "entry_mode": "truck",
        "idempotency_key": "location-test-walk-in-0001",
    })
    assert response.status_code == 201, response.text

    locations = client.get(f"/api/v1/locations/containers?terminal_id={database['terminal'].id}")
    assert locations.status_code == 200, locations.text
    assert len(locations.json()) == 1
    row = locations.json()[0]
    assert row["container_number"] == "ABCD7654321"
    assert row["current_location"] == "Terminal yard · Test Terminal"
    assert row["status"] == "in_terminal"
    assert row["timezone"] == "Asia/Kolkata"
    assert row["last_updated_at"].endswith(("+00:00", "Z"))


def test_contact_request_is_saved_and_admin_can_resolve(client, database):
    payload = {
        "organization_slug": database["organization"].slug,
        "contact_name": "Visitor",
        "email": "visitor@example.com",
        "subject": "Access help",
        "message": "Please help me request customer access.",
    }
    created = client.post("/api/v1/auth/contact-requests", json=payload)
    assert created.status_code == 201, created.text
    inquiry_id = created.json()["request_id"]

    with database["factory"]() as session:
        inquiry = session.get(ContactInquiry, UUID(inquiry_id))
        assert inquiry is not None
        assert inquiry.status == "open"
        assert inquiry.email == payload["email"]

    assert client.get("/api/v1/contact-requests").status_code == 403
    _promote_to_admin(database)
    inbox = client.get("/api/v1/contact-requests")
    assert inbox.status_code == 200, inbox.text
    assert [item["id"] for item in inbox.json()] == [inquiry_id]

    resolved = client.post(f"/api/v1/contact-requests/{inquiry_id}/resolve", json={})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["email"] == payload["email"]
    assert client.get("/api/v1/contact-requests").json() == []


def test_contact_request_rejects_unknown_organization(client):
    response = client.post("/api/v1/auth/contact-requests", json={
        "organization_slug": "not-a-workspace",
        "contact_name": "Visitor",
        "email": "visitor@example.com",
        "subject": "Help",
        "message": "A valid message body.",
    })
    assert response.status_code == 404
