from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS engagements (
    id                  TEXT PRIMARY KEY,
    slug                TEXT NOT NULL,
    purpose             TEXT NOT NULL,
    status              TEXT NOT NULL,
    scope_json          TEXT NOT NULL,
    created_at          INTEGER NOT NULL,
    closed_at           INTEGER,
    erased_at           INTEGER,
    audit_head_at_open  TEXT NOT NULL,
    audit_head_at_close TEXT,
    notes_json          TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS scope_tokens (
    jti           TEXT PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagements(id),
    tier          TEXT NOT NULL,
    issued_at     INTEGER NOT NULL,
    expires_at    INTEGER NOT NULL,
    revoked       INTEGER NOT NULL DEFAULT 0,
    revoked_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_scope_tokens_engagement ON scope_tokens(engagement_id);

CREATE TABLE IF NOT EXISTS dispatches (
    id            TEXT PRIMARY KEY,
    engagement_id TEXT NOT NULL,
    jti           TEXT,
    tool_id       TEXT NOT NULL,
    target        TEXT,
    action        TEXT NOT NULL,
    tier          TEXT NOT NULL,
    accepted      INTEGER NOT NULL,
    reason        TEXT,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dispatches_engagement ON dispatches(engagement_id);

CREATE TABLE IF NOT EXISTS forks (
    id            TEXT PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagements(id),
    fork_type     TEXT NOT NULL,
    status        TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    context_json  TEXT NOT NULL DEFAULT '{}',
    created_at    INTEGER NOT NULL,
    resolved_at   INTEGER,
    resolved_by   TEXT,
    resolution    TEXT,
    rationale     TEXT
);
CREATE INDEX IF NOT EXISTS idx_forks_engagement ON forks(engagement_id);
CREATE INDEX IF NOT EXISTS idx_forks_status ON forks(status);

CREATE TABLE IF NOT EXISTS vm_agents (
    vm_token        TEXT PRIMARY KEY,
    engagement_id   TEXT NOT NULL REFERENCES engagements(id),
    vm_name         TEXT NOT NULL,
    registered_at   INTEGER NOT NULL,
    last_heartbeat  INTEGER,
    revoked         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_vm_agents_engagement ON vm_agents(engagement_id);

CREATE TABLE IF NOT EXISTS engagement_networks (
    engagement_id  TEXT PRIMARY KEY REFERENCES engagements(id),
    substrate_name TEXT NOT NULL,
    driver         TEXT NOT NULL,
    handle_id      TEXT NOT NULL,
    name           TEXT NOT NULL,
    cidr           TEXT,
    created_at     INTEGER NOT NULL,
    destroyed_at   INTEGER
);

CREATE TABLE IF NOT EXISTS engagement_vms (
    handle_id      TEXT PRIMARY KEY,
    engagement_id  TEXT NOT NULL REFERENCES engagements(id),
    vm_name        TEXT NOT NULL,
    driver         TEXT NOT NULL,
    network        TEXT NOT NULL,
    address        TEXT,
    vm_token       TEXT NOT NULL REFERENCES vm_agents(vm_token),
    template_name  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'provisioned',
    created_at     INTEGER NOT NULL,
    destroyed_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_engagement_vms_engagement ON engagement_vms(engagement_id);
"""

_conn: sqlite3.Connection | None = None
_conn_path: Path | None = None
_conn_lock = threading.Lock()
_write_lock = threading.Lock()


def _eidolon_home() -> Path:
    override = os.environ.get("EIDOLON_HOME")
    if override:
        return Path(override)
    return Path.home() / ".eidolon"


def state_db_path() -> Path:
    return _eidolon_home() / "state.db"


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def get_db() -> sqlite3.Connection:
    global _conn, _conn_path
    db_path = state_db_path()
    with _conn_lock:
        if _conn is None or _conn_path != db_path:
            if _conn is not None:
                _conn.close()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(db_path.parent, 0o700)
            conn = sqlite3.connect(
                db_path,
                check_same_thread=False,
                isolation_level=None,
                timeout=5.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            _init_schema(conn)
            _conn = conn
            _conn_path = db_path
        return _conn


@contextmanager
def write_tx() -> Iterator[sqlite3.Connection]:
    """Serialize writes through a process-local lock + explicit transaction."""
    conn = get_db()
    with _write_lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


def reset_db() -> None:
    global _conn, _conn_path
    with _conn_lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _conn_path = None
