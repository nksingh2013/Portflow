from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.services import storage_days


def test_storage_days_counts_both_terminal_local_calendar_dates():
    received = datetime.fromisoformat("2026-04-01T18:00:00+05:30").astimezone(UTC)
    released = datetime.fromisoformat("2026-04-03T01:00:00+05:30").astimezone(UTC)
    assert storage_days(received, released, "Asia/Kolkata") == 3


def test_same_calendar_day_is_one_storage_day():
    received = datetime.fromisoformat("2026-04-01T00:10:00+05:30")
    released = datetime.fromisoformat("2026-04-01T23:50:00+05:30")
    assert storage_days(received, released, "Asia/Kolkata") == 1


def test_storage_days_rejects_release_before_receipt():
    received = datetime(2026, 4, 2, tzinfo=UTC)
    released = datetime(2026, 4, 1, tzinfo=UTC)
    with pytest.raises(HTTPException) as error:
        storage_days(received, released, "Asia/Kolkata")
    assert error.value.status_code == 422
