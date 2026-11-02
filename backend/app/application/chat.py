import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.application.context import build_context
from app.application.safety import SAFETY_RESPONSE, SafetyHit, SafetyService
from app.domain.character import Character
from app.domain.events import (
    ErrorCode,
    Session,
    assistant_completed,
    assistant_failed,
    safety_responded,
    safety_triggered,
    session_started,
    user_text,
)
from app.domain.ports import EventStore, LlmPort, LlmRequest
from app.shared.ids import new_ulid
from app.shared.time import utc_now_iso

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "抱歉，我刚才没组织好语言，你能再说一遍吗？"

FAILURE_MESSAGES: dict[ErrorCode, str] = {
    "llm_timeout": "模型暂时不可用，请重试",
    "llm_error": "模型暂时不可用，请重试",
    "client_disconnected": "连接已断开",
    "internal_error": "服务暂时不可用，请重试",
}


@dataclass(frozen=True)
class Delta:
    text: str


@dataclass(frozen=True)
class Done:
    message_id: str
    interrupted: bool = False


@dataclass(frozen=True)
class Error:
    code: ErrorCode
    message: str


TurnEvent = Delta | Done | Error


class ChatService:
    def __init__(
        self,
        *,
        store: EventStore,
        llm: LlmPort,
        safety: SafetyService,
        character: Character,
        timeout_seconds: float,
        max_context_turns: int,
    ) -> None:
        self._store = store
        self._llm = llm
        self._safety = safety
        self._character = character
        self._timeout_seconds = timeout_seconds
        self._max_context_turns = max_context_turns
        self._background: set[asyncio.Task[None]] = set()

    async def create_session(self) -> Session:
        now = utc_now_iso()
        session = Session(
            id=new_ulid(),
            character_id=self._character.id,
            character_version=self._character.version,
            status="active",
            created_at=now,
            updated_at=now,
        )
        await self._store.create_session(
            session,
            session_started(
                character_id=self._character.id,
                character_version=self._character.version,
            ),
        )
        return session

    async def stream_turn(self, session_id: str, text: str) -> AsyncIterator[TurnEvent]:
        decision = self._safety.check(text)
        turn_id = new_ulid()

        if decision.hit is not None:
            async for event in self._safety_turn(session_id, text, turn_id, decision.hit):
                yield event
            return

        async for event in self._normal_turn(session_id, text, turn_id):
            yield event

    async def _safety_turn(
        self,
        session_id: str,
        text: str,
        turn_id: str,
        decision: SafetyHit,
    ) -> AsyncIterator[TurnEvent]:
        try:
            events = await self._store.append(
                session_id,
                [
                    user_text(text, turn_id=turn_id),
                    safety_triggered(
                        category=decision.category,
                        matched_keyword=decision.matched_keyword,
                        turn_id=turn_id,
                    ),
                    safety_responded(
                        content=SAFETY_RESPONSE,
                        hotline_shown=True,
                        turn_id=turn_id,
                    ),
                ],
            )
        except Exception:
            logger.exception("could not record safety response")
            yield Error(code="internal_error", message=FAILURE_MESSAGES["internal_error"])
            return

        yield Delta(text=SAFETY_RESPONSE)
        yield Done(message_id=events[-1].id)

    async def _normal_turn(
        self,
        session_id: str,
        text: str,
        turn_id: str,
    ) -> AsyncIterator[TurnEvent]:
        try:
            await self._store.append(session_id, [user_text(text, turn_id=turn_id)])
            events = await self._store.list_events(session_id)
            messages = build_context(
                events,
                self._character,
                max_turns=self._max_context_turns,
            )
        except Exception:
            logger.exception("could not prepare turn")
            yield Error(code="internal_error", message=FAILURE_MESSAGES["internal_error"])
            return

        content_parts: list[str] = []
        started_at = time.perf_counter()
        finished = False
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async for chunk in self._llm.stream(LlmRequest(messages=messages)):
                    if not chunk:
                        continue
                    content_parts.append(chunk)
                    yield Delta(text=chunk)

            content = "".join(content_parts).strip()
            if not content:
                content = FALLBACK_REPLY
                yield Delta(text=FALLBACK_REPLY)
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            try:
                completed = await self._store.append(
                    session_id,
                    [
                        assistant_completed(
                            content=content,
                            model=self._llm.model,
                            prompt_version=self._character.prompt_version,
                            latency_ms=latency_ms,
                            turn_id=turn_id,
                        )
                    ],
                )
            except Exception:
                logger.exception("could not record assistant.completed")
                yield Error(code="internal_error", message=FAILURE_MESSAGES["internal_error"])
                return
            finished = True
            yield Done(message_id=completed[0].id)
        except TimeoutError:
            await self._record_failure(session_id, turn_id, "llm_timeout")
            yield Error(code="llm_timeout", message=FAILURE_MESSAGES["llm_timeout"])
        except (GeneratorExit, asyncio.CancelledError):
            if not finished:
                self._schedule_failure(session_id, turn_id, "client_disconnected")
            raise
        except Exception:
            logger.exception("llm turn failed")
            await self._record_failure(session_id, turn_id, "llm_error")
            yield Error(code="llm_error", message=FAILURE_MESSAGES["llm_error"])

    async def _record_failure(self, session_id: str, turn_id: str, code: ErrorCode) -> None:
        try:
            await self._store.append(
                session_id,
                [
                    assistant_failed(
                        code=code,
                        message=FAILURE_MESSAGES[code],
                        turn_id=turn_id,
                    )
                ],
            )
        except Exception:
            logger.exception("could not record assistant.failed")

    def _schedule_failure(self, session_id: str, turn_id: str, code: ErrorCode) -> None:
        task = asyncio.create_task(self._record_failure(session_id, turn_id, code))
        self._background.add(task)
        task.add_done_callback(self._background.discard)
