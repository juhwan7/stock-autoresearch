import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def markdown_files():
    yield ROOT / "README.md"
    yield from (ROOT / "docs").glob("*.md")


def test_internal_markdown_links_exist():
    missing = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for raw in LINK_RE.findall(text):
            target = raw.strip().split()[0].strip("<>")
            if (
                not target
                or target.startswith("#")
                or "://" in target
                or target.startswith("mailto:")
            ):
                continue
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                missing.append(f"{path.relative_to(ROOT)} -> {target} (저장소 밖)")
                continue
            if not resolved.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")

    assert not missing, "깨진 내부 Markdown 링크:\n" + "\n".join(missing)
