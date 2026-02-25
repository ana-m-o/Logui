"""Punto de entrada principal."""

import logging
import sys
from pathlib import Path

from logui.ui.app import run


def main() -> int:
    """Ejecutar LogUI."""
    try:
        # Configure logging to file in user's home directory
        log_file = Path.home() / ".logui.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stderr),
            ],
        )

        run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
