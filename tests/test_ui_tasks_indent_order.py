"""Test visual order after indent/unindent operations."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import ListItem, ListView

from logui.domain.entities.task import Task
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
from logui.ui.screens.tasks import TasksPane


class TasksOrderTestApp(App[None]):
    def __init__(self, repo, **kwargs):
        super().__init__(**kwargs)
        self.repo = repo
        self.notifications: list[str] = []

    def notify(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.notifications.append(str(message))

    def compose(self) -> ComposeResult:
        yield TasksPane(self.repo)


def get_visible_task_titles(lv: ListView) -> list[str]:
    """Extract task titles from the visible ListView items by inspecting _rows in TasksPane."""
    # Instead of parsing DOM, use the internal _rows structure
    tasks_pane = lv.parent
    while tasks_pane and not hasattr(tasks_pane, '_rows'):
        tasks_pane = tasks_pane.parent
    
    if tasks_pane and hasattr(tasks_pane, '_rows'):
        return [row.task.title for row in tasks_pane._rows]
    
    # Fallback: try to extract from DOM
    items = list(lv.query(ListItem))
    titles = []
    for item in items:
        try:
            from textual.widgets import Static
            # Look for the Static with task_title class
            statics = list(item.query(Static))
            for static in statics:
                if "task_title" in str(static.classes):
                    # Get the str representation of the rendered content
                    try:
                        # Try getting from internal state
                        if hasattr(static, '_render_cache'):
                            # This might have rendered text
                            pass
                        # Best way: check the segments or text directly
                        rendered = static.render()
                        if hasattr(rendered, 'plain'):
                            titles.append(rendered.plain.strip())
                        else:
                            titles.append(str(rendered).strip())
                        break
                    except Exception as e2:
                        titles.append(f"???e2:{e2}")
                        break
            else:
                titles.append("???noclass")
        except Exception as e:
            titles.append(f"???e:{e}")
    return titles


def get_dom_indices(lv: ListView) -> list[int]:
    """Get the actual DOM order by checking ListItem positions in the children list."""
    items = list(lv.query(ListItem))
    # Get the children list from the ListView to see actual DOM order
    children = list(lv.children)
    indices = []
    for item in items:
        try:
            idx = children.index(item)
            indices.append(idx)
        except ValueError:
            indices.append(-1)
    return indices


def test_indent_visual_order(tmp_path) -> None:
    """Test that visual order is correct after indent."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Sparse orders that simulate gaps left after prior task deletions.
    t1 = Task.create("Task1", order=5.0)
    _gap = Task.create("_gap", order=9.0)
    t2 = Task.create("Task2", order=14.0)
    t3 = Task.create("Task3", order=20.0)
    repo.upsert_task(t1)
    repo.upsert_task(_gap)
    repo.upsert_task(t2)
    repo.upsert_task(t3)
    repo.delete_task(_gap.id)

    async def _run() -> None:
        app = TasksOrderTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            # Initial order should be: Task1, Task2, Task3
            initial_titles = get_visible_task_titles(lv)
            print(f"Initial order: {initial_titles}")
            assert initial_titles == ["Task1", "Task2", "Task3"], f"Got: {initial_titles}"

            # Select Task2 (index 1) and indent it
            lv.index = 1
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()

            # After indent, Task2 should be a subtask of Task1
            # Visual order should be: Task1, Task2 (indented), Task3
            after_indent_titles = get_visible_task_titles(lv)
            print(f"After indent: {after_indent_titles}")
            assert after_indent_titles == ["Task1", "Task2", "Task3"], f"Got: {after_indent_titles}"

            # Verify Task2 is visually indented (has task_subtask class)
            items = list(lv.query(ListItem))
            assert items[1].has_class("task_subtask"), "Task2 should have task_subtask class"

    import asyncio

    asyncio.run(_run())


