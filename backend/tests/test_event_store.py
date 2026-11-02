import json
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.adapters.storage import sqlite_event_store as store_module
from app.adapters.storage.migrations import apply_migrations
from app.adapters.storage.sqlite_event_store import SqliteEventStore
from app.domain.errors import SessionNotFound
from app.domain.events import Session, session_started, user_text
from app.shared.ids import new_ulid

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
NOW = "2026-11-02T00:00:00.000Z"


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteEventStore]:
    db_path = tmp_path / "anime_companion.db"
    apply_migrations(db_path)
    event_store = SqliteEventStore(db_path)
    yield event_store
    await event_store.dispose()


def make_session() -> Session:
    return Session(
        id=new_ulid(),
        character_id="default",
        character_version="v1",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


async def create_session(store: SqliteEventStore) -> Session:
    session = make_session()
    await store.create_session(
        session,
        session_started(character_id="default", character_version="v1"),
    )
    return session


async def test_create_session_writes_session_started(store: SqliteEventStore) -> None:
    session = await create_session(store)

    events = await store.list_events(session.id)
    stored = await store.get_session(session.id)

    assert [event.type for event in events] == ["session.started"]
    assert events[0].seq == 1
    assert events[0].turn_id is None
    assert events[0].actor == "system"
    assert stored is not None
    assert stored.id == session.id
    assert stored.character_id == "default"
    assert stored.updated_at == events[0].created_at


async def test_batch_append_assigns_contiguous_seq(store: SqliteEventStore) -> None:
    session = await create_session(store)
    turn_id = new_ulid()

    events = await store.append(
        session.id,
        [
            user_text("第一句", turn_id=turn_id),
            user_text("第二句", turn_id=turn_id),
            user_text("第三句", turn_id=turn_id),
        ],
    )

    assert [event.seq for event in events] == [2, 3, 4]
    assert {event.turn_id for event in events} == {turn_id}
    assert [event.seq for event in await store.list_events(session.id)] == [1, 2, 3, 4]
    assert (await store.get_session(session.id)).updated_at == events[-1].created_at


async def test_append_to_missing_session_writes_nothing(store: SqliteEventStore) -> None:
    with pytest.raises(SessionNotFound):
        await store.append("missing", [user_text("你好", turn_id=new_ulid())])

    assert await store.list_events("missing") == []


async def test_batch_append_rolls_back_on_partial_failure(
    store: SqliteEventStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = await create_session(store)
    monkeypatch.setattr(store_module, "new_ulid", lambda: "01DUPLICATED0000000000000")

    with pytest.raises(IntegrityError):
        await store.append(
            session.id,
            [user_text("一", turn_id=new_ulid()), user_text("二", turn_id=new_ulid())],
        )

    assert [event.type for event in await store.list_events(session.id)] == ["session.started"]
    with sqlite3.connect(store.database_path) as conn:
        row = conn.execute(
            "SELECT last_seq FROM sessions WHERE id = ?", (session.id,)
        ).fetchone()
    assert row == (1,)


async def test_concurrent_appends_do_not_reuse_seq(store: SqliteEventStore) -> None:
    session = await create_session(store)

    await _append_many(store, session.id, 5)

    events = await store.list_events(session.id)
    assert [event.seq for event in events] == list(range(1, len(events) + 1))


async def _append_many(store: SqliteEventStore, session_id: str, count: int) -> None:
    import asyncio

    await asyncio.gather(
        *[
            store.append(session_id, [user_text(f"m{index}", turn_id=new_ulid())])
            for index in range(count)
        ]
    )


async def test_payload_is_stored_as_readable_json(store: SqliteEventStore) -> None:
    session = await create_session(store)

    events = await store.append(session.id, [user_text("今天有点累", turn_id=new_ulid())])

    with sqlite3.connect(store.database_path) as conn:
        raw = conn.execute(
            "SELECT payload_json FROM events WHERE id = ?", (events[0].id,)
        ).fetchone()
    assert raw is not None
    assert json.loads(raw[0]) == {"text": "今天有点累"}
