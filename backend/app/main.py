from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.llm.mock import MockLlm
from app.adapters.storage.migrations import MigrationError, check_migrations
from app.adapters.storage.sqlite_event_store import SqliteEventStore
from app.application.chat import ChatService
from app.application.locks import SessionLocks
from app.application.safety import SafetyService
from app.config import settings
from app.domain.character import DEFAULT_CHARACTER
from app.domain.ports import LlmPort
from app.transport.http.chat import router as chat_router
from app.transport.http.health import router as health_router
from app.transport.http.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        check_migrations(settings.database_path)
    except MigrationError as exc:
        raise RuntimeError(f"数据库未就绪：{exc}") from exc
    yield


def create_app(*, llm: LlmPort | None = None) -> FastAPI:
    """Build the app.

    `llm` exists so tests can inject a failing or slow adapter; production
    wiring uses the MockLlm adapter until a real provider is chosen.
    """
    store = SqliteEventStore(settings.database_path)
    chat_service = ChatService(
        store=store,
        llm=llm or MockLlm(),
        safety=SafetyService(),
        character=DEFAULT_CHARACTER,
        timeout_seconds=settings.llm_timeout_seconds,
        max_context_turns=settings.max_context_turns,
    )

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.event_store = store
    app.state.chat_service = chat_service
    app.state.session_locks = SessionLocks()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    return app


app = create_app()
