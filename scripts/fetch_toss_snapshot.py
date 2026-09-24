from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


OUTPUT = Path("data/providers/toss/latest.json")
RUNTIME = Path("data/providers/toss/fetch_runtime.json")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def main() -> None:
    url = os.getenv("TOSS_SNAPSHOT_URL", "").strip()
    token = os.getenv("TOSS_SNAPSHOT_TOKEN", "").strip()
    if not url:
        write_json(
            RUNTIME,
            {
                "status": "not_configured",
                "fetched_at": datetime.now().astimezone().isoformat(),
            },
        )
        print("TOSS_SNAPSHOT_URL 미설정: fetch를 건너뜁니다.")
        return

    headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = "Bearer " + token

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("snapshot은 JSON 객체여야 합니다.")
        if not data.get("captured_at"):
            raise ValueError("captured_at이 없습니다.")
        if not isinstance(data.get("minute_by_ticker"), dict):
            raise ValueError("minute_by_ticker가 없습니다.")

        write_json(OUTPUT, data)
        write_json(
            RUNTIME,
            {
                "status": "ok",
                "fetched_at": datetime.now().astimezone().isoformat(),
                "captured_at": data.get("captured_at"),
                "provider": data.get("provider"),
                "subscribed_count": (
                    data.get("collector", {}).get("subscribed_count")
                    if isinstance(data.get("collector"), dict)
                    else None
                ),
            },
        )
        print(
            "Toss snapshot fetched:",
            data.get("captured_at"),
        )
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
        OSError,
    ) as exc:
        write_json(
            RUNTIME,
            {
                "status": "error",
                "fetched_at": datetime.now().astimezone().isoformat(),
                "error": str(exc)[:500],
            },
        )
        print("Toss snapshot fetch failed:", exc)
        # Kiwoom fallback과 Health Watchdog가 계속 실행되도록 non-strict.
        if os.getenv("TOSS_SNAPSHOT_STRICT") == "1":
            raise


if __name__ == "__main__":
    main()
