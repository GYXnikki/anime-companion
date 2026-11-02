from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.adapters.storage.migrations import apply_migrations
from app.config import settings
from app.domain.ports import LlmPort
from app.main import create_app

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture
def app_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path, MIGRATIONS_DIR)
    monkeypatch.setattr(settings, "database_path", str(db_path))

    def factory(llm: LlmPort | None = None) -> FastAPI:
        return create_app(llm=llm)

    return factory


@pytest.fixture
def app(app_factory: Any) -> FastAPI:
    built: FastAPI = app_factory()
    return built


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
