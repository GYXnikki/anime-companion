import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite

from app.domain.errors import SessionNotFound
from app.domain.events import (
    ACTOR_BY_TYPE,
    PAYLOAD_MODELS,
    Event,
    EventDraft,
    EventType,
    Session,
    SessionStatus,
)
from app.shared.ids import new_ulid
from app.shared.time import utc_now_iso


class SqliteEventStore:
    """Event log backed by SQLite.

    Sequence numbers are assigned inside a `BEGIN IMMEDIATE` transaction, so a
    batch either lands completely or not at all.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(self._path, isolation_level=None)
        try:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA busy_timeout = 5000")
            yield conn
        finally:
            await conn.close()

    async def create_session(self, session: Session, started: EventDraft) -> Event:
        async with self._connect() as conn:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                await conn.execute(
                    """
                    INSERT INTO sessions (
                        id, character_id, character_version, status,
                        last_seq, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        session.id,
                        session.character_id,
                        session.character_version,
                        session.status,
                        session.created_at,
                        session.updated_at,
                    ),
                )
                events = await self._append_in_connection(conn, session.id, [started])
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise
        return events[0]

    async def get_session(self, session_id: str) -> Session | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, character_id, character_version, status, created_at, updated_at
                FROM sessions WHERE id = ?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return Session(
            id=cast(str, row["id"]),
            character_id=cast(str, row["character_id"]),
            character_version=cast(str, row["character_version"]),
            status=cast(SessionStatus, row["status"]),
            created_at=cast(str, row["created_at"]),
            updated_at=cast(str, row["updated_at"]),
        )

    async def append(self, session_id: str, drafts: Sequence[EventDraft]) -> list[Event]:
        if not drafts:
            return []
        async with self._connect() as conn:
            try:
                await conn.execute("BEGIN IMMEDIATE")
                events = await self._append_in_connection(conn, session_id, drafts)
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise
        return events

    async def list_events(self, session_id: str) -> list[Event]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, session_id, seq, type, turn_id, payload_json, created_at
                FROM events WHERE session_id = ? ORDER BY seq ASC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [_row_to_event(row) for row in rows]

    async def _append_in_connection(
        self,
        conn: aiosqlite.Connection,
        session_id: str,
        drafts: Sequence[EventDraft],
    ) -> list[Event]:
        cursor = await conn.execute(
            "SELECT last_seq FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise SessionNotFound(session_id)

        seq = int(row["last_seq"])
        created_at = utc_now_iso()
        events: list[Event] = []
        for draft in drafts:
            seq += 1
            event = Event(
                id=new_ulid(),
                session_id=session_id,
                seq=seq,
                type=draft.type,
                turn_id=draft.turn_id,
                actor=ACTOR_BY_TYPE[draft.type],
                payload=draft.payload,
                created_at=created_at,
            )
            await conn.execute(
                """
                INSERT INTO events (id, session_id, seq, type, turn_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    session_id,
                    seq,
                    event.type,
                    event.turn_id,
                    json.dumps(event.payload, ensure_ascii=False),
                    created_at,
                ),
            )
            events.append(event)

        await conn.execute(
            "UPDATE sessions SET last_seq = ?, updated_at = ? WHERE id = ?",
            (seq, created_at, session_id),
        )
        return events


def _row_to_event(row: aiosqlite.Row) -> Event:
    event_type = cast(EventType, row["type"])
    payload_model = PAYLOAD_MODELS.get(event_type)
    if payload_model is None:
        raise ValueError(f"unknown event type in database: {event_type}")
    payload = payload_model.model_validate(json.loads(cast(str, row["payload_json"]))).model_dump()
    return Event(
        id=cast(str, row["id"]),
        session_id=cast(str, row["session_id"]),
        seq=int(row["seq"]),
        type=event_type,
        turn_id=cast(str | None, row["turn_id"]),
        actor=ACTOR_BY_TYPE[event_type],
        payload=payload,
        created_at=cast(str, row["created_at"]),
    )
