from __future__ import annotations

import argparse
from pathlib import Path

from ui.main import run_app
from services.logging_setup import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TA-Lib ローソク足アナライザー")
    parser.add_argument("--csv", type=Path, help="起動時に読み込むウォッチリストCSV", default=None)
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    watchlist = args.csv if args.csv else None
    return run_app(watchlist)


if __name__ == "__main__":
    raise SystemExit(main())
