from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_risk_dirty_state_logic_files_exist():
    cfg = load_yaml(ROOT / "config" / "리스크.yaml")
    missing = [
        rel
        for rel in cfg.get("dirty_state", {}).get("logic_files", [])
        if not (ROOT / rel).exists()
    ]
    assert not missing, "Risk dirty-state가 존재하지 않는 파일을 감시함: " + ", ".join(missing)


def test_evolution_protected_paths_exist():
    cfg = load_yaml(ROOT / "config" / "자기진화.yaml")
    missing = [
        rel
        for rel in cfg.get("auto_apply", {}).get("protected_paths", [])
        if not (ROOT / rel).exists()
    ]
    assert not missing, "자기진화 보호경로가 실제 파일명과 불일치함: " + ", ".join(missing)
