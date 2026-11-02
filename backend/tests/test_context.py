from app.application.context import build_context
from app.domain.character import DEFAULT_CHARACTER
from app.domain.events import ACTOR_BY_TYPE, Event, EventType

SESSION_ID = "session-1"
NOW = "2026-11-02T00:00:00.000Z"


def make_event(seq: int, event_type: EventType, payload: dict[str, object]) -> Event:
    return Event(
        id=f"event-{seq}",
        session_id=SESSION_ID,
        seq=seq,
        type=event_type,
        turn_id=None,
        actor=ACTOR_BY_TYPE[event_type],
        payload=payload,
        created_at=NOW,
    )


def turn_events(seq: int, user: str, reply: str) -> list[Event]:
    return [
        make_event(seq, "user.text", {"text": user}),
        make_event(
            seq + 1,
            "assistant.completed",
            {
                "content": reply,
                "model": "mock",
                "prompt_version": "v1",
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 1,
            },
        ),
    ]


def test_empty_history_keeps_only_the_system_prompt() -> None:
    messages = build_context([], DEFAULT_CHARACTER)

    assert len(messages) == 1
    assert messages[0].role == "system"
    assert DEFAULT_CHARACTER.name in messages[0].content


def test_single_turn_becomes_user_then_assistant() -> None:
    events = turn_events(1, "今天有点累", "听起来今天不太容易。")

    messages = build_context(events, DEFAULT_CHARACTER)

    assert [(m.role, m.content) for m in messages[1:]] == [
        ("user", "今天有点累"),
        ("assistant", "听起来今天不太容易。"),
    ]


def test_only_the_last_twenty_turns_are_kept() -> None:
    events: list[Event] = []
    for index in range(25):
        events.extend(turn_events(index * 2 + 1, f"u{index}", f"a{index}"))

    messages = build_context(events, DEFAULT_CHARACTER, max_turns=20)

    assert len(messages) == 1 + 40
    assert messages[1].content == "u5"
    assert messages[-2].content == "u24"
    assert messages[-1].content == "a24"


def test_failed_turn_keeps_user_text_without_assistant_reply() -> None:
    events = [
        make_event(1, "user.text", {"text": "在吗"}),
        make_event(2, "assistant.failed", {"code": "llm_error", "message": "boom"}),
    ]

    messages = build_context(events, DEFAULT_CHARACTER)

    assert [(m.role, m.content) for m in messages[1:]] == [("user", "在吗")]


def test_safety_response_is_part_of_history() -> None:
    events = [
        make_event(1, "user.text", {"text": "我不想活了"}),
        make_event(2, "safety.triggered", {"category": "self_harm", "matched_keyword": "不想活"}),
        make_event(3, "safety.responded", {"content": "请先保证安全", "hotline_shown": True}),
    ]

    messages = build_context(events, DEFAULT_CHARACTER)

    assert [(m.role, m.content) for m in messages[1:]] == [
        ("user", "我不想活了"),
        ("assistant", "请先保证安全"),
    ]
