from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints

from app.domain.events import MAX_USER_TEXT_LENGTH, Actor, EventType


class CreateSessionResponse(BaseModel):
    id: str
    character_id: str
    character_version: str
    created_at: str


class SendMessageRequest(BaseModel):
    text: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=MAX_USER_TEXT_LENGTH,
        ),
    ]


class EventResponse(BaseModel):
    id: str
    seq: int
    type: EventType
    turn_id: str | None
    actor: Actor
    payload: dict[str, Any]
    created_at: str


class EventsResponse(BaseModel):
    session_id: str
    events: list[EventResponse]
