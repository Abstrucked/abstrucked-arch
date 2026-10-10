#!/usr/bin/env python3
"""Entry point for the os-assistant launcher.

Runs under python3 -B -I (isolated mode), where no default import path points
at this package, so exactly one path is added: the resolved parent directory of
this file, which holds the os_assistant package. Standard library only.
"""

import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from os_assistant.cli import main as cli_main

    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
