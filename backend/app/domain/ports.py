from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.domain.events import Event, EventDraft, Session


class LlmMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class LlmRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    messages: list[LlmMessage]
    max_tokens: int = 512


class EventStore(Protocol):
    async def create_session(self, session: Session, started: EventDraft) -> Event: ...

    async def get_session(self, session_id: str) -> Session | None: ...

    async def append(self, session_id: str, drafts: Sequence[EventDraft]) -> list[Event]:
        """Append drafts atomically, assigning contiguous seq values."""

    async def list_events(self, session_id: str) -> list[Event]: ...


class LlmPort(Protocol):
    @property
    def model(self) -> str: ...

    def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        """Yield reply text chunks. Errors are raised, never faked."""
