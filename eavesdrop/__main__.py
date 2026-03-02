"""Entry point: python -m eavesdrop"""

from __future__ import annotations

import argparse
from pathlib import Path

from eavesdrop.app import EavesdropApp, DEFAULT_SESSIONS_DIR


def main():
    parser = argparse.ArgumentParser(
        prog="eavesdrop",
        description="TUI browser for openclaw session JSONL files",
    )
    parser.add_argument(
        "--session",
        metavar="PATH",
        type=Path,
        help="Load a specific session file directly",
    )
    parser.add_argument(
        "--dir",
        metavar="PATH",
        type=Path,
        default=DEFAULT_SESSIONS_DIR,
        help=f"Sessions directory (default: {DEFAULT_SESSIONS_DIR})",
    )
    args = parser.parse_args()

    app = EavesdropApp(
        sessions_dir=args.dir,
        initial_session=args.session,
    )
    app.run()


if __name__ == "__main__":
    main()
