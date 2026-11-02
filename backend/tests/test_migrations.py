import sqlite3
from pathlib import Path

import pytest

from app.adapters.storage.migrations import (
    MigrationError,
    apply_migrations,
    check_migrations,
    migration_status,
)

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"


def test_apply_migrations_creates_core_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    applied = apply_migrations(db_path)

    assert len(applied) == 1
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"sessions", "events", "alembic_version"} <= tables


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    first = apply_migrations(db_path)
    second = apply_migrations(db_path)

    assert len(first) == 1
    assert second == ()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone() == (1,)


def test_migration_status_reports_current_and_head(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    before = migration_status(db_path)

    assert before.current is None
    assert before.head is not None
    assert before.pending is True
    assert not db_path.exists()

    apply_migrations(db_path)
    after = migration_status(db_path)

    assert after.current == after.head
    assert after.pending is False


def test_check_migrations_fails_when_database_is_not_migrated(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    with pytest.raises(MigrationError, match="app.cli migrate"):
        check_migrations(db_path)


def test_check_migrations_passes_after_migrate(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path)

    check_migrations(db_path)


def test_unknown_revision_is_reported(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'not-a-real-revision'")

    with pytest.raises(MigrationError, match="没有对应的 migration 文件"):
        migration_status(db_path)


def _describe_schema(conn: sqlite3.Connection) -> dict[str, object]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    description: dict[str, object] = {}
    for table in tables:
        columns = tuple(conn.execute(f"PRAGMA table_info({table})").fetchall())
        indexes = tuple(sorted(conn.execute(f"PRAGMA index_list({table})").fetchall()))
        foreign_keys = tuple(sorted(conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()))
        description[table] = (columns, indexes, foreign_keys)
    return description


def test_schema_sql_matches_applied_migrations(tmp_path: Path) -> None:
    migrated_db = tmp_path / "migrated.db"
    apply_migrations(migrated_db)

    declared_db = tmp_path / "declared.db"
    with sqlite3.connect(declared_db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

    with (
        sqlite3.connect(migrated_db) as migrated_conn,
        sqlite3.connect(declared_db) as declared_conn,
    ):
        assert _describe_schema(migrated_conn) == _describe_schema(declared_conn)
