from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .config import load_yaml
from .scoring import quality_average


KST = timezone(timedelta(hours=9))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _health_score(status: str) -> float:
    return {
        "OK": 100.0,
        "INFO": 98.0,
        "NOTICE": 90.0,
        "WARN": 70.0,
        "CRITICAL": 20.0,
    }.get(status, 60.0)


class RegressionDetector:
    """AI 변경 뒤 품질 악화를 장기 기준선과 비교한다.

    git reset을 사용하지 않는다. Evolution manifest에 저장한 변경 전 파일만
    복원하므로 독립적인 이후 작업은 보존한다.
    """

    def __init__(self, root: Path):
        self.root = root
        self.cfg = load_yaml(root / "config" / "회귀탐지.yaml")
        data = self.cfg.get("data", {})
        self.history_dir = root / data.get(
            "history_dir", "data/regression/history"
        )
        self.latest_path = root / data.get(
            "latest_file", "data/regression/latest.json"
        )
        self.quarantine_path = root / data.get(
            "quarantine_file", "data/regression/quarantine.json"
        )
        self.changes_dir = root / data.get(
            "changes_dir", "data/evolution/changes"
        )

    def _latest_research_quality(self) -> float | None:
        runs = self.root / "data" / "runs"
        if not runs.exists():
            return None
        for path in sorted(runs.glob("*.json"), reverse=True)[:30]:
            data = _read_json(path)
            if data.get("mode") != "live":
                continue
            scores = []
            for topic in data.get("topics", []):
                final = topic.get("final", {})
                if final.get("quality_score"):
                    scores.append(quality_average(final))
            if scores:
                return round(mean(scores), 2)
        return None

    def _data_completeness(self) -> float:
        parts: list[float] = []

        market = _read_json(self.root / "data" / "market" / "latest.json")
        if market:
            parts.append(
                100.0
                if market.get("quantitative", {}).get("status") == "ok"
                else 50.0
            )

        macro = _read_json(self.root / "data" / "macro" / "current.json")
        values = macro.get("values", {})
        if values:
            total = len(values)
            known = sum(1 for value in values.values() if value not in (None, ""))
            parts.append(100.0 * known / total if total else 0.0)

        risk = _read_json(self.root / "data" / "risk" / "latest.json")
        if risk:
            calendar = risk.get("upcoming_events")
            parts.append(100.0 if isinstance(calendar, list) else 50.0)

        return round(mean(parts), 2) if parts else 0.0

    def capture_snapshot(self, now: datetime) -> dict[str, Any]:
        health = _read_json(self.root / "data" / "health" / "latest.json")
        research_quality = self._latest_research_quality()
        health_score = _health_score(str(health.get("status") or "UNKNOWN"))
        completeness = self._data_completeness()

        weights = self.cfg.get("quality", {}).get("weights", {})
        components = {
            "health": health_score,
            "data_completeness": completeness,
        }
        if research_quality is not None:
            components["research_quality"] = research_quality

        weighted = 0.0
        total_weight = 0.0
        for key, value in components.items():
            weight = float(weights.get(key, 0.0))
            weighted += float(value) * weight
            total_weight += weight
        overall = round(weighted / total_weight, 2) if total_weight else 0.0

        return {
            "timestamp": now.astimezone(timezone.utc).isoformat(),
            "overall_quality": overall,
            "research_quality": research_quality,
            "health_score": health_score,
            "data_completeness": completeness,
            "health_status": health.get("status"),
        }

    def _append_snapshot(self, snapshot: dict[str, Any]) -> None:
        now = _parse_time(snapshot.get("timestamp")) or datetime.now(timezone.utc)
        path = self.history_dir / (now.strftime("%Y-%m-%d") + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    def _history(self, now: datetime, days: int) -> list[dict[str, Any]]:
        start = now - timedelta(days=days)
        rows: list[dict[str, Any]] = []
        if not self.history_dir.exists():
            return rows
        for path in sorted(self.history_dir.glob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                stamp = _parse_time(item.get("timestamp"))
                if stamp is not None and start <= stamp <= now:
                    rows.append(item)
        return rows

    @staticmethod
    def _avg(rows: list[dict[str, Any]], field: str) -> float | None:
        values = [
            float(row[field])
            for row in rows
            if row.get(field) not in (None, "")
        ]
        return round(mean(values), 2) if values else None

    def _change_manifests(self) -> list[tuple[Path, dict[str, Any]]]:
        if not self.changes_dir.exists():
            return []
        result = []
        for path in sorted(self.changes_dir.glob("*.json")):
            data = _read_json(path)
            if data:
                result.append((path, data))
        return result

    def _later_overlap(
        self,
        target: dict[str, Any],
        manifests: list[tuple[Path, dict[str, Any]]],
    ) -> list[str]:
        applied = _parse_time(target.get("applied_at"))
        if applied is None:
            return []
        paths = set(target.get("paths", []))
        overlaps: set[str] = set()
        for _, item in manifests:
            if item.get("change_id") == target.get("change_id"):
                continue
            when = _parse_time(item.get("applied_at"))
            if when is None or when <= applied:
                continue
            if item.get("status", "active") not in {"active", "quarantined"}:
                continue
            overlaps.update(paths & set(item.get("paths", [])))
        return sorted(overlaps)

    def _current_hash_mismatches(
        self,
        manifest: dict[str, Any],
    ) -> list[str]:
        mismatches = []
        for change in manifest.get("files", []):
            path = self.root / str(change.get("path"))
            expected = change.get("after_hash")
            current = _file_hash(path)
            if current != expected:
                mismatches.append(str(change.get("path")))
        return mismatches

    def _restore_manifest(
        self,
        manifest_path: Path,
        manifest: dict[str, Any],
        now: datetime,
        reason: str,
    ) -> list[str]:
        restored = []
        for change in manifest.get("files", []):
            rel = str(change.get("path"))
            path = self.root / rel
            before = change.get("before_content")
            if before is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(before), encoding="utf-8")
            restored.append(rel)

        manifest["status"] = "rolled_back_regression"
        manifest["rolled_back_at"] = now.isoformat()
        manifest["rollback_reason"] = reason
        _write_json(manifest_path, manifest)

        experiment = self.root / "docs" / "실험_기록.md"
        experiment.parent.mkdir(parents=True, exist_ok=True)
        with experiment.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n## REG-"
                + now.strftime("%Y%m%d-%H%M")
                + " — "
                + str(manifest.get("title") or manifest.get("change_id"))
                + "\n\n"
                + "가설: 자동 적용 변경이 장기 품질을 개선해야 한다.\n\n"
                + "변경: "
                + ", ".join(restored)
                + "\n\n"
                + "평가 방법: 변경 전 7일/30일 기준선과 변경 후 품질 비교.\n\n"
                + "결과: "
                + reason
                + "\n\n"
                + "판정: 기능 단위 롤백\n\n"
                + "배운 점: 저장소 전체를 되돌리지 않고 해당 변경의 파일만 복원했다.\n"
            )
        return restored

    def _quarantine(
        self,
        manifest_path: Path,
        manifest: dict[str, Any],
        reason: str,
    ) -> None:
        manifest["status"] = "quarantined"
        manifest["quarantine_reason"] = reason
        _write_json(manifest_path, manifest)

        current = _read_json(self.quarantine_path)
        items = current.get("items", [])
        if not any(
            x.get("change_id") == manifest.get("change_id") for x in items
        ):
            items.append(
                {
                    "change_id": manifest.get("change_id"),
                    "title": manifest.get("title"),
                    "paths": manifest.get("paths", []),
                    "reason": reason,
                }
            )
        _write_json(self.quarantine_path, {"items": items[-100:]})

    def _evaluate_change(
        self,
        manifest_path: Path,
        manifest: dict[str, Any],
        history: list[dict[str, Any]],
        now: datetime,
        manifests: list[tuple[Path, dict[str, Any]]],
    ) -> dict[str, Any]:
        applied = _parse_time(manifest.get("applied_at"))
        if applied is None:
            return {"status": "invalid_manifest"}
        if manifest.get("status", "active") != "active":
            return {"status": str(manifest.get("status"))}

        grace = float(self.cfg.get("windows", {}).get("grace_hours", 6))
        if now < applied + timedelta(hours=grace):
            return {"status": "grace_period"}

        post_hours = float(
            self.cfg.get("windows", {}).get("post_change_hours", 24)
        )
        post_end = min(now, applied + timedelta(hours=post_hours))
        post = [
            row
            for row in history
            if applied <= (_parse_time(row.get("timestamp")) or applied)
            <= post_end
        ]

        min_samples = self.cfg.get("minimum_samples", {})
        if len(post) < int(min_samples.get("post_change", 6)):
            return {"status": "collecting_post", "post_samples": len(post)}

        before_7 = [
            row
            for row in history
            if applied - timedelta(days=7)
            <= (_parse_time(row.get("timestamp")) or applied)
            < applied
        ]
        before_30 = [
            row
            for row in history
            if applied - timedelta(days=30)
            <= (_parse_time(row.get("timestamp")) or applied)
            < applied
        ]

        enough7 = len(before_7) >= int(min_samples.get("baseline_7d", 12))
        enough30 = len(before_30) >= int(min_samples.get("baseline_30d", 24))
        baseline7 = self._avg(before_7, "overall_quality")
        baseline30 = self._avg(before_30, "overall_quality")
        post_overall = self._avg(post, "overall_quality")
        research7 = self._avg(before_7, "research_quality")
        research30 = self._avg(before_30, "research_quality")
        post_research = self._avg(post, "research_quality")

        result = {
            "status": "evaluated",
            "change_id": manifest.get("change_id"),
            "baseline_7d": baseline7,
            "baseline_30d": baseline30,
            "post_overall": post_overall,
            "research_7d": research7,
            "research_30d": research30,
            "post_research": post_research,
            "samples": {
                "baseline_7d": len(before_7),
                "baseline_30d": len(before_30),
                "post": len(post),
            },
        }

        if not enough7:
            result["status"] = "collecting_7d_baseline"
            return result

        thresholds = self.cfg.get("thresholds", {})
        drop7 = (
            baseline7 - post_overall
            if baseline7 is not None and post_overall is not None
            else None
        )
        drop30 = (
            baseline30 - post_overall
            if baseline30 is not None and post_overall is not None
            else None
        )
        research_ref = research30 if research30 is not None else research7
        research_drop = (
            research_ref - post_research
            if research_ref is not None and post_research is not None
            else None
        )
        result.update(
            {
                "drop_7d": drop7,
                "drop_30d": drop30,
                "research_drop": research_drop,
            }
        )

        bad7 = drop7 is not None and drop7 >= float(
            thresholds.get("overall_drop_7d", 8)
        )
        bad30 = enough30 and drop30 is not None and drop30 >= float(
            thresholds.get("overall_drop_30d", 8)
        )
        research_bad = (
            research_drop is not None
            and research_drop >= float(
                thresholds.get("research_quality_drop", 8)
            )
        )
        severe = drop7 is not None and drop7 >= float(
            thresholds.get("severe_overall_drop", 15)
        )

        rollback_cfg = self.cfg.get("rollback", {})
        require_both = bool(
            rollback_cfg.get("require_both_baselines", True)
        )
        regression = bad7 and ((bad30 and enough30) if require_both else True)
        if bool(rollback_cfg.get("require_research_quality_drop", True)):
            regression = regression and research_bad

        if not regression:
            if severe and not enough30:
                reason = (
                    f"7일 대비 품질 {drop7:.2f}p 악화. "
                    "30일 기준선이 부족해 자동 롤백하지 않고 격리."
                )
                self._quarantine(manifest_path, manifest, reason)
                result["status"] = "quarantined"
                result["reason"] = reason
            else:
                result["status"] = "no_regression"
            return result

        overlaps = self._later_overlap(manifest, manifests)
        mismatches = self._current_hash_mismatches(manifest)
        blockers = []
        if overlaps and rollback_cfg.get("block_on_later_path_overlap", True):
            blockers.append("이후 변경과 경로 겹침: " + ", ".join(overlaps))
        if mismatches and rollback_cfg.get(
            "block_on_current_hash_mismatch", True
        ):
            blockers.append("현재 파일이 도입 직후 상태와 다름: " + ", ".join(mismatches))

        reason = (
            f"7일 대비 {drop7:.2f}p, 30일 대비 {drop30:.2f}p, "
            f"리서치 품질 {research_drop:.2f}p 악화"
        )
        if blockers:
            full = reason + ". 자동 롤백 차단: " + " / ".join(blockers)
            self._quarantine(manifest_path, manifest, full)
            result["status"] = "quarantined"
            result["reason"] = full
            return result

        if not rollback_cfg.get("enabled", True):
            self._quarantine(manifest_path, manifest, reason)
            result["status"] = "quarantined"
            result["reason"] = reason
            return result

        restored = self._restore_manifest(
            manifest_path,
            manifest,
            now,
            reason,
        )
        result["status"] = "rolled_back"
        result["restored_paths"] = restored
        result["reason"] = reason
        return result

    def run(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        snapshot = self.capture_snapshot(now)
        self._append_snapshot(snapshot)

        history_days = int(
            self.cfg.get("windows", {}).get("baseline_30d_days", 30)
        )
        history = self._history(now, history_days)
        manifests = self._change_manifests()

        evaluations = []
        rollback_limit = int(
            self.cfg.get("rollback", {}).get("max_per_tick", 1)
        )
        rolled_back = 0

        for path, manifest in reversed(manifests):
            result = self._evaluate_change(
                path,
                manifest,
                history,
                now,
                manifests,
            )
            evaluations.append(result)
            if result.get("status") == "rolled_back":
                rolled_back += 1
                if rolled_back >= rollback_limit:
                    break

        rolling_7d = [
            row
            for row in history
            if (_parse_time(row.get("timestamp")) or now)
            >= now - timedelta(days=7)
        ]
        rolling_30d = history
        baseline_summary = {
            "overall_7d": self._avg(rolling_7d, "overall_quality"),
            "overall_30d": self._avg(rolling_30d, "overall_quality"),
            "research_7d": self._avg(rolling_7d, "research_quality"),
            "research_30d": self._avg(rolling_30d, "research_quality"),
            "samples_7d": len(rolling_7d),
            "samples_30d": len(rolling_30d),
        }

        status = "OK"
        if any(x.get("status") == "rolled_back" for x in evaluations):
            status = "ROLLED_BACK"
        elif any(x.get("status") == "quarantined" for x in evaluations):
            status = "QUARANTINED"
        elif (
            not manifests
            or baseline_summary["samples_7d"]
            < int(self.cfg.get("minimum_samples", {}).get("baseline_7d", 12))
            or any(
                str(x.get("status", "")).startswith("collecting")
                for x in evaluations
            )
        ):
            status = "COLLECTING"

        latest = {
            "generated_at": now.isoformat(),
            "status": status,
            "snapshot": snapshot,
            "baseline_summary": baseline_summary,
            "evaluations": evaluations[:20],
            "active_change_count": sum(
                1
                for _, x in manifests
                if x.get("status", "active") == "active"
            ),
            "quarantine_count": sum(
                1
                for _, x in manifests
                if x.get("status") == "quarantined"
            ),
            "rolled_back_count": sum(
                1
                for _, x in manifests
                if x.get("status") == "rolled_back_regression"
            ),
        }
        _write_json(self.latest_path, latest)
        return latest
