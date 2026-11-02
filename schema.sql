CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    character_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    last_seq INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    turn_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (session_id, seq)
);

CREATE INDEX idx_events_turn_id ON events (turn_id);

CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
