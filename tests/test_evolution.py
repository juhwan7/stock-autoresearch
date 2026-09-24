from pathlib import Path

from autoresearch.evolution import EvolutionEngine


def make_engine(tmp_path: Path) -> EvolutionEngine:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "evolution.yaml").write_text(
        """
limits:
  max_changes_per_tick: 2
  max_total_changed_chars: 1000
auto_apply:
  allowed_prefixes: [docs/, src/autoresearch/]
  protected_paths: [src/autoresearch/evolution.py]
  protected_prefixes: [.github/workflows/]
  allowed_extensions: [.md, .py]
validation:
  commands: []
""",
        encoding="utf-8",
    )
    (tmp_path / "config" / "research.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "scoring.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "sources.yaml").write_text("{}", encoding="utf-8")
    return EvolutionEngine(tmp_path, "dry-run")


def test_protected_path_blocked(tmp_path):
    engine = make_engine(tmp_path)
    ok, reason = engine._path_allowed("src/autoresearch/evolution.py")
    assert not ok
    assert "보호" in reason


def test_safe_docs_path_allowed(tmp_path):
    engine = make_engine(tmp_path)
    ok, reason = engine._path_allowed("docs/NEW_IDEA.md")
    assert ok
    assert reason == ""


def test_change_limit(tmp_path):
    engine = make_engine(tmp_path)
    ok, reason = engine._validate_changes(
        {
            "changes": [
                {"path": "docs/a.md", "content": "a"},
                {"path": "docs/b.md", "content": "b"},
                {"path": "docs/c.md", "content": "c"},
            ]
        }
    )
    assert not ok
    assert "한도" in reason
