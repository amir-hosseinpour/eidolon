from __future__ import annotations

import time

from .db import get_db, write_tx


class RevocationStore:
    """SQLite-backed scope-token revocation list.

    Backed by the `revoked` column on `scope_tokens`. A JTI never inserted
    via `attach_jti` is treated as not-revoked (default behaviour).
    """

    def revoke(self, jti: str) -> None:
        now = int(time.time())
        with write_tx() as conn:
            conn.execute(
                "UPDATE scope_tokens SET revoked = 1, revoked_at = ? WHERE jti = ?",
                (now, jti),
            )

    def is_revoked(self, jti: str) -> bool:
        conn = get_db()
        row = conn.execute(
            "SELECT revoked FROM scope_tokens WHERE jti = ?", (jti,)
        ).fetchone()
        if row is None:
            return False
        return bool(row["revoked"])

    def reset(self) -> None:
        with write_tx() as conn:
            conn.execute("UPDATE scope_tokens SET revoked = 0, revoked_at = NULL")


_singleton: RevocationStore | None = None


def get_revocation_store() -> RevocationStore:
    global _singleton
    if _singleton is None:
        _singleton = RevocationStore()
    return _singleton
