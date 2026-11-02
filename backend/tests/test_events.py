import pytest
from pydantic import ValidationError

from app.domain.events import (
    ACTOR_BY_TYPE,
    MAX_USER_TEXT_LENGTH,
    EventDraft,
    assistant_completed,
    assistant_failed,
    safety_responded,
    safety_triggered,
    user_text,
)


def test_every_event_type_has_a_single_actor() -> None:
    assert ACTOR_BY_TYPE == {
        "session.started": "system",
        "user.text": "user",
        "assistant.completed": "assistant",
        "assistant.failed": "assistant",
        "safety.triggered": "system",
        "safety.responded": "assistant",
    }


def test_user_text_rejects_empty_and_oversized_text() -> None:
    with pytest.raises(ValidationError):
        user_text("", turn_id="turn-1")
    with pytest.raises(ValidationError):
        user_text("x" * (MAX_USER_TEXT_LENGTH + 1), turn_id="turn-1")


def test_payload_must_match_event_type() -> None:
    with pytest.raises(ValidationError):
        EventDraft(type="user.text", payload={"content": "不是 text 字段"})
    with pytest.raises(ValidationError):
        EventDraft(type="assistant.failed", payload={"code": "not-a-code", "message": "x"})


def test_drafts_carry_turn_id() -> None:
    assert user_text("你好", turn_id="turn-1").turn_id == "turn-1"
    assert assistant_completed(
        content="在呢",
        model="mock",
        prompt_version="v1",
        turn_id="turn-1",
    ).turn_id == "turn-1"
    assert assistant_failed(code="llm_error", message="boom", turn_id="turn-1").turn_id == "turn-1"
    assert safety_triggered(
        category="self_harm",
        matched_keyword="自杀",
        turn_id="turn-1",
    ).turn_id == "turn-1"
    assert safety_responded(
        content="请先保证安全",
        hotline_shown=True,
        turn_id="turn-1",
    ).turn_id == "turn-1"
