from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evolution import EvolutionEngine
from .health import HealthWatchdog
from .market_discovery import collect as market_discovery_collect
from .market_intel import MarketIntelEngine
from .naver_batch_market import collect as naver_batch_market_collect
from .pipeline import Pipeline
from .regression import RegressionDetector
from .relative_strength import collect as relative_strength_collect
from .risk_engine import RiskEngine
from .supervisor_queue import observe as supervisor_observe
from .toss_batch_market import collect as toss_batch_market_collect
from .toss_collector import main as toss_collector_main


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
        choices=["dry-run", "live", "sensor"],
        default="dry-run",
        help="sensor는 실제 입력을 읽되 OpenAI 호출 없이 6분 자동복구용 runtime만 갱신",
    )
    market.add_argument("--root", default=".", help="저장소 루트")

    risk = sub.add_parser("risk-intel", help="일정·매크로 기반 Overnight Risk 분석")
    risk.add_argument(
        "--mode",
        choices=["dry-run", "live", "sensor"],
        default="dry-run",
        help="sensor는 LLM 없이 일정·매크로·Risk runtime을 안전하게 갱신",
    )
    risk.add_argument("--root", default=".", help="저장소 루트")

    health = sub.add_parser("health", help="프로젝트 운영 상태 점검")
    health.add_argument("--root", default=".", help="저장소 루트")

    regression = sub.add_parser(
        "regression",
        help="7일/30일 품질 회귀 탐지와 기능 단위 롤백",
    )
    regression.add_argument("--root", default=".", help="저장소 루트")

    batch_market = sub.add_parser(
        "naver-batch-market",
        help="라즈베리파이 없이 네이버 공개 시세로 6분 거래대금 배치를 수집",
    )
    batch_market.add_argument("--root", default=".", help="저장소 루트")
    batch_market.add_argument("--limit", type=int, default=50, help="현재 거래대금 Top50 + 당일 Top50 진입 종목 전체를 추적")

    relative_strength = sub.add_parser(
        "relative-strength",
        help="NASDAQ·KOSPI 기준지수 대비 종목 상대강도를 수집",
    )
    relative_strength.add_argument("--root", default=".", help="저장소 루트")
    relative_strength.add_argument("--limit", type=int, default=500, help="시장별 시가총액 상위 비교 종목 수")
    relative_strength.add_argument("--force", action="store_true", help="30분 캐시를 무시하고 즉시 다시 수집")

    discovery = sub.add_parser(
        "market-discovery-observe",
        help="AI 호출 없이 웹·포털 시장 단서를 수집",
    )
    discovery.add_argument("--root", default=".", help="저장소 루트")

    supervisor = sub.add_parser(
        "supervisor-observe",
        help="AI 호출 없이 6분 감독 관측을 큐에 저장",
    )
    supervisor.add_argument("--root", default=".", help="저장소 루트")

    toss_batch = sub.add_parser(
        "toss-batch-market",
        help="고정 IP 환경에서 Toss REST로 6분 시장 배치 수집",
    )
    toss_batch.add_argument("--root", default=".", help="저장소 루트")
    toss_batch.add_argument("--limit", type=int, default=50, help="현재 거래대금 Top50")

    collector = sub.add_parser(
        "toss-collector",
        help="고정 IP 환경에서 Toss 실시간 체결 Collector 실행",
    )
    collector.add_argument("--output", default="data/providers/toss/latest.json")
    collector.add_argument("--top-n", type=int, default=80)
    collector.add_argument("--ranking-refresh", type=int, default=600)
    collector.add_argument("--snapshot-seconds", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(getattr(args, "root", ".")).resolve()

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
    elif args.command == "regression":
        result = RegressionDetector(root).run()
    elif args.command == "naver-batch-market":
        result = naver_batch_market_collect(root, limit=args.limit)
    elif args.command == "relative-strength":
        result = relative_strength_collect(root, force=args.force, limit=args.limit)
    elif args.command == "market-discovery-observe":
        result = market_discovery_collect(root)
    elif args.command == "supervisor-observe":
        result = supervisor_observe(root)
    elif args.command == "toss-batch-market":
        result = toss_batch_market_collect(root, limit=args.limit)
    elif args.command == "toss-collector":
        toss_collector_main(
            [
                "--output", str((root / args.output).resolve()),
                "--top-n", str(args.top_n),
                "--ranking-refresh", str(args.ranking_refresh),
                "--snapshot-seconds", str(args.snapshot_seconds),
            ]
        )
        return
    else:
        raise SystemExit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
