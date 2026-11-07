from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.models import Container, ContainerVisit, CustodyEvent, Customer, OperationalInvoice, OperationalInvoiceLine, SaasUsageEvent, Terminal


def test_walk_in_idempotency_and_rail_release_create_snapshot_invoice(client, database):
    terminal_id = str(database["terminal"].id)
    customer_id = str(database["customer"].id)
    response = client.post("/api/v1/gate/walk-ins", json={
        "terminal_id": terminal_id,
        "customer_id": customer_id,
        "container_number": "ABCD1234567",
        "size_feet": 40,
        "category": "DRY",
        "is_empty": True,
        "direction": "import",
        "entry_mode": "truck",
        "is_transshipment": False,
        "idempotency_key": "walk-in-request-0001",
        "event_at": "2026-04-01T18:00:00+05:30",
    })
    assert response.status_code == 201, response.text
    visit_id = response.json()["visit"]["id"]

    replay = client.post("/api/v1/gate/walk-ins", json={
        "terminal_id": terminal_id,
        "customer_id": customer_id,
        "container_number": "ABCD1234567",
        "idempotency_key": "walk-in-request-0001",
        "event_at": "2026-04-01T18:00:00+05:30",
    })
    assert replay.status_code == 201, replay.text
    assert replay.json()["duplicate"] is True
    assert replay.json()["visit"]["id"] == visit_id

    duplicate_submission = client.post("/api/v1/gate/walk-ins", json={
        "terminal_id": terminal_id,
        "customer_id": customer_id,
        "container_number": "ABCD1234567",
        "idempotency_key": "walk-in-request-0002",
    })
    assert duplicate_submission.status_code == 409, duplicate_submission.text
    assert duplicate_submission.json()["detail"] == "This container already has an active visit"

    released = client.post(f"/api/v1/visits/{visit_id}/custody/release", json={
        "mode": "rail_dispatch",
        "idempotency_key": "rail-release-request-0001",
        "event_at": "2026-04-03T01:00:00+05:30",
        "external_reference": "RAIL-OUT-1001",
    })
    assert released.status_code == 200, released.text
    payload = released.json()
    assert payload["visit"]["release_mode"] == "rail_dispatch"
    assert payload["invoice_created"] is True
    assert payload["invoice"]["currency"] == "INR"
    assert payload["invoice"]["total"] == "160.00"

    with database["factory"]() as session:
        visit = session.get(ContainerVisit, UUID(visit_id))
        assert visit.status == "released"
        assert session.scalar(select(func.count(CustodyEvent.id)).where(CustodyEvent.visit_id == visit.id)) == 2
        assert session.scalar(select(func.count(SaasUsageEvent.id)).where(SaasUsageEvent.visit_id == visit.id)) == 1
        invoice = session.scalar(select(OperationalInvoice).where(OperationalInvoice.id == UUID(payload["invoice"]["id"])))
        assert invoice.snapshot["calendar_days"] == 3
        assert invoice.snapshot["free_storage_days"] == 1
        assert invoice.snapshot["billable_days"] == 2
        line = session.scalar(select(OperationalInvoiceLine).where(OperationalInvoiceLine.visit_id == visit.id))
        assert line.amount == 160

    release_replay = client.post(f"/api/v1/visits/{visit_id}/custody/release", json={
        "mode": "rail_dispatch",
        "idempotency_key": "rail-release-request-0001",
        "event_at": "2026-04-03T01:00:00+05:30",
    })
    assert release_replay.status_code == 200, release_replay.text
    assert release_replay.json()["duplicate"] is True

    revisit = client.post("/api/v1/visits", json={
        "terminal_id": terminal_id,
        "container_id": response.json()["visit"]["container_id"],
        "direction": "export",
        "idempotency_key": "future-visit-request-0001",
    })
    assert revisit.status_code == 201, revisit.text
    revisit_id = revisit.json()["id"]

    revisit_replay = client.post("/api/v1/visits", json={
        "terminal_id": terminal_id,
        "container_id": response.json()["visit"]["container_id"],
        "direction": "export",
        "idempotency_key": "future-visit-request-0001",
    })
    assert revisit_replay.status_code == 201, revisit_replay.text
    assert revisit_replay.json()["id"] == revisit_id

    active_visit_conflict = client.post("/api/v1/visits", json={
        "terminal_id": terminal_id,
        "container_id": response.json()["visit"]["container_id"],
        "idempotency_key": "future-visit-request-0002",
    })
    assert active_visit_conflict.status_code == 409, active_visit_conflict.text


