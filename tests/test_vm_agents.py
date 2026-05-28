from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eidolon.orchestrator.lib.engagements import EngagementStore
from eidolon.orchestrator.lib.scope import ScopeDocument
from eidolon.orchestrator.lib.secrets import SecretsBroker
from eidolon.orchestrator.lib.vm_agents import VMAgentError, get_vm_agent_store
from eidolon.vm_agent.main import (
    AgentConfig,
    OrchestratorClient,
    SocketServer,
)


def _make_engagement() -> str:
    eng = EngagementStore().create(
        slug="vm-test",
        purpose="pentest",
        scope=ScopeDocument(
            allowed_cidrs=["10.42.0.0/24"],
            allowed_actions=["recon.read"],
            tier="confirm",
        ),
    )
    return eng.id


def test_issue_then_register_succeeds() -> None:
    eid = _make_engagement()
    store = get_vm_agent_store()
    token = store.issue(engagement_id=eid, vm_name="kali")
    agent = store.register(token, vm_name="kali")
    assert agent.engagement_id == eid
    assert agent.vm_name == "kali"
    assert agent.last_heartbeat is not None


def test_register_with_wrong_vm_name_fails() -> None:
    eid = _make_engagement()
    store = get_vm_agent_store()
    token = store.issue(engagement_id=eid, vm_name="kali")
    with pytest.raises(VMAgentError) as exc:
        store.register(token, vm_name="other")
    assert exc.value.status_code == 403


def test_register_with_unknown_token_fails() -> None:
    store = get_vm_agent_store()
    with pytest.raises(VMAgentError) as exc:
        store.register("not-a-real-token", vm_name="kali")
    assert exc.value.status_code == 401


def test_revoke_blocks_subsequent_register_and_heartbeat() -> None:
    eid = _make_engagement()
    store = get_vm_agent_store()
    token = store.issue(engagement_id=eid, vm_name="kali")
    assert store.revoke(token) is True
    with pytest.raises(VMAgentError) as exc:
        store.register(token, vm_name="kali")
    assert exc.value.status_code == 401
    with pytest.raises(VMAgentError):
        store.heartbeat(token)


def test_heartbeat_updates_timestamp() -> None:
    eid = _make_engagement()
    store = get_vm_agent_store()
    token = store.issue(engagement_id=eid, vm_name="kali")
    store.register(token, vm_name="kali")
    first = store.lookup(token)
    assert first is not None
    time.sleep(1.1)
    store.heartbeat(token)
    second = store.lookup(token)
    assert second is not None
    assert second.last_heartbeat is not None
    assert first.last_heartbeat is not None
    assert second.last_heartbeat >= first.last_heartbeat


# REST tests


def test_rest_register_and_secret_proxy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EIDOLON_SECRETS_BACKEND", "env")
    SecretsBroker().put("api_key", "topsecret")

    eng_resp = client.post(
        "/v1/engagements/start",
        json={
            "slug": "vm-rest",
            "purpose": "pentest",
            "scope": {
                "allowed_cidrs": ["10.42.0.0/24"],
                "allowed_actions": ["recon.read"],
                "tier": "confirm",
            },
        },
    )
    engagement_id = eng_resp.json()["engagement_id"]
    vm_token = get_vm_agent_store().issue(engagement_id=engagement_id, vm_name="kali")

    headers = {"Authorization": f"Bearer {vm_token}"}
    reg = client.post(
        "/v1/vm-agent/register", json={"vm_name": "kali"}, headers=headers
    )
    assert reg.status_code == 200, reg.text
    assert reg.json()["agent"]["vm_name"] == "kali"

    hb = client.post("/v1/vm-agent/heartbeat", headers=headers)
    assert hb.status_code == 200, hb.text

    sec = client.post(
        "/v1/vm-agent/secrets", json={"label": "api_key"}, headers=headers
    )
    assert sec.status_code == 200, sec.text
    assert sec.json()["value"] == "topsecret"


def test_rest_register_rejects_missing_token(client: TestClient) -> None:
    resp = client.post("/v1/vm-agent/register", json={"vm_name": "kali"})
    assert resp.status_code == 401


