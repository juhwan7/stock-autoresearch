from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import load_prompt, load_settings, load_yaml, render_prompt
from .llm import ResearchLLM


def _kst_label(now: datetime) -> str:
    return (now + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M KST")


def _read(path: Path, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return text if limit is None else text[:limit]


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        if path.exists() and path.stat().st_size > 0:
            f.write("\n")
        f.write(text.rstrip() + "\n")


class EvolutionEngine:
    def __init__(self, root: Path, mode: str = "live"):
        self.root = root
        self.mode = mode
        self.settings = load_yaml(root / "config" / "evolution.yaml")
        self.research_settings = load_settings(root)
        self.limits = self.settings.get("limits", {})
        self.auto = self.settings.get("auto_apply", {})
        self.validation = self.settings.get("validation", {})
        self._last_change_backup: dict[str, str | None] = {}
        self.llm = None
        if mode == "live":
            self.llm = ResearchLLM(self.settings.get("models", {}).get("scout", {}))

    def _memory(self) -> str:
        parts = []
        for rel in (
            "docs/DECISIONS.md",
            "docs/IDEAS.md",
            "docs/EXPERIMENTS.md",
            "docs/HELP_NEEDED.md",
            "docs/CHANGELOG_AI.md",
        ):
            text = _read(self.root / rel, 24000)
            parts.append(f"\n--- {rel} ---\n{text[-16000:]}")
        return "".join(parts)

    def _snapshot(self) -> str:
        max_chars = int(self.limits.get("max_snapshot_chars", 180000))
        preferred = [
            "README.md",
            "AGENTS.md",
            "config/research.yaml",
            "config/scoring.yaml",
            "config/sources.yaml",
            "config/evolution.yaml",
            "config/market_intel.yaml",
            "config/risk.yaml",
            "config/events_2026.yaml",
            "docs/TRADING_RESEARCH_MANDATE.md",
            "docs/RISK_VETO.md",
            "docs/DOCS_MAP.md",
            "docs/TOSS_DATA_PLAN.md",
            "docs/MARKET_DATA_SPEC.md",
            "src/autoresearch/market_intel.py",
            "src/autoresearch/risk_engine.py",
            "src/autoresearch/market_stats.py",
            "src/autoresearch/pullback_stats.py",
            "src/autoresearch/kiwoom_source.py",
            "prompts/market_regime.md",
            "prompts/risk_evaluator.md",
            "src/autoresearch/pipeline.py",
            "src/autoresearch/llm.py",
            "src/autoresearch/scoring.py",
            "src/autoresearch/report.py",
            "src/autoresearch/memory.py",
            "src/autoresearch/evolution.py",
            "prompts/market_scanner.md",
            "prompts/researcher.md",
            "prompts/critic.md",
            "prompts/chief_researcher.md",
            "site/index.html",
            "site/app.js",
            "site/style.css",
        ]
        chunks: list[str] = []
        used = 0
        for rel in preferred:
            text = _read(self.root / rel)
            if not text:
                continue
            chunk = f"\n===== {rel} =====\n{text}\n"
            if used + len(chunk) > max_chars:
                remaining = max_chars - used
                if remaining > 1000:
                    chunks.append(chunk[:remaining])
                break
            chunks.append(chunk)
            used += len(chunk)
        return "".join(chunks)

    def _scout(self, now: datetime) -> dict[str, Any]:
        if self.mode == "dry-run":
            return {
                "decision": "no_change",
                "category": "testing",
                "title": "[DRY-RUN] 자기진화 파이프라인 점검",
                "observation": "실제 모델 호출 없이 기록 경로를 검증한다.",
                "decision_basis": "dry-run 모드",
                "expected_benefit": "자동화 검증",
                "risk": "low",
                "idea_status": "실험중",
                "needs_user": False,
                "user_help": None,
                "builder_instruction": "",
                "references": [],
            }

        prompt = render_prompt(
            load_prompt(self.root, "evolution_scout.md"),
            {
                "NOW": now.isoformat(),
                "USER_INTENT": _read(self.root / "docs/USER_INTENT.md", 30000),
                "MEMORY": self._memory(),
                "SNAPSHOT": self._snapshot(),
            },
        )
        cfg = self.settings.get("models", {}).get("scout", {})
        return self.llm.request_json(prompt, web=True, model_cfg=cfg)

    def _builder(self, scout: dict[str, Any]) -> dict[str, Any]:
        prompt = render_prompt(
            load_prompt(self.root, "evolution_builder.md"),
            {
                "SCOUT": json.dumps(scout, ensure_ascii=False, indent=2),
                "RULES": _read(self.root / "docs/EVOLUTION_RULES.md", 30000),
                "SNAPSHOT": self._snapshot(),
            },
        )
        cfg = self.settings.get("models", {}).get("builder", {})
        return self.llm.request_json(prompt, web=False, model_cfg=cfg)

    def _path_allowed(self, rel: str) -> tuple[bool, str]:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            return False, "저장소 밖 경로는 허용하지 않음"

        if rel in set(self.auto.get("protected_paths", [])):
            return False, "보호 파일"

        for prefix in self.auto.get("protected_prefixes", []):
            if rel.startswith(prefix):
                return False, "보호 경로"

        allowed_paths = set(self.auto.get("allowed_paths", []))
        allowed_prefix = any(rel.startswith(x) for x in self.auto.get("allowed_prefixes", []))
        if rel not in allowed_paths and not allowed_prefix:
            return False, "자동 수정 허용 경로가 아님"

        if p.suffix not in set(self.auto.get("allowed_extensions", [])):
            return False, "허용되지 않은 확장자"

        return True, ""

    def _validate_changes(self, builder: dict[str, Any]) -> tuple[bool, str]:
        changes = builder.get("changes", [])
        if not isinstance(changes, list):
            return False, "changes가 배열이 아님"
        if len(changes) > int(self.limits.get("max_changes_per_tick", 3)):
            return False, "한 Tick의 변경 파일 수 한도 초과"

        total = 0
        for item in changes:
            rel = str(item.get("path", ""))
            ok, why = self._path_allowed(rel)
            if not ok:
                return False, f"{rel}: {why}"
            content = item.get("content")
            if not isinstance(content, str):
                return False, f"{rel}: content가 문자열이 아님"
            total += len(content)

        if total > int(self.limits.get("max_total_changed_chars", 50000)):
            return False, "변경 문자 수 한도 초과"
        return True, ""

    def _apply_and_test(self, changes: list[dict[str, Any]]) -> tuple[bool, str]:
        backups: dict[str, str | None] = {}
        for item in changes:
            rel = str(item["path"])
            path = self.root / rel
            backups[rel] = _read(path) if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(item["content"]), encoding="utf-8")

        self._last_change_backup = dict(backups)

        try:
            for argv in self.validation.get("commands", []):
                if not isinstance(argv, list) or not argv:
                    raise RuntimeError("검증 명령 형식이 잘못됨")
                result = subprocess.run(
                    [str(x) for x in argv],
                    cwd=self.root,
                    text=True,
                    capture_output=True,
                    timeout=180,
                    check=False,
                )
                if result.returncode != 0:
                    detail = (result.stdout + "\n" + result.stderr)[-6000:]
                    raise RuntimeError(f"{' '.join(argv)} 실패\n{detail}")
            return True, "모든 검증 통과"
        except Exception as exc:
            for rel, old in backups.items():
                path = self.root / rel
                if old is None:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    path.write_text(old, encoding="utf-8")
            return False, str(exc)

    def _record_tick(
        self,
        now: datetime,
        scout: dict[str, Any],
        builder: dict[str, Any] | None,
        outcome: str,
        validation: str,
    ) -> None:
        day = _kst_label(now)[:10]
        path = self.root / "data" / "evolution" / "ticks" / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        item = {
            "timestamp_utc": now.isoformat(),
            "timestamp_kst": _kst_label(now),
            "scout": scout,
            "builder": builder,
            "outcome": outcome,
            "validation": validation,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _record_idea(self, now: datetime, scout: dict[str, Any], outcome: str) -> None:
        block = (
            f"## {_kst_label(now)} — {scout.get('title', '아이디어')}\n\n"
            f"상태: {scout.get('idea_status') or '재검토'}\n\n"
            f"분류: {scout.get('category', '기타')}\n\n"
            f"발견: {scout.get('observation', '')}\n\n"
            f"판단 근거: {scout.get('decision_basis', '')}\n\n"
            f"기대효과: {scout.get('expected_benefit', '')}\n\n"
            f"위험: {scout.get('risk', '')}\n\n"
            f"이번 처리: {outcome}\n"
        )
        _append(self.root / "docs/IDEAS.md", block)

    def _record_help(self, now: datetime, scout: dict[str, Any]) -> None:
        if not scout.get("needs_user"):
            return
        help_text = scout.get("user_help")
        if isinstance(help_text, dict):
            help_text = json.dumps(help_text, ensure_ascii=False, indent=2)
        block = (
            f"## {_kst_label(now)} — {scout.get('title', '사용자 도움 필요')}\n\n"
            f"상태: 사용자 작업 필요\n\n"
            f"필요 이유: {scout.get('observation', '')}\n\n"
            f"사용자가 해줄 일:\n\n{help_text or '구체적 작업이 아직 정의되지 않음'}\n"
        )
        _append(self.root / "docs/HELP_NEEDED.md", block)

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _record_change_manifest(
        self,
        now: datetime,
        scout: dict[str, Any],
        builder: dict[str, Any],
    ) -> str:
        raw_id = (
            now.strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + str(scout.get("title") or "change")
        )
        short = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:10]
        change_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + short

        files = []
        for item in builder.get("changes", []):
            rel = str(item.get("path") or "")
            after = str(item.get("content") or "")
            before = self._last_change_backup.get(rel)
            files.append(
                {
                    "path": rel,
                    "before_content": before,
                    "after_content": after,
                    "before_hash": (
                        self._hash_text(before) if before is not None else None
                    ),
                    "after_hash": self._hash_text(after),
                }
            )

        manifest = {
            "change_id": change_id,
            "applied_at": now.isoformat(),
            "title": scout.get("title"),
            "category": scout.get("category"),
            "risk": scout.get("risk"),
            "decision_basis": scout.get("decision_basis"),
            "expected_benefit": scout.get("expected_benefit"),
            "summary": builder.get("summary"),
            "paths": [x.get("path") for x in files],
            "files": files,
            "status": "active",
        }
        path = (
            self.root
            / "data"
            / "evolution"
            / "changes"
            / (change_id + ".json")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return change_id

    def _record_change(
        self,
        now: datetime,
        scout: dict[str, Any],
        builder: dict[str, Any],
        validation: str,
    ) -> None:
        paths = [x.get("path") for x in builder.get("changes", [])]
        change_id = self._record_change_manifest(now, scout, builder)
        changelog = (
            f"## {_kst_label(now)} — {scout.get('title', '자동 개선')}\n\n"
            f"- change_id: {change_id}\n"
            f"- 분류: {scout.get('category')}\n"
            f"- 변경: {', '.join(str(x) for x in paths)}\n"
            f"- 이유: {scout.get('decision_basis', '')}\n"
            f"- 기대효과: {scout.get('expected_benefit', '')}\n"
            f"- 검증: {validation}\n"
        )
        _append(self.root / "docs/CHANGELOG_AI.md", changelog)

        decision = (
            f"## {_kst_label(now)} — {scout.get('title', '자동 개선')}\n\n"
            f"상태: 도입\n\n"
            f"change_id: {change_id}\n\n"
            f"발견: {scout.get('observation', '')}\n\n"
            f"결정: {builder.get('summary', '')}\n\n"
            f"이유: {scout.get('decision_basis', '')}\n\n"
            f"기대효과: {scout.get('expected_benefit', '')}\n\n"
            f"위험: {scout.get('risk', '')}\n\n"
            f"검증: {validation}\n\n"
            f"다음 확인: {', '.join(str(x) for x in builder.get('followups', [])) or '없음'}\n"
        )
        _append(self.root / "docs/DECISIONS.md", decision)

    def run(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        scout = self._scout(now)
        decision = str(scout.get("decision", "no_change"))
        self._record_help(now, scout)

        if decision == "no_change":
            self._record_tick(now, scout, None, "no_change", "변경 없음")
            return {"decision": decision, "title": scout.get("title"), "changed": False}

        if decision == "proposal_only" or scout.get("risk") == "high":
            self._record_idea(now, scout, "자동 적용하지 않고 제안으로 보존")
            self._record_tick(now, scout, None, "proposal_only", "고위험 또는 제안 전용")
            return {"decision": "proposal_only", "title": scout.get("title"), "changed": False}

        builder = self._builder(scout)
        if builder.get("risk") == "high":
            reason = "Builder가 고위험 변경으로 분류함"
            self._record_idea(now, scout, reason)
            self._record_tick(now, scout, builder, "blocked", reason)
            return {"decision": "blocked", "title": scout.get("title"), "changed": False}

        if builder.get("blocked_reason"):
            reason = str(builder.get("blocked_reason"))
            self._record_idea(now, scout, f"Builder 보류: {reason}")
            self._record_tick(now, scout, builder, "blocked", reason)
            return {"decision": "blocked", "title": scout.get("title"), "changed": False}

        ok, reason = self._validate_changes(builder)
        if not ok:
            self._record_idea(now, scout, f"자동 변경 정책에 의해 차단: {reason}")
            self._record_tick(now, scout, builder, "blocked", reason)
            return {"decision": "blocked", "title": scout.get("title"), "changed": False}

        changes = builder.get("changes", [])
        if not changes:
            self._record_tick(
                now,
                scout,
                builder,
                "no_file_change",
                "Builder가 파일 변경이 필요 없다고 판단",
            )
            return {"decision": "no_file_change", "title": scout.get("title"), "changed": False}

        passed, validation = self._apply_and_test(changes)
        if passed:
            self._record_change(now, scout, builder, validation)
            outcome = "applied"
        else:
            self._record_idea(now, scout, f"검증 실패로 롤백: {validation}")
            experiment = (
                f"## {_kst_label(now)} — {scout.get('title', '자동 개선')}\n\n"
                f"가설: {scout.get('expected_benefit', '')}\n\n"
                f"변경: {builder.get('summary', '')}\n\n"
                f"평가 방법: 자동 검증 명령\n\n"
                f"결과: {validation}\n\n"
                f"판정: 롤백\n\n"
                f"배운 점: 현재 변경안은 검증을 통과하지 못했다. 같은 접근을 반복하지 말고 원인을 수정해야 한다.\n"
            )
            _append(self.root / "docs/EXPERIMENTS.md", experiment)
            outcome = "rolled_back"

        self._record_tick(now, scout, builder, outcome, validation)
        return {
            "decision": decision,
            "title": scout.get("title"),
            "changed": passed,
            "outcome": outcome,
        }