def test_create_visit_rejects_container_from_another_terminal(client, database):
    other_terminal_id = uuid4()
    other_customer_id = uuid4()
    other_container_id = uuid4()
    with database["factory"]() as session:
        other_terminal = Terminal(
            id=other_terminal_id,
            organization_id=database["organization"].id,
            code="TST-02",
            name="Other Test Terminal",
            timezone="Asia/Kolkata",
        )
        other_customer = Customer(
            id=other_customer_id,
            organization_id=database["organization"].id,
            terminal_id=other_terminal_id,
            code="CUST-02",
            name="Other Test Logistics",
            email="other@example.test",
        )
        other_container = Container(
            id=other_container_id,
            organization_id=database["organization"].id,
            terminal_id=other_terminal_id,
            customer_id=other_customer_id,
            container_number="WXYZ1234567",
            size_feet=40,
            category="DRY",
            is_empty=False,
        )
        session.add_all([other_terminal, other_customer, other_container])
        session.commit()

    response = client.post("/api/v1/visits", json={
        "terminal_id": str(database["terminal"].id),
        "container_id": str(other_container_id),
        "idempotency_key": "wrong-terminal-visit-0001",
    })
    assert response.status_code == 404, response.text


def test_appointment_creation_returns_saved_record(client, database):
    response = client.post("/api/v1/appointments", json={
        "terminal_id": str(database["terminal"].id),
        "customer_id": str(database["customer"].id),
        "vehicle_number": "MH 01 AB 1234",
        "planned_at": "2026-11-07T10:30:00+05:30",
        "notes": "Test appointment",
    })
    assert response.status_code == 201, response.text
    assert response.json()["vehicle_number"] == "MH 01 AB 1234"
    assert response.json()["notes"] == "Test appointment"


def test_yard_allocation_requires_configured_slot_then_assigns_and_marks_it_occupied(client, database):
    terminal_id = str(database["terminal"].id)

    first_visit = client.post("/api/v1/gate/walk-ins", json={
        "terminal_id": terminal_id,
        "customer_id": str(database["customer"].id),
        "container_number": "YARD1234567",
        "category": "DRY",
        "idempotency_key": "yard-walk-in-request-0001",
    })
    assert first_visit.status_code == 201, first_visit.text
    visit_id = first_visit.json()["visit"]["id"]

    no_slots = client.get(f"/api/v1/yard/suggestions?visit_id={visit_id}")
    assert no_slots.status_code == 200, no_slots.text
    assert no_slots.json() == []

    created_slot = client.post("/api/v1/yard/slots", json={
        "terminal_id": terminal_id,
        "code": "A-01-01-01",
        "zone": "GENERAL",
        "block": "A",
        "bay": 1,
        "row": 1,
        "tier": 1,
        "container_category": "DRY",
    })
    assert created_slot.status_code == 201, created_slot.text
    slot_id = created_slot.json()["id"]

    suggestions = client.get(f"/api/v1/yard/suggestions?visit_id={visit_id}")
    assert suggestions.status_code == 200, suggestions.text
    assert [item["slot_id"] for item in suggestions.json()] == [slot_id]

    allocation = client.post("/api/v1/yard/allocate", json={"visit_id": visit_id, "slot_id": slot_id})
    assert allocation.status_code == 200, allocation.text
    assert allocation.json()["visit"]["yard_slot_id"] == slot_id
    assert allocation.json()["movement"]["movement_type"] == "yard_in"
    assert allocation.json()["movement"]["to_slot_id"] == slot_id

    yard = client.get(f"/api/v1/yard/slots?terminal_id={terminal_id}")
    assert yard.status_code == 200, yard.text
    assert yard.json()[0]["occupied"] is True
    assert yard.json()[0]["current_visit_id"] == visit_id
    assert yard.json()[0]["current_container_number"] == "YARD1234567"
