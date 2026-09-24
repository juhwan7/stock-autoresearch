from autoresearch.llm import extract_json


def test_extract_plain_json():
    assert extract_json('{"ok": true}') == {"ok": True}


def test_extract_fenced_json():
    value = """```json
{"ok": true, "n": 1}
```"""
    assert extract_json(value) == {"ok": True, "n": 1}


def test_extract_json_from_wrapped_text():
    value = 'prefix text {"ok": true} suffix text'
    assert extract_json(value) == {"ok": True}
