from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone

from textual.app import App, ComposeResult


class DayRolloverTestApp(App[None]):
    def __init__(self, tasks_repo, events_repo, **kwargs):
        super().__init__(**kwargs)
        self.tasks_repo = tasks_repo
        self.events_repo = events_repo

    def compose(self) -> ComposeResult:
        from logui.ui.screens.events import EventsPane
        from logui.ui.screens.tasks import TasksPane

        yield TasksPane(self.tasks_repo)
        yield EventsPane(self.events_repo)


def test_day_rollover_refreshes_tasks_and_events(tmp_path) -> None:
    from logui.domain.entities.task import TaskStatus
    from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
    from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
    from logui.usecases.events import CreateEventInput, create_event
    from logui.usecases.tasks import CreateTaskInput, UpdateTaskPatch, create_task, update_task

    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")

    # Seed a task completed on 2026-01-08 (local day should be stable across TZs: use midday UTC).
    t1 = create_task(tasks_repo, CreateTaskInput(title="Done yesterday"))
    update_task(
        tasks_repo,
        t1.id,
        UpdateTaskPatch(status=TaskStatus.DONE),
        now=datetime(2026, 1, 8, 12, 0, tzinfo=timezone.utc),
    )

    # Seed an event that ends on 2026-01-08.
    create_event(
        events_repo,
        CreateEventInput(
            title="Event yesterday",
            day=date(2026, 1, 8),
            start_time=time(9, 0),
            end_time=time(10, 0),
            end_day_offset=0,
            notify=False,
            notify_minutes_before=None,
        ),
        default_notify_minutes_before=0,
    )

    async def _run() -> None:
        app = DayRolloverTestApp(tasks_repo, events_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks")
            events = app.query_one("#events")

            # Simulate end-of-day -> new day.
            tasks.on_day_rollover(today=date(2026, 1, 9))
            events.on_day_rollover(today=date(2026, 1, 9))
            await pilot.pause()

            # DONE task from previous day is hidden.
            assert getattr(tasks, "_rows") == []

            # Past event is hidden.
            assert getattr(events, "_events") == []

    asyncio.run(_run())
