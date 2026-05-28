from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ZERO_HASH = "0" * 64


class AuditEntry(BaseModel):
    seq: int
    ts: int
    event: str
    engagement_id: str | None = None
    operator_id: str | None = None
    action: str | None = None
    target: str | None = None
    tier: str | None = None
    dispatch_id: str | None = None
    authz_id: str | None = None
    jti: str | None = None
    reason: str | None = None
    prev_hash: str
    hash: str

    @staticmethod
    def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(prev_hash.encode() + body).hexdigest()


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _eidolon_home() -> Path:
    override = os.environ.get("EIDOLON_HOME")
    if override:
        return Path(override)
    return Path.home() / ".eidolon"


def _audit_dir() -> Path:
    root = _eidolon_home() / "audit"
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


class AuditChain:
    """Append-only hash-chained audit log. One JSONL file per UTC day."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._head: str | None = None
        self._seq: int | None = None

    def segment_path_for(self, day: date) -> Path:
        return _audit_dir() / f"audit-{day.isoformat()}.jsonl"

    def _segments_sorted(self) -> list[Path]:
        root = _audit_dir()
        return sorted(p for p in root.glob("audit-*.jsonl"))

    def _bootstrap(self) -> None:
        if self._head is not None and self._seq is not None:
            return
        segments = self._segments_sorted()
        if not segments:
            self._head = ZERO_HASH
            self._seq = 0
            return
        last = segments[-1]
        text = last.read_text().strip()
        if not text:
            tail_hash = ZERO_HASH
            tail_seq = 0
            for prev in reversed(segments[:-1]):
                prev_text = prev.read_text().strip()
                if prev_text:
                    last_line = prev_text.splitlines()[-1]
                    obj = json.loads(last_line)
                    tail_hash = obj["hash"]
                    tail_seq = obj["seq"]
                    break
            self._head = tail_hash
            self._seq = tail_seq
            return
        last_line = text.splitlines()[-1]
        obj = json.loads(last_line)
        self._head = obj["hash"]
        self._seq = obj["seq"]

    def head(self) -> str:
        with self._lock:
            self._bootstrap()
            if self._head is None:
                raise RuntimeError("audit chain bootstrap failed")
            return self._head

    def current_seq(self) -> int:
        with self._lock:
            self._bootstrap()
            if self._seq is None:
                raise RuntimeError("audit chain bootstrap failed")
            return self._seq

    def append(self, event_name: str, **fields: Any) -> AuditEntry:
        with self._lock:
            self._bootstrap()
            if self._head is None or self._seq is None:
                raise RuntimeError("audit chain bootstrap failed")
            seq = self._seq + 1
            allowed = set(AuditEntry.model_fields.keys()) - {"seq", "ts", "event", "prev_hash", "hash"}
            payload: dict[str, Any] = {
                "seq": seq,
                "ts": int(time.time()),
                "event": event_name,
                "prev_hash": self._head,
            }
            for k, v in fields.items():
                if k in allowed and v is not None:
                    payload[k] = v
            for k in allowed:
                payload.setdefault(k, None)
            entry_hash = AuditEntry.compute_hash(self._head, payload)
            entry = AuditEntry(**payload, hash=entry_hash)

            seg = self.segment_path_for(_utc_today())
            line = json.dumps(
                entry.model_dump(), sort_keys=True, separators=(",", ":")
            ) + "\n"
            fd = os.open(
                seg,
                os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                0o600,
            )
            try:
                os.write(fd, line.encode())
            finally:
                os.close(fd)

            self._head = entry.hash
            self._seq = seq
            return entry

    def verify(self, path: Path) -> tuple[bool, int | None]:
        if not path.exists():
            return False, None
        text = path.read_text()
        if not text.strip():
            return True, None
        prev_hash = ZERO_HASH
        first_seq: int | None = None
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                return False, None
            if first_seq is None:
                first_seq = entry["seq"]
                expected_seq = first_seq
            if entry["seq"] != expected_seq:
                return False, entry["seq"]
            if first_seq == 1 and entry["seq"] == 1 and entry["prev_hash"] != ZERO_HASH:
                return False, entry["seq"]
            payload = {k: v for k, v in entry.items() if k != "hash"}
            recomputed = AuditEntry.compute_hash(entry["prev_hash"], payload)
            if recomputed != entry["hash"]:
                return False, entry["seq"]
            if entry["seq"] > 1 and entry["prev_hash"] != prev_hash and prev_hash != ZERO_HASH:
                return False, entry["seq"]
            prev_hash = entry["hash"]
            expected_seq += 1
        return True, None

    def reset(self) -> None:
        with self._lock:
            self._head = None
            self._seq = None


_chain: AuditChain | None = None
_chain_lock = threading.Lock()


def get_audit_chain() -> AuditChain:
    global _chain
    with _chain_lock:
        if _chain is None:
            _chain = AuditChain()
        return _chain


def reset_audit_chain() -> None:
    global _chain
    with _chain_lock:
        _chain = None


def emit_audit(event_name: str, **fields: Any) -> AuditEntry:
    return get_audit_chain().append(event_name, **fields)
