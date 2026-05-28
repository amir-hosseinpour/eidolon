"""Eidolon in-VM agent.

Lightweight daemon baked into engagement-VM templates. Responsibilities:

1. Register the VM with the orchestrator using the provisioned EIDOLON_VM_TOKEN.
2. Heartbeat to the orchestrator on a fixed interval.
3. Expose a Unix-domain socket so in-VM tools can request secrets without
   ever knowing the orchestrator URL or the VM token directly.

Designed to be imported with no Eidolon orchestrator dependencies — the agent
runs inside operator-targeted VMs that should not carry the host codebase.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_SOCKET = Path("/run/eidolon-agent.sock")
HEARTBEAT_SECONDS = 60
SOCKET_BACKLOG = 16
SOCKET_TIMEOUT = 5.0
HTTP_TIMEOUT = 5.0

logger = logging.getLogger("eidolon-agent")


class AgentError(Exception):
    """Raised on a fatal agent operation failure."""


def _http_post_json(
    url: str,
    body: dict[str, Any],
    *,
    token: str,
    verify: bool = True,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - operator-supplied URL
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "eidolon-agent/0.1",
        },
    )
    ctx = None if verify else ssl._create_unverified_context()  # noqa: S323
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ctx) as resp:  # noqa: S310
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise AgentError(f"http {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc
    except urllib.error.URLError as exc:
        raise AgentError(f"network: {exc}") from exc
    if not payload:
        return {}
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise AgentError("response_not_object")
    return parsed


def _read_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


class AgentConfig:
    def __init__(
        self,
        *,
        orchestrator_url: str,
        vm_token: str,
        vm_name: str,
        socket_path: Path,
        verify_tls: bool,
    ) -> None:
        self.orchestrator_url = orchestrator_url.rstrip("/")
        self.vm_token = vm_token
        self.vm_name = vm_name
        self.socket_path = socket_path
        self.verify_tls = verify_tls

    @classmethod
    def from_env(cls) -> AgentConfig:
        url = _read_env("EIDOLON_ORCHESTRATOR_URL")
        token = _read_env("EIDOLON_VM_TOKEN")
        name = _read_env("EIDOLON_VM_NAME")
        if not url or not token or not name:
            raise AgentError(
                "missing env: EIDOLON_ORCHESTRATOR_URL, "
                "EIDOLON_VM_TOKEN, EIDOLON_VM_NAME required"
            )
        socket_path = Path(_read_env("EIDOLON_AGENT_SOCKET") or str(DEFAULT_SOCKET))
        verify = _read_env("EIDOLON_AGENT_VERIFY_TLS", "1") != "0"
        return cls(
            orchestrator_url=url,
            vm_token=token,
            vm_name=name,
            socket_path=socket_path,
            verify_tls=verify,
        )


class OrchestratorClient:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def _url(self, path: str) -> str:
        return f"{self.config.orchestrator_url}/v1/vm-agent{path}"

    def register(self) -> dict[str, Any]:
        return _http_post_json(
            self._url("/register"),
            {"vm_name": self.config.vm_name},
            token=self.config.vm_token,
            verify=self.config.verify_tls,
        )

    def heartbeat(self) -> dict[str, Any]:
        return _http_post_json(
            self._url("/heartbeat"),
            {},
            token=self.config.vm_token,
            verify=self.config.verify_tls,
        )

    def fetch_secret(self, label: str) -> str:
        body = _http_post_json(
            self._url("/secrets"),
            {"label": label},
            token=self.config.vm_token,
            verify=self.config.verify_tls,
        )
        value = body.get("value")
        if not isinstance(value, str):
            raise AgentError("secret_response_invalid")
        return value


class HeartbeatThread(threading.Thread):
    def __init__(self, client: OrchestratorClient, interval: int = HEARTBEAT_SECONDS):
        super().__init__(daemon=True, name="eidolon-agent-heartbeat")
        self.client = client
        self.interval = interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.client.heartbeat()
            except AgentError as exc:
                logger.warning("heartbeat failed: %s", exc)
            self._stop_event.wait(self.interval)


class SocketServer:
    """Unix-domain socket. Each connection: client sends one JSON line, agent
    replies with one JSON line. Two request kinds:
      {"op": "get_secret", "label": "..."}
      {"op": "ping"}
    """

    def __init__(self, client: OrchestratorClient, socket_path: Path) -> None:
        self.client = client
        self.socket_path = socket_path
        self._sock: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        sock.listen(SOCKET_BACKLOG)
        sock.settimeout(1.0)
        self._sock = sock
        logger.info("listening on %s", self.socket_path)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        if self._sock is None:
            raise AgentError("socket_not_started")
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                raise
            threading.Thread(
                target=self._handle, args=(conn,), daemon=True, name="agent-conn"
            ).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(SOCKET_TIMEOUT)
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 64 * 1024:
                    self._reply(conn, {"ok": False, "reason": "request_too_large"})
                    return
            response = self._dispatch(data)
            self._reply(conn, response)
        except Exception as exc:  # noqa: BLE001
            logger.exception("socket handler error")
            try:
                self._reply(conn, {"ok": False, "reason": str(exc)})
            except OSError:
                pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch(self, raw: bytes) -> dict[str, Any]:
        if not raw.strip():
            return {"ok": False, "reason": "empty_request"}
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "reason": "invalid_json"}
        op = req.get("op")
        if op == "ping":
            return {"ok": True, "pong": int(time.time())}
        if op == "get_secret":
            label = req.get("label")
            if not isinstance(label, str) or not label:
                return {"ok": False, "reason": "label_required"}
            try:
                value = self.client.fetch_secret(label)
            except AgentError as exc:
                return {"ok": False, "reason": str(exc)}
            return {"ok": True, "value": value}
        return {"ok": False, "reason": f"unknown_op: {op}"}

    @staticmethod
    def _reply(conn: socket.socket, payload: dict[str, Any]) -> None:
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eidolon-agent")
    parser.add_argument(
        "--no-heartbeat",
        action="store_true",
        help="Skip the periodic heartbeat thread (useful for one-shot tests).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Register once and exit (no socket, no heartbeat).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        config = AgentConfig.from_env()
    except AgentError as exc:
        logger.error("%s", exc)
        return 2

    client = OrchestratorClient(config)
    try:
        client.register()
    except AgentError as exc:
        logger.error("register failed: %s", exc)
        return 1

    logger.info("registered as vm_name=%s", config.vm_name)
    if args.once:
        return 0

    hb: HeartbeatThread | None = None
    if not args.no_heartbeat:
        hb = HeartbeatThread(client)
        hb.start()

    server = SocketServer(client, config.socket_path)
    server.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        if hb is not None:
            hb.stop()
        server.stop()
    return 0


def cli_main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    cli_main()
