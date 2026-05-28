"""Unit tests for ProxmoxSubstrate using a fake proxmoxer API.

Real-Proxmox tests live below the `proxmox` marker and are skipped unless
EIDOLON_PROXMOX_TESTS=1.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

from eidolon.orchestrator.lib.substrate import (
    NetworkSpec,
    ProxmoxConfig,
    ProxmoxError,
    ProxmoxSubstrate,
    VMHandle,
    VMSpec,
)


class _FakeNode:
    """Mimics the chained call pattern used by proxmoxer."""

    def __init__(self, scribe: dict[str, Any]) -> None:
        self.scribe = scribe
        self.scribe.setdefault("calls", [])
        self.scribe.setdefault("vms", {})
        self.scribe.setdefault("tasks", {})

    @property
    def qemu(self) -> _FakeQemuRoot:
        return _FakeQemuRoot(self.scribe)

    @property
    def tasks(self):  # type: ignore[no-untyped-def]
        return _FakeTaskFactory(self.scribe)


class _FakeQemuRoot:
    """`api.nodes(n).qemu.get()` lists; `.qemu(vmid)` returns a per-VM handle."""

    def __init__(self, scribe: dict[str, Any]) -> None:
        self.scribe = scribe

    def get(self) -> list[dict[str, Any]]:
        return [{"vmid": v} for v in self.scribe["vms"].keys()]

    def __call__(self, vmid: int) -> _FakeQemu:
        return _FakeQemu(self.scribe, vmid)


class _FakeTaskFactory:
    def __init__(self, scribe: dict[str, Any]) -> None:
        self.scribe = scribe

    def __call__(self, upid: str) -> _FakeTask:
        return _FakeTask(self.scribe, upid)


class _FakeTask:
    def __init__(self, scribe: dict[str, Any], upid: str) -> None:
        self.scribe = scribe
        self.upid = upid

    @property
    def status(self):  # type: ignore[no-untyped-def]
        return _FakeTaskStatus(self.scribe, self.upid)


class _FakeTaskStatus:
    def __init__(self, scribe: dict[str, Any], upid: str) -> None:
        self.scribe = scribe
        self.upid = upid

    def get(self) -> dict[str, str]:
        return self.scribe["tasks"].get(self.upid, {"status": "stopped", "exitstatus": "OK"})


class _FakeQemu:
    def __init__(self, scribe: dict[str, Any], vmid: int | None) -> None:
        self.scribe = scribe
        self.vmid = vmid

    @property
    def config(self):  # type: ignore[no-untyped-def]
        return _FakeConfig(self.scribe, self.vmid)

    @property
    def clone(self):  # type: ignore[no-untyped-def]
        return _FakeClone(self.scribe, self.vmid)

    @property
    def status(self):  # type: ignore[no-untyped-def]
        return _FakeStatus(self.scribe, self.vmid)

    @property
    def snapshot(self):  # type: ignore[no-untyped-def]
        return _FakeSnapshot(self.scribe, self.vmid)

    def delete(self) -> str:
        upid = f"UPID:delete-{self.vmid}"
        self.scribe["calls"].append({"op": "delete", "vmid": self.vmid})
        self.scribe["vms"].pop(self.vmid, None)
        return upid


class _FakeConfig:
    def __init__(self, scribe: dict[str, Any], vmid: int | None) -> None:
        self.scribe = scribe
        self.vmid = vmid

    def get(self) -> dict[str, str]:
        return self.scribe["vms"].get(self.vmid, {})

    def put(self, **kwargs: Any) -> None:
        self.scribe["calls"].append({"op": "config.put", "vmid": self.vmid, **kwargs})
        self.scribe["vms"].setdefault(self.vmid, {}).update(kwargs)


class _FakeClone:
    def __init__(self, scribe: dict[str, Any], vmid: int | None) -> None:
        self.scribe = scribe
        self.vmid = vmid

    def post(self, **kwargs: Any) -> str:
        new = kwargs["newid"]
        self.scribe["vms"][new] = {"name": kwargs.get("name", "")}
        upid = f"UPID:clone-{new}"
        self.scribe["calls"].append({"op": "clone", "from": self.vmid, "to": new})
        return upid


class _FakeStatus:
    def __init__(self, scribe: dict[str, Any], vmid: int | None) -> None:
        self.scribe = scribe
        self.vmid = vmid

    @property
    def start(self):  # type: ignore[no-untyped-def]
        return _FakeStatusVerb(self.scribe, self.vmid, "start")

    @property
    def stop(self):  # type: ignore[no-untyped-def]
        return _FakeStatusVerb(self.scribe, self.vmid, "stop")


class _FakeStatusVerb:
    def __init__(self, scribe: dict[str, Any], vmid: int | None, verb: str) -> None:
        self.scribe = scribe
        self.vmid = vmid
        self.verb = verb

    def post(self) -> str:
        self.scribe["calls"].append({"op": f"status.{self.verb}", "vmid": self.vmid})
        return f"UPID:{self.verb}-{self.vmid}"


class _FakeSnapshot:
    def __init__(self, scribe: dict[str, Any], vmid: int | None) -> None:
        self.scribe = scribe
        self.vmid = vmid

    def post(self, **kwargs: Any) -> str:
        snap = kwargs["snapname"]
        self.scribe["calls"].append({"op": "snapshot", "vmid": self.vmid, "name": snap})
        return f"UPID:snapshot-{self.vmid}"


class _FakeCluster:
    def __init__(self, scribe: dict[str, Any]) -> None:
        self.scribe = scribe
        self._next = 100

    @property
    def nextid(self):  # type: ignore[no-untyped-def]
        return self

    def get(self) -> int:
        v = self._next
        self._next += 1
        return v


class _FakeAPI:
    def __init__(self) -> None:
        self.scribe: dict[str, Any] = {}
        self._node = _FakeNode(self.scribe)
        self._cluster = _FakeCluster(self.scribe)

    def nodes(self, name: str) -> _FakeNode:
        return self._node

    @property
    def cluster(self) -> _FakeCluster:
        return self._cluster


@pytest.fixture
def proxmox() -> tuple[ProxmoxSubstrate, _FakeAPI]:
    api = _FakeAPI()
    cfg = ProxmoxConfig(
        host="fake.local",
        user="root@pam",
        password="x",  # noqa: S106 — fake config for unit tests
        node="pve",
        template_id=9000,
        storage="local-lvm",
        bridge="vmbr0",
        vlan_pool_start=1000,
        vlan_pool_end=1010,
    )
    return ProxmoxSubstrate(config=cfg, api=api), api


def test_network_create_returns_vlan_handle(proxmox: tuple[ProxmoxSubstrate, _FakeAPI]) -> None:
    sub, _api = proxmox
    handle = sub.network_create(NetworkSpec(engagement_id="ENG-1", name="net-1"))
    assert handle.driver == "proxmox"
    assert handle.id.startswith("vlan-")
    tag = int(handle.id.split("-", 1)[1])
    assert 1000 <= tag <= 1010


def test_provision_clones_and_starts(proxmox: tuple[ProxmoxSubstrate, _FakeAPI]) -> None:
    sub, api = proxmox
    net = sub.network_create(NetworkSpec(engagement_id="ENG-1", name="net-1"))
    vm = sub.provision(
        VMSpec(name="kali", image="ignored", network=net.id, cpu=2, memory_mb=2048)
    )
    assert vm.driver == "proxmox"
    ops = [c["op"] for c in api.scribe["calls"]]
    assert "clone" in ops
    assert "config.put" in ops
    assert "status.start" in ops


def test_destroy_stops_and_deletes(proxmox: tuple[ProxmoxSubstrate, _FakeAPI]) -> None:
    sub, api = proxmox
    handle = VMHandle(id="100", name="kali", driver="proxmox", network="vlan-1000")
    api.scribe["vms"][100] = {"name": "kali"}
    sub.destroy(handle)
    ops = [c["op"] for c in api.scribe["calls"]]
    assert "status.stop" in ops
    assert "delete" in ops


def test_snapshot_creates_named_snapshot(proxmox: tuple[ProxmoxSubstrate, _FakeAPI]) -> None:
    sub, api = proxmox
    handle = VMHandle(id="100", name="kali", driver="proxmox", network="vlan-1000")
    snap = sub.snapshot(handle)
    assert snap.driver == "proxmox"
    assert snap.snapshot_id.startswith("eidolon-snap-")
    snapshot_calls = [c for c in api.scribe["calls"] if c["op"] == "snapshot"]
    assert len(snapshot_calls) == 1


def test_secrets_inject_routes_to_agent(proxmox: tuple[ProxmoxSubstrate, _FakeAPI]) -> None:
    sub, _api = proxmox
    handle = VMHandle(id="100", name="kali", driver="proxmox", network="vlan-1000")
    with pytest.raises(ProxmoxError) as exc:
        sub.secrets_inject(handle, {"k": "v"})
    assert exc.value.reason == "secrets_via_agent_only"


def test_config_from_env_requires_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROXMOX_HOST", raising=False)
    with pytest.raises(ProxmoxError) as exc:
        ProxmoxConfig.from_env()
    assert exc.value.reason == "missing_proxmox_host"


@pytest.mark.proxmox
@pytest.mark.skipif(
    os.environ.get("EIDOLON_PROXMOX_TESTS") != "1",
    reason="EIDOLON_PROXMOX_TESTS!=1",
)
def test_real_proxmox_lifecycle() -> None:
    """Smoke test against a real Proxmox host. Requires PROXMOX_HOST etc."""
    sub = ProxmoxSubstrate()
    net = sub.network_create(NetworkSpec(engagement_id="ENG-test", name="eng-test-net"))
    vm = sub.provision(
        VMSpec(name="eidolon-test", image="ignored", network=net.id, cpu=1, memory_mb=512)
    )
    try:
        snap = sub.snapshot(vm)
        assert snap.snapshot_id
    finally:
        sub.destroy(vm)
        sub.network_destroy(net)
