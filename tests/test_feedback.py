from autoresearch.feedback import build_telegram_payload, classify_feedback, feedback_fingerprint


def test_feedback_commands_are_classified():
    assert classify_feedback("좋아").kind == "positive"
    assert classify_feedback("보류").kind == "hold"
    assert classify_feedback("수정해줘: 알림을 짧게").kind == "modify_request"
    rollback = classify_feedback(
        "되돌려줘: 20260925T071500Z-abcdef1234"
    )
    assert rollback.kind == "rollback_request"
    assert rollback.priority == "urgent"
    assert rollback.change_id == "20260925T071500Z-abcdef1234"
    assert classify_feedback("아이디어: 종목별 페이지").kind == "idea"


def test_feedback_fingerprint_is_stable():
    first = feedback_fingerprint("juhwan7", 123, "좋아")
    second = feedback_fingerprint("juhwan7", 123, "좋아")
    third = feedback_fingerprint("juhwan7", 124, "좋아")
    assert first == second
    assert first != third



def test_telegram_payload_has_feedback_button():
    payload = build_telegram_payload(
        chat_id="1234",
        text="변경 알림",
        feedback_url="https://github.com/juhwan7/stock-autoresearch/issues/1",
        dashboard_url="https://juhwan7.github.io/stock-autoresearch/",
    )
    assert payload["chat_id"] == "1234"
    assert payload["text"] == "변경 알림"
    buttons = payload["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["text"] == "💬 바로 피드백"
    assert buttons[0]["url"].endswith("/issues/1")
    assert buttons[1]["text"] == "📊 대시보드"
