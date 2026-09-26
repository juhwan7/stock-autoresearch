from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site" / "AI대화.html"
JS = ROOT / "site" / "기능.js"
GENERATOR = ROOT / "scripts" / "대시보드_생성.py"

def test_ai_dialogue_page_uses_real_supervisor_timeline():
    html = PAGE.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    assert 'id="ai-dialogue"' in html
    assert 'id="collaboration-headline"' in html
    assert 'id="collaboration-active"' in html
    assert 'id="collaboration-resolved"' in html
    assert 'id="collaboration-change"' in html
    assert 'id="collaboration-next"' in html
    assert "function renderAIDialogue(data)" in js
    assert "function renderAICollaboration(data)" in js
    assert "data.supervisor_collaboration" in js
    assert "data.supervisor_timeline" in js
    assert 'folder = ROOT / "data" / "supervisor" / "ai-results"' in generator
    assert "feedback_to_other_supervisor" in generator
    assert "supervisor_disagreements" in generator
    assert '"supervisor_collaboration"' in generator
    assert '"data" / "supervisor" / "collaboration.json"' in generator

def test_supervisor_timeline_is_latest_first_and_only_real_supervisor_roles():
    namespace = runpy.run_path(str(GENERATOR))
    rows = namespace["supervisor_timeline"](limit=80)
    times = [str(row.get("processed_at") or "") for row in rows]
    assert times == sorted(times, reverse=True)
    assert all(row.get("supervisor") in {"A", "B", "RECOVERY"} for row in rows)
    assert all(str(row.get("source_file", "")).startswith("data/supervisor/ai-results/") for row in rows)
