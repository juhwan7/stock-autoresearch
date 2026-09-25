from autoresearch.capability_requests import capability_request


def test_capability_request_uses_minimum_permissions_without_secret_values():
    scout = {
        "needs_user": True,
        "expected_benefit": "속보 탐지 지연 감소",
        "external_capability": {
            "service": "Example News API",
            "purpose": "공식 속보 탐지",
            "credentials_needed": ["EXAMPLE_API_KEY"],
            "minimum_permissions": ["read:news"],
            "cost": "unknown",
            "setup_location": "GitHub Actions Repository secrets",
            "can_prepare_before_credentials": True,
        },
    }
    result = capability_request(scout)
    assert result["service"] == "Example News API"
    assert result["minimum_permissions"] == ["read:news"]
    assert result["credentials_needed"] == ["EXAMPLE_API_KEY"]
    assert result["secret_values_must_not_be_logged"] is True


def test_capability_request_skips_when_user_not_needed():
    assert capability_request({"needs_user": False}) is None
