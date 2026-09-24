from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def has_hangul(value: str) -> bool:
    return any("가" <= ch <= "힣" for ch in value)


def test_user_facing_docs_use_korean_filenames():
    for folder in ("docs", "prompts"):
        for path in (ROOT / folder).glob("*.md"):
            assert has_hangul(path.stem), (
                f"사용자가 직접 읽는 파일은 한글 파일명을 사용해야 합니다: {path}"
            )


def test_workflow_filenames_are_readable_in_korean():
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        assert has_hangul(path.stem), (
            f"워크플로 파일명은 한글로 표시해야 합니다: {path}"
        )


def test_config_and_scripts_use_korean_filenames():
    for path in (ROOT / "config").glob("*.yaml"):
        assert has_hangul(path.stem), (
            f"설정 파일은 한글 파일명을 사용해야 합니다: {path}"
        )
    for path in (ROOT / "scripts").glob("*.py"):
        assert has_hangul(path.stem), (
            f"운영 스크립트는 한글 파일명을 사용해야 합니다: {path}"
        )


def test_site_support_files_use_korean_filenames():
    allowed_standard = {"index.html"}
    for path in (ROOT / "site").iterdir():
        if not path.is_file() or path.name in allowed_standard:
            continue
        if path.suffix not in {".js", ".css"}:
            continue
        assert has_hangul(path.stem), (
            f"웹 보조 파일은 한글 파일명을 사용해야 합니다: {path}"
        )
