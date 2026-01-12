from __future__ import annotations

from datetime import date

from logui.ui.screens.events import _sync_end_fields_logic


def test_start_time_change_does_not_autofill_end_time_when_empty():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    res = _sync_end_fields_logic(
        changed_id="start_time",
        start_day=start_day,
        start_time_raw="10:00",
        end_day_raw="",
        end_time_raw="",
        duration_minutes=60,
        end_day_autofilled=False,
        today=today,
    )

    assert res.end_time_value is None
    assert res.end_day_value is None


def test_start_time_change_preserves_duration_when_end_time_exists():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    # Previous duration was 2h; start moved to 11:00, so end should become 13:00.
    res = _sync_end_fields_logic(
        changed_id="start_time",
        start_day=start_day,
        start_time_raw="11:00",
        end_day_raw="",
        end_time_raw="12:00",
        duration_minutes=120,
        end_day_autofilled=False,
        today=today,
    )

    assert res.end_time_value == "13:00"
    assert res.end_day_value is None  # no rollover, keep end_day empty


def test_start_time_change_sets_end_day_only_on_rollover():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    res = _sync_end_fields_logic(
        changed_id="start_time",
        start_day=start_day,
        start_time_raw="23:30",
        end_day_raw="",
        end_time_raw="00:30",  # exists, but will be recomputed anyway
        duration_minutes=60,
        end_day_autofilled=False,
        today=today,
    )

    assert res.end_time_value == "00:30"
    assert res.end_day_value == "2025-12-26"
    assert res.end_day_autofilled is True


def test_end_time_change_autofills_end_day_only_when_needed_and_updates_duration():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    # User sets an end_time earlier than start_time -> implies rollover.
    res = _sync_end_fields_logic(
        changed_id="end_time",
        start_day=start_day,
        start_time_raw="23:30",
        end_day_raw="",
        end_time_raw="00:15",
        duration_minutes=None,
        end_day_autofilled=False,
        today=today,
    )

    assert res.end_day_value == "2025-12-26"
    assert res.duration_minutes == 45


def test_clears_autofilled_end_day_when_end_time_is_cleared():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    res = _sync_end_fields_logic(
        changed_id="end_time",
        start_day=start_day,
        start_time_raw="23:30",
        end_day_raw="2025-12-26",
        end_time_raw="",
        duration_minutes=60,
        end_day_autofilled=True,
        today=today,
    )

    assert res.end_day_value is None
    assert res.duration_minutes is None
    assert res.end_day_autofilled is True


def test_start_time_change_updates_autofilled_end_day_when_present():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    # Event originally crossed midnight (+1) and end_day is shown (autofilled).
    # Moving start later should keep +1 and update end_time accordingly.
    res = _sync_end_fields_logic(
        changed_id="start_time",
        start_day=start_day,
        start_time_raw="23:30",
        end_day_raw="2025-12-26",
        end_time_raw="00:00",
        duration_minutes=60,
        end_day_autofilled=True,
        today=today,
    )

    assert res.end_time_value == "00:30"
    assert res.end_day_value == "2025-12-26"
    assert res.end_day_autofilled is True


def test_start_time_change_clears_autofilled_end_day_when_rollover_no_longer_needed():
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    # Event originally crossed midnight (+1). If start moves earlier so end is same-day,
    # the autofilled end_day should be cleared.
    res = _sync_end_fields_logic(
        changed_id="start_time",
        start_day=start_day,
        start_time_raw="22:00",
        end_day_raw="2025-12-26",
        end_time_raw="00:00",
        duration_minutes=60,
        end_day_autofilled=True,
        today=today,
    )

    assert res.end_time_value == "23:00"
    assert res.end_day_value == "2025-12-25"
    assert res.end_day_autofilled is True


def test_end_time_after_start_time_does_not_autofill_end_day():
    """Test that when end_time >= start_time, end_day is NOT auto-filled."""
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    # User enters end_time that is after start_time (same day)
    res = _sync_end_fields_logic(
        changed_id="end_time",
        start_day=start_day,
        start_time_raw="10:00",
        end_day_raw="",
        end_time_raw="14:00",
        duration_minutes=None,
        end_day_autofilled=False,
        today=today,
    )

    # end_day should remain empty (not auto-filled)
    assert res.end_day_value is None
    assert res.duration_minutes == 240  # 4 hours
    assert res.end_day_autofilled is False


def test_end_time_before_start_time_autofills_end_day_plus_one():
    """Test that when end_time < start_time, end_day IS auto-filled with +1 day."""
    today = date(2025, 12, 25)
    start_day = date(2025, 12, 25)

    # User enters end_time that is before start_time (implies next day)
    res = _sync_end_fields_logic(
        changed_id="end_time",
        start_day=start_day,
        start_time_raw="22:00",
        end_day_raw="",
        end_time_raw="02:00",
        duration_minutes=None,
        end_day_autofilled=False,
        today=today,
    )

    # end_day should be auto-filled with next day
    assert res.end_day_value == "2025-12-26"
    assert res.duration_minutes == 240  # 4 hours (22:00 -> 02:00 next day)
    assert res.end_day_autofilled is True
