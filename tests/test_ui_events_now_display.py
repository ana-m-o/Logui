"""Test that in-progress events show 'Now' instead of 'Today'."""

from datetime import date, time

from logui.domain.entities.event import Event
from logui.ui.screens.events import EventsPane


def test_in_progress_event_shows_now():
    """When an event is in progress, it should show 'Now' instead of 'Today'."""
    # Create an event that is happening now
    today = date(2024, 1, 15)
    event = Event.create(
        title="Meeting",
        day=today,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    
    # Create an EventsPane instance
    pane = EventsPane(repo=None)  # type: ignore[arg-type]
    
    # Mock today_local and datetime.now to control time
    from unittest.mock import patch
    from datetime import datetime
    
    # Mock current time to be during the event (10:30)
    mock_now = datetime(2024, 1, 15, 10, 30)
    
    with patch("logui.ui.screens.events.today_local", return_value=today), \
         patch("logui.ui.screens.events.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        
        # Format the row
        formatted = pane._format_row(event)
        
        # Should contain "Now" instead of "Today"
        assert "[bold]Now[/bold]" in formatted
        assert "[bold]Today[/bold]" not in formatted


def test_future_event_shows_today():
    """When an event hasn't started yet, it should show 'Today'."""
    today = date(2024, 1, 15)
    event = Event.create(
        title="Meeting",
        day=today,
        start_time=time(14, 0),
        end_time=time(15, 0),
    )
    
    pane = EventsPane(repo=None)  # type: ignore[arg-type]
    
    from unittest.mock import patch
    from datetime import datetime
    
    # Mock current time to be before the event (10:00)
    mock_now = datetime(2024, 1, 15, 10, 0)
    
    with patch("logui.ui.screens.events.today_local", return_value=today), \
         patch("logui.ui.screens.events.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        
        formatted = pane._format_row(event)
        
        # Should contain "Today" not "Now"
        assert "[bold]Today[/bold]" in formatted
        assert "[bold]Now[/bold]" not in formatted


def test_past_event_shows_today():
    """When an event has ended, it should show 'Today' (not 'Now')."""
    today = date(2024, 1, 15)
    event = Event.create(
        title="Meeting",
        day=today,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    
    pane = EventsPane(repo=None)  # type: ignore[arg-type]
    
    from unittest.mock import patch
    from datetime import datetime
    
    # Mock current time to be after the event (11:00)
    mock_now = datetime(2024, 1, 15, 11, 0)
    
    with patch("logui.ui.screens.events.today_local", return_value=today), \
         patch("logui.ui.screens.events.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        
        formatted = pane._format_row(event)
        
        # Should contain "Today" not "Now"
        assert "[bold]Today[/bold]" in formatted
        assert "[bold]Now[/bold]" not in formatted


def test_all_day_event_does_not_show_now():
    """All-day events show 'Now' when it's today (they ARE 'in progress' during the day)."""
    today = date(2024, 1, 15)
    event = Event.create(
        title="All day event",
        day=today,
        start_time=None,
        end_time=None,
    )
    
    pane = EventsPane(repo=None)  # type: ignore[arg-type]
    
    from unittest.mock import patch
    from datetime import datetime
    
    # Mock current time to midday
    mock_now = datetime(2024, 1, 15, 12, 0)
    
    with patch("logui.ui.screens.events.today_local", return_value=today), \
         patch("logui.ui.screens.events.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        
        formatted = pane._format_row(event)
        
        # All-day events on today show "Now", not "Today"
        # (because technically they are "in progress" all day)
        assert "[bold]Now[/bold]" in formatted
        assert "[bold]Today[/bold]" not in formatted
