from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.storage.migrations import apply_migrations
from app.config import settings
from app.main import create_app

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


async def test_startup_fails_when_database_is_not_migrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "missing.db"))
    app = create_app()

    with pytest.raises(RuntimeError, match="app.cli migrate"):
        async with app.router.lifespan_context(app):
            pass


async def test_startup_succeeds_when_database_is_migrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path, MIGRATIONS_DIR)
    monkeypatch.setattr(settings, "database_path", str(db_path))
    app = create_app()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
