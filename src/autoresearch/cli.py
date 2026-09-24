from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evolution import EvolutionEngine
from .health import HealthWatchdog
from .market_intel import MarketIntelEngine
from .pipeline import Pipeline
from .risk_engine import RiskEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="자율 주식 리서치와 프로젝트 자기진화")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="시장 리서치 1회 실행")
    run.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
        help="dry-run은 합성 데이터, live는 실제 웹 검색",
    )
    run.add_argument("--root", default=".", help="저장소 루트")

    evolve = sub.add_parser("evolve", help="프로젝트 자기진화 1회 실행")
    evolve.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
    )
    evolve.add_argument("--root", default=".", help="저장소 루트")

    market = sub.add_parser("market-intel", help="국내시장 장세/분봉 거래대금 분석")
    market.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
    )
    market.add_argument("--root", default=".", help="저장소 루트")

    risk = sub.add_parser("risk-intel", help="일정·매크로 기반 Overnight Risk 분석")
    risk.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
    )
    risk.add_argument("--root", default=".", help="저장소 루트")

    health = sub.add_parser("health", help="프로젝트 운영 상태 점검")
    health.add_argument("--root", default=".", help="저장소 루트")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()

    if args.command == "run":
        result = Pipeline(root, args.mode).run()
    elif args.command == "evolve":
        result = EvolutionEngine(root, args.mode).run()
    elif args.command == "market-intel":
        result = MarketIntelEngine(root, args.mode).run()
    elif args.command == "risk-intel":
        result = RiskEngine(root, args.mode).run()
    elif args.command == "health":
        result = HealthWatchdog(root).run()
    else:
        raise SystemExit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
