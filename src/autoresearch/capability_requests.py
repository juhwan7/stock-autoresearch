from __future__ import annotations

from typing import Any


def capability_request(scout: dict[str, Any]) -> dict[str, Any] | None:
    """Scout가 사용자 승인/자격증명을 요구할 때 안전한 요청 카드로 정규화한다."""
    if not scout.get("needs_user"):
        return None
    ext = scout.get("external_capability") or {}
    service = str(ext.get("service") or "").strip()
    purpose = str(ext.get("purpose") or scout.get("expected_benefit") or "").strip()
    credentials = [str(x) for x in ext.get("credentials_needed", []) if x]
    permissions = [str(x) for x in ext.get("minimum_permissions", []) if x]
    if not service and not credentials and not permissions:
        return None
    return {
        "type": "external_capability_request",
        "service": service or "unspecified",
        "purpose": purpose,
        "credentials_needed": credentials,
        "minimum_permissions": permissions,
        "cost": ext.get("cost"),
        "setup_location": ext.get("setup_location"),
        "can_prepare_before_credentials": bool(ext.get("can_prepare_before_credentials")),
        "status": "waiting_for_user",
        "secret_values_must_not_be_logged": True,
    }
