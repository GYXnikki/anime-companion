from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def create_database_engine(database_path: str | Path) -> AsyncEngine:
    url = URL.create("sqlite+aiosqlite", database=str(database_path))
    engine = create_async_engine(
        url,
        connect_args={"isolation_level": None},
        poolclass=NullPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_connection(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _begin_immediate(conn: Connection) -> None:
        # SQLite needs the write lock before reading last_seq; a deferred
        # transaction can fail when upgrading while another writer committed.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
