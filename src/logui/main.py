"""Punto de entrada principal."""

import sys

from logui.ui.app import run


def main() -> int:
    """Ejecutar LogUI."""
    try:
        run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
