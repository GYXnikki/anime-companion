import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

_FILENAME_PATTERN = re.compile(r"^(\d{4})_.+\.sql$")


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    path: Path


@dataclass(frozen=True)
class MigrationStatus:
    applied: tuple[int, ...]
    pending: tuple[int, ...]


def discover_migrations(
    migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
) -> tuple[Migration, ...]:
    base = Path(migrations_dir)
    if not base.is_dir():
        raise MigrationError(f"migration 目录不存在：{base}")

    migrations: list[Migration] = []
    seen: set[int] = set()
    for path in sorted(base.iterdir()):
        if path.suffix != ".sql":
            continue
        match = _FILENAME_PATTERN.match(path.name)
        if match is None:
            raise MigrationError(f"无法识别的 migration 文件名：{path.name}")
        version = int(match.group(1))
        if version in seen:
            raise MigrationError(f"migration 版本重复：{version}")
        seen.add(version)
        migrations.append(Migration(version=version, path=path))

    if not migrations:
        raise MigrationError(f"migration 目录为空：{base}")

    migrations.sort(key=lambda migration: migration.version)
    versions = [migration.version for migration in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f"migration 版本必须从 1 连续递增，当前：{versions}")
    return tuple(migrations)


def apply_migrations(
    db_path: Path | str,
    migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
) -> tuple[int, ...]:
    migrations = discover_migrations(migrations_dir)
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_migrations_table(conn)
        applied = _applied_versions(conn)
        _validate(applied, migrations)

        newly_applied: list[int] = []
        for migration in migrations:
            if migration.version in applied:
                continue
            _apply_one(conn, migration)
            newly_applied.append(migration.version)
        conn.execute("PRAGMA journal_mode = WAL")
        return tuple(newly_applied)
    finally:
        conn.close()


def migration_status(
    db_path: Path | str,
    migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
) -> MigrationStatus:
    migrations = discover_migrations(migrations_dir)
    path = Path(db_path)

    applied: tuple[int, ...] = ()
    if path.exists():
        conn = sqlite3.connect(path, isolation_level=None)
        try:
            applied = _applied_versions(conn)
        finally:
            conn.close()

    _validate(applied, migrations)
    pending = tuple(m.version for m in migrations if m.version not in applied)
    return MigrationStatus(applied=applied, pending=pending)


def check_migrations(
    db_path: Path | str,
    migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
) -> None:
    status = migration_status(db_path, migrations_dir)
    if status.pending:
        pending = ", ".join(str(version) for version in status.pending)
        raise MigrationError(
            f"数据库有 {len(status.pending)} 个待应用 migration（{pending}）。"
            "请在 backend/ 下运行 `uv run python -m app.cli migrate`。"
        )


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _applied_versions(conn: sqlite3.Connection) -> tuple[int, ...]:
    if not _has_table(conn, "schema_migrations"):
        return ()
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return tuple(int(row[0]) for row in rows)


def _validate(applied: tuple[int, ...], migrations: tuple[Migration, ...]) -> None:
    known = {migration.version for migration in migrations}
    missing = [version for version in applied if version not in known]
    if missing:
        raise MigrationError(f"数据库已应用但缺少对应 migration 文件：{missing}")
    expected = tuple(range(1, len(applied) + 1))
    if applied != expected:
        raise MigrationError(f"数据库中的 migration 记录不连续：{list(applied)}")


def _apply_one(conn: sqlite3.Connection, migration: Migration) -> None:
    statements = _split_statements(migration.path.read_text(encoding="utf-8"))
    conn.execute("BEGIN")
    try:
        for statement in statements:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (migration.version, _utc_now()),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _split_statements(sql: str) -> tuple[str, ...]:
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    remaining = buffer.strip()
    if remaining and not all(
        not line.strip() or line.strip().startswith("--") for line in remaining.splitlines()
    ):
        raise MigrationError("migration 文件末尾存在未闭合的 SQL 语句")
    return tuple(statements)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
