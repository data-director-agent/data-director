# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""The former name of scripts/dd.py, kept so that `uv run scripts/dev.py setup` still works."""

import sys

from dd import main

if __name__ == "__main__":
    sys.exit(main())
