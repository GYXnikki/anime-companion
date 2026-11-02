import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.application.chat import Delta, Done, TurnEvent
from app.transport.http.deps import ChatServiceDep, EventStoreDep, SessionLocksDep
from app.transport.http.schemas import SendMessageRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    service: ChatServiceDep,
    store: EventStoreDep,
    locks: SessionLocksDep,
) -> StreamingResponse:
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    if not locks.try_begin(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="session is already generating a reply",
        )

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.stream_turn(session_id, body.text):
                yield _render(event)
        except Exception:
            logger.exception("chat stream failed")
            yield _sse("error", {"code": "internal_error", "message": "服务暂时不可用，请重试"})
        finally:
            locks.end(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _render(event: TurnEvent) -> str:
    if isinstance(event, Delta):
        return _sse("delta", {"text": event.text})
    if isinstance(event, Done):
        return _sse("done", {"message_id": event.message_id, "interrupted": event.interrupted})
    return _sse("error", {"code": event.code, "message": event.message})


def _sse(name: str, data: dict[str, object]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
