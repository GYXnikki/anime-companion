from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_USER_TEXT_LENGTH = 2000

EventType = Literal[
    "session.started",
    "user.text",
    "assistant.completed",
    "assistant.failed",
    "safety.triggered",
    "safety.responded",
]
Actor = Literal["user", "assistant", "system"]
ErrorCode = Literal["llm_timeout", "llm_error", "client_disconnected", "internal_error"]
SafetyCategory = Literal["self_harm"]
SessionStatus = Literal["active", "closed"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SessionStartedPayload(BaseModel):
    model_config = _FROZEN

    character_id: str
    character_version: str


class UserTextPayload(BaseModel):
    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=MAX_USER_TEXT_LENGTH)


class AssistantCompletedPayload(BaseModel):
    model_config = _FROZEN

    content: str = Field(min_length=1)
    model: str
    prompt_version: str
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)


class AssistantFailedPayload(BaseModel):
    model_config = _FROZEN

    code: ErrorCode
    message: str = Field(min_length=1)


class SafetyTriggeredPayload(BaseModel):
    model_config = _FROZEN

    category: SafetyCategory
    matched_keyword: str = Field(min_length=1)


class SafetyRespondedPayload(BaseModel):
    model_config = _FROZEN

    content: str = Field(min_length=1)
    hotline_shown: bool


PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    "session.started": SessionStartedPayload,
    "user.text": UserTextPayload,
    "assistant.completed": AssistantCompletedPayload,
    "assistant.failed": AssistantFailedPayload,
    "safety.triggered": SafetyTriggeredPayload,
    "safety.responded": SafetyRespondedPayload,
}

ACTOR_BY_TYPE: dict[EventType, Actor] = {
    "session.started": "system",
    "user.text": "user",
    "assistant.completed": "assistant",
    "assistant.failed": "assistant",
    "safety.triggered": "system",
    "safety.responded": "assistant",
}


class EventDraft(BaseModel):
    """An event before the store assigns id, seq and created_at.

    The payload is validated against the model registered for `type`, so an
    invalid payload can never reach the database.
    """

    model_config = ConfigDict(frozen=True)

    type: EventType
    turn_id: str | None = None
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _payload_matches_type(self) -> "EventDraft":
        PAYLOAD_MODELS[self.type].model_validate(self.payload)
        return self


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    session_id: str
    seq: int
    type: EventType
    turn_id: str | None
    actor: Actor
    payload: dict[str, Any]
    created_at: str


class Session(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    character_id: str
    character_version: str
    status: SessionStatus
    created_at: str
    updated_at: str


def session_started(*, character_id: str, character_version: str) -> EventDraft:
    return EventDraft(
        type="session.started",
        payload=SessionStartedPayload(
            character_id=character_id,
            character_version=character_version,
        ).model_dump(),
    )


def user_text(text: str, *, turn_id: str) -> EventDraft:
    return EventDraft(
        type="user.text",
        turn_id=turn_id,
        payload=UserTextPayload(text=text).model_dump(),
    )


def assistant_completed(
    *,
    content: str,
    model: str,
    prompt_version: str,
    turn_id: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
) -> EventDraft:
    return EventDraft(
        type="assistant.completed",
        turn_id=turn_id,
        payload=AssistantCompletedPayload(
            content=content,
            model=model,
            prompt_version=prompt_version,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        ).model_dump(),
    )


def assistant_failed(*, code: ErrorCode, message: str, turn_id: str) -> EventDraft:
    return EventDraft(
        type="assistant.failed",
        turn_id=turn_id,
        payload=AssistantFailedPayload(code=code, message=message).model_dump(),
    )


def safety_triggered(
    *, category: SafetyCategory, matched_keyword: str, turn_id: str
) -> EventDraft:
    return EventDraft(
        type="safety.triggered",
        turn_id=turn_id,
        payload=SafetyTriggeredPayload(
            category=category,
            matched_keyword=matched_keyword,
        ).model_dump(),
    )


def safety_responded(*, content: str, hotline_shown: bool, turn_id: str) -> EventDraft:
    return EventDraft(
        type="safety.responded",
        turn_id=turn_id,
        payload=SafetyRespondedPayload(content=content, hotline_shown=hotline_shown).model_dump(),
    )
