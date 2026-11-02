from app.application.safety import SAFETY_RESPONSE, SafetyService


def test_plain_crisis_text_triggers() -> None:
    decision = SafetyService().check("我不想活了")

    assert decision.triggered is True
    assert decision.hit is not None
    assert decision.hit.category == "self_harm"


def test_whitespace_and_zero_width_are_ignored() -> None:
    decision = SafetyService().check("我 不 想\u200b活 了")

    assert decision.triggered is True


def test_ordinary_sadness_does_not_trigger() -> None:
    decision = SafetyService().check("今天上班好累，想早点睡")

    assert decision.triggered is False
    assert decision.hit is None


def test_safety_response_is_fixed_and_does_not_ask_for_details() -> None:
    assert "120" in SAFETY_RESPONSE
    assert "AI" in SAFETY_RESPONSE
    assert "？" not in SAFETY_RESPONSE
