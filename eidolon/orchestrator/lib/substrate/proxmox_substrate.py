from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .base import (
    NetworkHandle,
    NetworkSpec,
    SnapshotHandle,
    Substrate,
    VMHandle,
    VMSpec,
)

if TYPE_CHECKING:  # pragma: no cover
    from proxmoxer import ProxmoxAPI  # type: ignore[import-untyped]


class ProxmoxError(Exception):
    """Wraps proxmoxer exceptions with stable reasons for the orchestrator."""

    def __init__(self, reason: str, cause: Exception | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


@dataclass(frozen=True)
class ProxmoxConfig:
    """Connection + provisioning defaults for the Proxmox driver.

    The driver expects the Proxmox node to already host a `template_id`
    (full VM template prepared offline). Cloning is fast; provisioning a
    template from scratch is out of scope for v0.1.
    """

    host: str
    user: str
    password: str | None = None
    token_name: str | None = None
    token_value: str | None = None
    node: str = "pve"
    template_id: int = 9000
    storage: str = "local-lvm"
    bridge: str = "vmbr0"
    vlan_pool_start: int = 1000
    vlan_pool_end: int = 1999
    verify_ssl: bool = False

    @classmethod
    def from_env(cls) -> ProxmoxConfig:
        host = os.environ.get("PROXMOX_HOST")
        user = os.environ.get("PROXMOX_USER", "root@pam")
        if not host:
            raise ProxmoxError("missing_proxmox_host")
        return cls(
            host=host,
            user=user,
            password=os.environ.get("PROXMOX_PASSWORD"),
            token_name=os.environ.get("PROXMOX_TOKEN_NAME"),
            token_value=os.environ.get("PROXMOX_TOKEN_VALUE"),
            node=os.environ.get("PROXMOX_NODE", "pve"),
            template_id=int(os.environ.get("PROXMOX_TEMPLATE_ID", "9000")),
            storage=os.environ.get("PROXMOX_STORAGE", "local-lvm"),
            bridge=os.environ.get("PROXMOX_BRIDGE", "vmbr0"),
            vlan_pool_start=int(os.environ.get("PROXMOX_VLAN_POOL_START", "1000")),
            vlan_pool_end=int(os.environ.get("PROXMOX_VLAN_POOL_END", "1999")),
            verify_ssl=os.environ.get("PROXMOX_VERIFY_SSL", "0") == "1",
        )


class ProxmoxSubstrate(Substrate):
    """Proxmox VE driver. Each engagement reserves a VLAN tag from the pool;
    each VM is a clone of `template_id`. Snapshots use Proxmox's native
    `qemu-snapshot`. Destroy = stop + purge.
    """

    driver_name = "proxmox"

    def __init__(
        self,
        config: ProxmoxConfig | None = None,
        *,
        api: ProxmoxAPI | None = None,
    ) -> None:
        self._config = config
        self._api_override = api
        self._vlan_cursor = (config.vlan_pool_start if config else 1000)

    @property
    def config(self) -> ProxmoxConfig:
        if self._config is None:
            self._config = ProxmoxConfig.from_env()
        return self._config

    @property
    def api(self) -> ProxmoxAPI:
        if self._api_override is not None:
            return self._api_override
        try:
            from proxmoxer import ProxmoxAPI
        except ImportError as exc:
            raise ProxmoxError("proxmoxer_missing", cause=exc) from exc

        cfg = self.config
        kwargs: dict[str, Any] = {"verify_ssl": cfg.verify_ssl}
        if cfg.token_name and cfg.token_value:
            kwargs["token_name"] = cfg.token_name
            kwargs["token_value"] = cfg.token_value
        elif cfg.password:
            kwargs["password"] = cfg.password
        else:
            raise ProxmoxError("missing_proxmox_credentials")

        try:
            return ProxmoxAPI(cfg.host, user=cfg.user, **kwargs)
        except Exception as exc:
            raise ProxmoxError("proxmox_unreachable", cause=exc) from exc

    def _next_vlan(self) -> int:
        cfg = self.config
        used: set[int] = set()
        try:
            for vm in self.api.nodes(cfg.node).qemu.get():
                cur = self.api.nodes(cfg.node).qemu(vm["vmid"]).config.get()
                for key, val in cur.items():
                    if key.startswith("net") and isinstance(val, str) and "tag=" in val:
                        for part in val.split(","):
                            if part.startswith("tag="):
                                used.add(int(part.split("=", 1)[1]))
        except Exception as exc:
            raise ProxmoxError("vlan_scan_failed", cause=exc) from exc
        for tag in range(cfg.vlan_pool_start, cfg.vlan_pool_end + 1):
            if tag not in used:
                return tag
        raise ProxmoxError("vlan_pool_exhausted")

    def _allocate_vmid(self) -> int:
        try:
            return int(self.api.cluster.nextid.get())
        except Exception as exc:
            raise ProxmoxError("vmid_alloc_failed", cause=exc) from exc

    def _wait_task(self, upid: str, timeout: int = 120) -> None:
        cfg = self.config
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = self.api.nodes(cfg.node).tasks(upid).status.get()
            except Exception as exc:
                raise ProxmoxError("task_status_failed", cause=exc) from exc
            if status.get("status") == "stopped":
                if status.get("exitstatus") == "OK":
                    return
                raise ProxmoxError(f"task_failed:{status.get('exitstatus')}")
            time.sleep(1)
        raise ProxmoxError("task_timeout")

    def network_create(self, spec: NetworkSpec) -> NetworkHandle:
        tag = self._next_vlan()
        return NetworkHandle(
            id=f"vlan-{tag}",
            name=spec.name,
            driver=self.driver_name,
            cidr=spec.cidr,
        )

    def network_destroy(self, handle: NetworkHandle) -> None:
        # VLAN tags are pool-managed; nothing to delete server-side.
        return None

    def provision(self, spec: VMSpec) -> VMHandle:
        cfg = self.config
        try:
            tag = int(spec.network.split("-", 1)[1]) if spec.network.startswith("vlan-") else self._next_vlan()
        except (IndexError, ValueError) as exc:
            raise ProxmoxError("bad_network_handle", cause=exc) from exc

        new_vmid = self._allocate_vmid()
        try:
            upid = self.api.nodes(cfg.node).qemu(cfg.template_id).clone.post(
                newid=new_vmid,
                name=spec.name,
                full=1,
                target=cfg.node,
                storage=cfg.storage,
            )
        except Exception as exc:
            raise ProxmoxError("clone_failed", cause=exc) from exc
        self._wait_task(upid)

        try:
            self.api.nodes(cfg.node).qemu(new_vmid).config.put(
                cores=spec.cpu,
                memory=spec.memory_mb,
                net0=f"virtio,bridge={cfg.bridge},tag={tag}",
            )
        except Exception as exc:
            raise ProxmoxError("config_failed", cause=exc) from exc

        try:
            upid = self.api.nodes(cfg.node).qemu(new_vmid).status.start.post()
        except Exception as exc:
            raise ProxmoxError("start_failed", cause=exc) from exc
        self._wait_task(upid)

        return VMHandle(
            id=str(new_vmid),
            name=spec.name,
            driver=self.driver_name,
            network=spec.network,
            address=None,
        )

    def destroy(self, handle: VMHandle) -> None:
        cfg = self.config
        try:
            upid = self.api.nodes(cfg.node).qemu(handle.id).status.stop.post()
            self._wait_task(upid)
        except Exception:  # noqa: BLE001, S110 — already-stopped is OK
            pass
        try:
            upid = self.api.nodes(cfg.node).qemu(handle.id).delete()
        except Exception as exc:
            raise ProxmoxError("destroy_failed", cause=exc) from exc
        self._wait_task(upid)

    def snapshot(self, handle: VMHandle) -> SnapshotHandle:
        cfg = self.config
        snap_name = f"eidolon-snap-{int(time.time())}"
        try:
            upid = self.api.nodes(cfg.node).qemu(handle.id).snapshot.post(
                snapname=snap_name,
            )
        except Exception as exc:
            raise ProxmoxError("snapshot_failed", cause=exc) from exc
        self._wait_task(upid)
        return SnapshotHandle(
            vm_id=handle.id,
            snapshot_id=snap_name,
            driver=self.driver_name,
        )

    def secrets_inject(self, handle: VMHandle, secrets: dict[str, str]) -> None:
        """Stage secrets via the eidolon-agent in-VM daemon.

        v0.1 limitation: this driver does not poke into guests directly.
        The engagement controller pushes secrets through the agent socket
        once the VM is up. See task #103 (secrets broker) and #104 (agent).
        """
        if not secrets:
            return
        raise ProxmoxError("secrets_via_agent_only")
