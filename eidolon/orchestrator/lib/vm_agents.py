from __future__ import annotations

import secrets
import sqlite3
import time

from pydantic import BaseModel

from .db import get_db, write_tx


class VMAgentError(Exception):
    """Raised when a VM-agent operation fails."""

    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(f"{status_code} {reason}")
        self.status_code = status_code
        self.reason = reason


class VMAgent(BaseModel):
    vm_token: str
    engagement_id: str
    vm_name: str
    registered_at: int
    last_heartbeat: int | None = None
    revoked: bool = False


def _row_to_agent(row: sqlite3.Row) -> VMAgent:
    return VMAgent(
        vm_token=row["vm_token"],
        engagement_id=row["engagement_id"],
        vm_name=row["vm_name"],
        registered_at=row["registered_at"],
        last_heartbeat=row["last_heartbeat"],
        revoked=bool(row["revoked"]),
    )


class VMAgentStore:
    """SQLite-backed registry of VM agents. One row per provisioned VM token."""

    def issue(self, *, engagement_id: str, vm_name: str) -> str:
        """Issue a fresh vm_token for a VM about to boot. Called by the
        orchestrator at provision-time, then injected into the VM via the
        substrate's secrets_inject."""
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with write_tx() as conn:
            row = conn.execute(
                "SELECT id FROM engagements WHERE id = ?", (engagement_id,)
            ).fetchone()
            if row is None:
                raise VMAgentError(404, "engagement_not_found")
            conn.execute(
                """
                INSERT INTO vm_agents (
                    vm_token, engagement_id, vm_name, registered_at
                ) VALUES (?, ?, ?, ?)
                """,
                (token, engagement_id, vm_name, now),
            )
        return token

    def register(self, vm_token: str, *, vm_name: str) -> VMAgent:
        """Called by the in-VM agent on boot to confirm registration. The
        token must already exist (issued at provision-time). vm_name must
        match the issued name (defense in depth against token reuse)."""
        with write_tx() as conn:
            row = conn.execute(
                "SELECT * FROM vm_agents WHERE vm_token = ?", (vm_token,)
            ).fetchone()
            if row is None:
                raise VMAgentError(401, "vm_token_invalid")
            if row["revoked"]:
                raise VMAgentError(401, "vm_token_revoked")
            if row["vm_name"] != vm_name:
                raise VMAgentError(403, "vm_name_mismatch")
            now = int(time.time())
            conn.execute(
                "UPDATE vm_agents SET last_heartbeat = ? WHERE vm_token = ?",
                (now, vm_token),
            )
            row = conn.execute(
                "SELECT * FROM vm_agents WHERE vm_token = ?", (vm_token,)
            ).fetchone()
            return _row_to_agent(row)

    def heartbeat(self, vm_token: str) -> VMAgent:
        with write_tx() as conn:
            row = conn.execute(
                "SELECT * FROM vm_agents WHERE vm_token = ?", (vm_token,)
            ).fetchone()
            if row is None:
                raise VMAgentError(401, "vm_token_invalid")
            if row["revoked"]:
                raise VMAgentError(401, "vm_token_revoked")
            now = int(time.time())
            conn.execute(
                "UPDATE vm_agents SET last_heartbeat = ? WHERE vm_token = ?",
                (now, vm_token),
            )
            row = conn.execute(
                "SELECT * FROM vm_agents WHERE vm_token = ?", (vm_token,)
            ).fetchone()
            return _row_to_agent(row)

    def lookup(self, vm_token: str) -> VMAgent | None:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM vm_agents WHERE vm_token = ?", (vm_token,)
        ).fetchone()
        return _row_to_agent(row) if row is not None else None

    def revoke(self, vm_token: str) -> bool:
        with write_tx() as conn:
            row = conn.execute(
                "SELECT * FROM vm_agents WHERE vm_token = ?", (vm_token,)
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE vm_agents SET revoked = 1 WHERE vm_token = ?", (vm_token,)
            )
            return True

    def list_for_engagement(self, engagement_id: str) -> list[VMAgent]:
        conn = get_db()
        rows = conn.execute(
            """
            SELECT * FROM vm_agents
            WHERE engagement_id = ?
            ORDER BY registered_at ASC
            """,
            (engagement_id,),
        ).fetchall()
        return [_row_to_agent(r) for r in rows]


_store = VMAgentStore()


def get_vm_agent_store() -> VMAgentStore:
    return _store
