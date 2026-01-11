def test_ui_imports() -> None:
    # Catches syntax/import errors in UI modules (not covered by domain/usecase tests).
    from logui.ui.app import LogUIApp  # noqa: F401


def test_app_starts_in_test_mode() -> None:
    # This exercises CSS loading/parsing and widget composition without opening a real TTY.
    import asyncio

    from logui.ui.app import LogUIApp

    async def _run() -> None:
        app = LogUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Basic sanity: main content switcher exists.
            app.query_one("#content")

    asyncio.run(_run())
