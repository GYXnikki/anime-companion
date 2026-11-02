import sqlite3
from pathlib import Path

import pytest

from app.adapters.storage.migrations import (
    MigrationError,
    apply_migrations,
    check_migrations,
    migration_status,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"


def test_apply_migrations_creates_core_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    applied = apply_migrations(db_path, MIGRATIONS_DIR)

    assert applied == (1,)
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"sessions", "events", "schema_migrations"} <= tables


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    assert apply_migrations(db_path, MIGRATIONS_DIR) == (1,)
    assert apply_migrations(db_path, MIGRATIONS_DIR) == ()

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
    assert count == (1,)


def test_migration_status_reports_applied_and_pending(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    before = migration_status(db_path, MIGRATIONS_DIR)

    assert before.applied == ()
    assert before.pending == (1,)
    assert not db_path.exists()

    apply_migrations(db_path, MIGRATIONS_DIR)
    after = migration_status(db_path, MIGRATIONS_DIR)

    assert after.applied == (1,)
    assert after.pending == ()


def test_check_migrations_fails_when_database_is_not_migrated(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"

    with pytest.raises(MigrationError, match="app.cli migrate"):
        check_migrations(db_path, MIGRATIONS_DIR)


def test_check_migrations_passes_after_migrate(tmp_path: Path) -> None:
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path, MIGRATIONS_DIR)

    check_migrations(db_path, MIGRATIONS_DIR)


def test_check_migrations_fails_when_applied_file_is_missing(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    for name in ("0001_init.sql", "0002_extra.sql"):
        (migrations_dir / name).write_text("SELECT 1;\n", encoding="utf-8")
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path, migrations_dir)

    (migrations_dir / "0002_extra.sql").unlink()

    with pytest.raises(MigrationError, match="缺少对应 migration 文件"):
        check_migrations(db_path, migrations_dir)


def test_check_migrations_fails_when_versions_have_a_gap(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    for name in ("0001_init.sql", "0003_extra.sql"):
        (migrations_dir / name).write_text("SELECT 1;\n", encoding="utf-8")

    with pytest.raises(MigrationError, match="连续"):
        check_migrations(tmp_path / "anime_companion.db", migrations_dir)


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
    apply_migrations(migrated_db, MIGRATIONS_DIR)

    declared_db = tmp_path / "declared.db"
    with sqlite3.connect(declared_db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

    with (
        sqlite3.connect(migrated_db) as migrated_conn,
        sqlite3.connect(declared_db) as declared_conn,
    ):
        assert _describe_schema(migrated_conn) == _describe_schema(declared_conn)
