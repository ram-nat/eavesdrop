"""Entry point: python -m eavesdrop"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load a .env file from the project root (next to pyproject.toml).

    Only sets variables that aren't already set in the environment.
    No third-party deps — handles simple KEY=VALUE lines only.
    """
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

from eavesdrop.app import EavesdropApp, DEFAULT_SESSIONS_DIR, DEFAULT_OPENCLAW_DIR


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
    parser.add_argument(
        "--cron",
        metavar="PATH",
        type=Path,
        nargs="?",
        const=DEFAULT_OPENCLAW_DIR,
        default=None,
        help=(
            "Launch in cron mode. Optionally specify the openclaw root dir "
            f"(default: {DEFAULT_OPENCLAW_DIR})"
        ),
    )
    args = parser.parse_args()

    app = EavesdropApp(
        sessions_dir=args.dir,
        initial_session=args.session,
        openclaw_dir=args.cron if args.cron is not None else DEFAULT_OPENCLAW_DIR,
        start_cron=args.cron is not None,
    )
    app.run()


if __name__ == "__main__":
    main()
