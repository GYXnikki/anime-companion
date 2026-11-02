import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.storage.database import create_database_engine, create_session_factory
from app.adapters.storage.tables import EventRow, SessionRow
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
    """Event log backed by SQLite through SQLAlchemy.

    Every write runs inside a transaction that begins with `BEGIN IMMEDIATE`
    (see `create_database_engine`), so a batch either lands completely or not
    at all and `seq` can never be handed out twice.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._engine = create_database_engine(self.database_path)
        self._session_factory: async_sessionmaker[AsyncSession] = create_session_factory(
            self._engine
        )

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def create_session(self, session: Session, started: EventDraft) -> Event:
        async with self._session_factory() as db, db.begin():
            db.add(
                SessionRow(
                    id=session.id,
                    character_id=session.character_id,
                    character_version=session.character_version,
                    status=session.status,
                    last_seq=0,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )
            await db.flush()
            events = await self._append(db, session.id, [started])
        return events[0]

    async def get_session(self, session_id: str) -> Session | None:
        async with self._session_factory() as db:
            row = await db.get(SessionRow, session_id)
            return None if row is None else _to_session(row)

    async def append(self, session_id: str, drafts: Sequence[EventDraft]) -> list[Event]:
        if not drafts:
            return []
        async with self._session_factory() as db, db.begin():
            events = await self._append(db, session_id, drafts)
        return events

    async def list_events(self, session_id: str) -> list[Event]:
        async with self._session_factory() as db:
            result = await db.execute(
                select(EventRow)
                .where(EventRow.session_id == session_id)
                .order_by(EventRow.seq.asc())
            )
            rows = result.scalars().all()
            return [_to_event(row) for row in rows]

    async def _append(
        self,
        db: AsyncSession,
        session_id: str,
        drafts: Sequence[EventDraft],
    ) -> list[Event]:
        row = await db.get(SessionRow, session_id)
        if row is None:
            raise SessionNotFound(session_id)

        seq = row.last_seq
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
            db.add(
                EventRow(
                    id=event.id,
                    session_id=session_id,
                    seq=seq,
                    type=event.type,
                    turn_id=event.turn_id,
                    payload_json=json.dumps(event.payload, ensure_ascii=False),
                    created_at=created_at,
                )
            )
            events.append(event)

        row.last_seq = seq
        row.updated_at = created_at
        return events


def _to_session(row: SessionRow) -> Session:
    return Session(
        id=row.id,
        character_id=row.character_id,
        character_version=row.character_version,
        status=cast(SessionStatus, row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_event(row: EventRow) -> Event:
    event_type = cast(EventType, row.type)
    payload_model = PAYLOAD_MODELS.get(event_type)
    if payload_model is None:
        raise ValueError(f"unknown event type in database: {event_type}")
    payload = payload_model.model_validate(json.loads(row.payload_json)).model_dump()
    return Event(
        id=row.id,
        session_id=row.session_id,
        seq=row.seq,
        type=event_type,
        turn_id=row.turn_id,
        actor=ACTOR_BY_TYPE[event_type],
        payload=payload,
        created_at=row.created_at,
    )
