from fastapi import APIRouter, HTTPException, status

from app.transport.http.deps import ChatServiceDep, EventStoreDep
from app.transport.http.schemas import (
    CreateSessionResponse,
    EventResponse,
    EventsResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(service: ChatServiceDep) -> CreateSessionResponse:
    session = await service.create_session()
    return CreateSessionResponse(
        id=session.id,
        character_id=session.character_id,
        character_version=session.character_version,
        created_at=session.created_at,
    )


@router.get("/{session_id}/events")
async def list_events(session_id: str, store: EventStoreDep) -> EventsResponse:
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    events = await store.list_events(session_id)
    return EventsResponse(
        session_id=session_id,
        events=[EventResponse(**event.model_dump()) for event in events],
    )
