"""Package entry point for `python -m ac`."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
