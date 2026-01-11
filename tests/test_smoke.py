def test_imports() -> None:
    import logui  # noqa: F401


def test_version_string() -> None:
    import logui

    assert isinstance(logui.__version__, str)
    assert logui.__version__