def test_rest_secret_proxy_404_when_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EIDOLON_SECRETS_BACKEND", "env")
    eng_resp = client.post(
        "/v1/engagements/start",
        json={
            "slug": "vm-rest-2",
            "purpose": "pentest",
            "scope": {
                "allowed_cidrs": ["10.42.0.0/24"],
                "allowed_actions": ["recon.read"],
                "tier": "confirm",
            },
        },
    )
    engagement_id = eng_resp.json()["engagement_id"]
    vm_token = get_vm_agent_store().issue(engagement_id=engagement_id, vm_name="kali")
    headers = {"Authorization": f"Bearer {vm_token}"}
    client.post("/v1/vm-agent/register", json={"vm_name": "kali"}, headers=headers)
    resp = client.post(
        "/v1/vm-agent/secrets",
        json={"label": "no_such_secret"},
        headers=headers,
    )
    assert resp.status_code == 404


# In-VM agent: socket integration with a fake OrchestratorClient


class _FakeClient:
    def __init__(self) -> None:
        self.secrets = {"api_key": "topsecret"}

    def fetch_secret(self, label: str) -> str:
        if label not in self.secrets:
            raise RuntimeError("not_found")
        return self.secrets[label]


def _request(socket_path: Path, payload: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.0)
    s.connect(str(socket_path))
    s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    chunks: list[bytes] = []
    while True:
        b = s.recv(4096)
        if not b:
            break
        chunks.append(b)
        if b.endswith(b"\n"):
            break
    s.close()
    raw = b"".join(chunks).decode("utf-8").strip()
    return json.loads(raw)


def test_socket_server_responds_to_ping_and_get_secret(tmp_path: Path) -> None:
    short_dir = Path(tempfile.mkdtemp(prefix="eag-", dir="/tmp"))  # noqa: S108
    sock_path = short_dir / "a.sock"
    config = AgentConfig(
        orchestrator_url="http://unused",
        vm_token="t",  # noqa: S106
        vm_name="kali",
        socket_path=sock_path,
        verify_tls=True,
    )
    fake_client = _FakeClient()
    server = SocketServer(OrchestratorClient(config), sock_path)
    server.client = fake_client  # type: ignore[assignment]
    server.start()

    serve_thread = threading.Thread(target=server.serve_forever, daemon=True)
    serve_thread.start()

    try:
        ping = _request(sock_path, {"op": "ping"})
        assert ping["ok"] is True
        assert "pong" in ping

        secret = _request(sock_path, {"op": "get_secret", "label": "api_key"})
        assert secret == {"ok": True, "value": "topsecret"}

        bad = _request(sock_path, {"op": "get_secret", "label": "missing"})
        assert bad["ok"] is False

        unknown = _request(sock_path, {"op": "weird"})
        assert unknown["ok"] is False
    finally:
        server.stop()
        serve_thread.join(timeout=2.0)


def test_socket_server_rejects_oversized_request(tmp_path: Path) -> None:
    short_dir = Path(tempfile.mkdtemp(prefix="eag-", dir="/tmp"))  # noqa: S108
    sock_path = short_dir / "a.sock"
    config = AgentConfig(
        orchestrator_url="http://unused",
        vm_token="t",  # noqa: S106
        vm_name="kali",
        socket_path=sock_path,
        verify_tls=True,
    )
    server = SocketServer(OrchestratorClient(config), sock_path)
    server.client = _FakeClient()  # type: ignore[assignment]
    server.start()

    serve_thread = threading.Thread(target=server.serve_forever, daemon=True)
    serve_thread.start()

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(str(sock_path))
        big = b"x" * (128 * 1024)
        try:
            s.sendall(big)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # server may close mid-write after refusal
        # Server should refuse and close.
        try:
            buf = b""
            while True:
                part = s.recv(4096)
                if not part:
                    break
                buf += part
                if b"\n" in buf:
                    break
            response = json.loads(buf.decode("utf-8").strip())
            assert response["ok"] is False
        finally:
            s.close()
    finally:
        server.stop()
        serve_thread.join(timeout=2.0)
