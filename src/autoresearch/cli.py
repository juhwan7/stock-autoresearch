from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous stock research")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run one research cycle")
    run.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
        help="dry-run uses synthetic data; live uses OpenAI web search",
    )
    run.add_argument(
        "--root",
        default=".",
        help="Repository root",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        result = Pipeline(Path(args.root).resolve(), args.mode).run()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