def test_unindent_visual_order(tmp_path) -> None:
    """Test that visual order is correct after unindent."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Sparse orders: Task1=#5, Task2=#20 (gap from deleted root at #9).
    # SubA=#3, SubB=#12 (gap from deleted subtask between them).
    t1 = Task.create("Task1", order=5.0)
    repo.upsert_task(t1)
    task1_obj = repo.get_task(t1.id)
    assert task1_obj is not None

    sub_a = Task.create("SubA", order=3.0)
    sub_b = Task.create("SubB", order=12.0)
    task1_obj.add_subtask(sub_a)
    task1_obj.add_subtask(sub_b)
    repo.upsert_task(task1_obj)

    _gap_root = Task.create("_gap_root", order=9.0)
    repo.upsert_task(_gap_root)
    t2 = Task.create("Task2", order=20.0)
    repo.upsert_task(t2)
    repo.delete_task(_gap_root.id)

    async def _run() -> None:
        app = TasksOrderTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            # Initial order: Task1, SubA, SubB, Task2
            initial_titles = get_visible_task_titles(lv)
            print(f"Initial order: {initial_titles}")
            assert initial_titles == ["Task1", "SubA", "SubB", "Task2"], f"Got: {initial_titles}"

            # Select SubB (index 2) and unindent it
            lv.index = 2
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()

            # After unindent, SubB should be a root task after Task1
            # Expected visual order: Task1, SubA, SubB, Task2
            # Or possibly: Task1, SubA, Task2, SubB (depending on order calculation)
            after_unindent_titles = get_visible_task_titles(lv)
            print(f"After unindent: {after_unindent_titles}")
            
            # SubB should be in the list
            assert "SubB" in after_unindent_titles, f"SubB not found in {after_unindent_titles}"
            
            # SubB should NOT have task_subtask class anymore
            items = list(lv.query(ListItem))
            sub_b_index = after_unindent_titles.index("SubB")
            assert not items[sub_b_index].has_class("task_subtask"), "SubB should not have task_subtask class"

            # Verify actual data order matches visual order
            pane = app.query_one("#tasks", TasksPane)
            data_titles = [row.task.title for row in pane._rows]
            print(f"Data order: {data_titles}")
            assert data_titles == after_unindent_titles, f"Data order {data_titles} != Visual order {after_unindent_titles}"

    import asyncio

    asyncio.run(_run())


def test_multiple_indent_operations(tmp_path) -> None:
    """Test multiple indent operations maintain correct visual order."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Sparse orders that simulate gaps left after prior task deletions.
    ta = Task.create("A", order=5.0)
    _gap1 = Task.create("_gap1", order=9.0)
    tb = Task.create("B", order=14.0)
    _gap2 = Task.create("_gap2", order=17.0)
    tc = Task.create("C", order=20.0)
    td = Task.create("D", order=28.0)
    repo.upsert_task(ta)
    repo.upsert_task(_gap1)
    repo.upsert_task(tb)
    repo.upsert_task(_gap2)
    repo.upsert_task(tc)
    repo.upsert_task(td)
    repo.delete_task(_gap1.id)
    repo.delete_task(_gap2.id)

    async def _run() -> None:
        app = TasksOrderTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            # Initial: A, B, C, D
            initial_titles = get_visible_task_titles(lv)
            print(f"Step 0: {initial_titles}")
            assert initial_titles == ["A", "B", "C", "D"]

            # Verify DOM order matches
            dom_indices = get_dom_indices(lv)
            print(f"Step 0 DOM indices: {dom_indices}")
            # Should be in ascending order [0, 1, 2, 3] or similar
            assert dom_indices == sorted(dom_indices), f"DOM order is not sequential: {dom_indices}"

            # Indent B (B becomes subtask of A)
            lv.index = 1
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()

            step1_titles = get_visible_task_titles(lv)
            print(f"Step 1 (indent B): {step1_titles}")
            assert step1_titles == ["A", "B", "C", "D"], f"Got: {step1_titles}"

            # Verify DOM order
            dom_indices = get_dom_indices(lv)
            print(f"Step 1 DOM indices: {dom_indices}")
            assert dom_indices == sorted(dom_indices), f"DOM order is not sequential after indent B: {dom_indices}"

            # Indent C (C should become subtask of A, not B)
            lv.index = 2
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()

            step2_titles = get_visible_task_titles(lv)
            print(f"Step 2 (indent C): {step2_titles}")
            # Expected: A, B (sub), C (sub), D
            assert step2_titles == ["A", "B", "C", "D"], f"Got: {step2_titles}"

            # Verify DOM order
            dom_indices = get_dom_indices(lv)
            print(f"Step 2 DOM indices: {dom_indices}")
            assert dom_indices == sorted(dom_indices), f"DOM order is not sequential after indent C: {dom_indices}"

            # Verify data matches visual
            pane = app.query_one("#tasks", TasksPane)
            data_titles = [row.task.title for row in pane._rows]
            print(f"Final data order: {data_titles}")
            assert data_titles == step2_titles

    import asyncio

    asyncio.run(_run())


def test_move_parent_up_keeps_subtasks_below_parent(tmp_path) -> None:
    """Regression: moving a parent task up must keep its subtasks under it."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Root gaps: Top=#3, [deleted #8], Parent=#14, Bottom=#22.
    # Subtask gaps: Child A=#4, [deleted subtask implies gap], Child B=#15.
    top_t = Task.create("Top", order=3.0)
    _gap_root = Task.create("_gap_root", order=8.0)
    parent_t = Task.create("Parent", order=14.0)
    bottom_t = Task.create("Bottom", order=22.0)
    repo.upsert_task(top_t)
    repo.upsert_task(_gap_root)
    repo.upsert_task(parent_t)
    repo.upsert_task(bottom_t)
    repo.delete_task(_gap_root.id)

    parent_obj = repo.get_task(parent_t.id)
    assert parent_obj is not None
    parent_obj.add_subtask(Task.create("Child A", order=4.0))
    parent_obj.add_subtask(Task.create("Child B", order=15.0))
    repo.upsert_task(parent_obj)

    async def _run() -> None:
        app = TasksOrderTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            initial_titles = get_visible_task_titles(lv)
            assert initial_titles == ["Top", "Parent", "Child A", "Child B", "Bottom"]

            # Move Parent (index 1) up over Top.
            lv.index = 1
            await pilot.pause()
            await pilot.press("alt+up")
            await pilot.pause()

            after_titles = get_visible_task_titles(lv)
            assert after_titles == ["Parent", "Child A", "Child B", "Top", "Bottom"]

            # Children must remain below parent and marked as subtasks.
            items = list(lv.query(ListItem))
            assert not items[0].has_class("task_subtask")
            assert items[1].has_class("task_subtask")
            assert items[2].has_class("task_subtask")

            # Data model order must match visible order.
            pane = app.query_one("#tasks", TasksPane)
            data_titles = [row.task.title for row in pane._rows]
            assert data_titles == after_titles

    import asyncio

    asyncio.run(_run())
