from typing import Annotated, cast

from fastapi import Depends, Request

from app.application.chat import ChatService
from app.application.locks import SessionLocks
from app.domain.ports import EventStore


def get_chat_service(request: Request) -> ChatService:
    return cast(ChatService, request.app.state.chat_service)


def get_event_store(request: Request) -> EventStore:
    return cast(EventStore, request.app.state.event_store)


def get_session_locks(request: Request) -> SessionLocks:
    return cast(SessionLocks, request.app.state.session_locks)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
EventStoreDep = Annotated[EventStore, Depends(get_event_store)]
SessionLocksDep = Annotated[SessionLocks, Depends(get_session_locks)]
