from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
ALEMBIC_DIR = BACKEND_ROOT / "alembic"


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class MigrationStatus:
    current: str | None
    head: str | None
    pending: bool


def apply_migrations(db_path: Path | str) -> tuple[str, ...]:
    """Upgrade the database to the latest revision, returning applied revisions."""
    config = _config(db_path)
    status = _status(config, Path(db_path))
    if status.head is None:
        raise MigrationError("Alembic 目录中没有可用的 migration")
    if not status.pending:
        return ()
    command.upgrade(config, "head")
    return (status.head,)


def migration_status(db_path: Path | str) -> MigrationStatus:
    return _status(_config(db_path), Path(db_path))


def check_migrations(db_path: Path | str) -> None:
    status = migration_status(db_path)
    if status.pending:
        raise MigrationError(
            f"数据库版本为 {status.current or '空'}，最新为 {status.head}。"
            "请在 backend/ 下运行 `uv run python -m app.cli migrate`。"
        )


def _config(db_path: Path | str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.attributes["database_path"] = str(Path(db_path))
    return config


def _status(config: Config, db_path: Path) -> MigrationStatus:
    head = _head_revision(config)
    current = _current_revision(db_path)
    if current is not None:
        _ensure_known(config, current)
    return MigrationStatus(current=current, head=head, pending=current != head)


def _head_revision(config: Config) -> str | None:
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) > 1:
        raise MigrationError(f"Alembic 存在多个 head，需要先合并：{heads}")
    return heads[0] if heads else None


def _current_revision(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _ensure_known(config: Config, revision: str) -> None:
    script = ScriptDirectory.from_config(config)
    try:
        script.get_revision(revision)
    except Exception as exc:
        raise MigrationError(f"数据库版本 {revision} 没有对应的 migration 文件") from exc
