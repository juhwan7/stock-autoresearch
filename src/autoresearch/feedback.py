from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


CHANGE_ID_RE = re.compile(r"\b\d{8}T\d{6}Z-[0-9a-f]{10}\b", re.IGNORECASE)


@dataclass(frozen=True)
class FeedbackClassification:
    kind: str
    priority: str
    change_id: str | None


def classify_feedback(body: str) -> FeedbackClassification:
    text = str(body or "").strip()
    compact = re.sub(r"\s+", " ", text)
    lower = compact.lower()
    match = CHANGE_ID_RE.search(compact)
    change_id = match.group(0) if match else None

    if lower.startswith(("되돌려줘", "롤백", "원복")):
        return FeedbackClassification("rollback_request", "urgent", change_id)
    if lower.startswith(("수정해줘", "변경해줘", "고쳐줘")):
        return FeedbackClassification("modify_request", "high", change_id)
    if lower.startswith(("보류", "멈춰", "하지마", "하지 마")):
        return FeedbackClassification("hold", "high", change_id)
    if lower.startswith(("아이디어", "제안")):
        return FeedbackClassification("idea", "normal", change_id)
    if lower in {"좋아", "유지", "승인", "괜찮아", "좋음", "계속"}:
        return FeedbackClassification("positive", "normal", change_id)
    return FeedbackClassification("freeform", "normal", change_id)


def extract_change_id(value: str) -> str | None:
    match = CHANGE_ID_RE.search(str(value or ""))
    return match.group(0) if match else None


def feedback_fingerprint(author: str, comment_id: str | int, body: str) -> str:
    raw = f"{author}|{comment_id}|{body}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def stable_event_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]



def build_telegram_payload(
    *,
    chat_id: str,
    text: str,
    feedback_url: str,
    dashboard_url: str,
) -> dict[str, Any]:
    return {
        "chat_id": str(chat_id),
        "text": str(text)[:4096],
        "link_preview_options": {"is_disabled": True},
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "💬 바로 피드백", "url": feedback_url},
                    {"text": "📊 대시보드", "url": dashboard_url},
                ]
            ]
        },
    }
