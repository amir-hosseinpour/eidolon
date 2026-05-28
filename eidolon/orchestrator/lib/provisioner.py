from __future__ import annotations

import sqlite3
import time

from pydantic import BaseModel

from .audit import emit_audit
from .db import get_db, write_tx
from .engagements import EngagementStatus, EngagementStore
from .substrate import (
    NetworkHandle,
    NetworkSpec,
    Substrate,
    VMHandle,
    VMSpec,
)
from .templates import LoadedTemplate, SubstrateName
from .vm_agents import get_vm_agent_store


class ProvisionError(Exception):
    """Raised when provisioning or teardown fails for an engagement."""

    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(f"{status_code} {reason}")
        self.status_code = status_code
        self.reason = reason


class ProvisionedVM(BaseModel):
    handle_id: str
    engagement_id: str
    vm_name: str
    driver: str
    network: str
    address: str | None
    template_name: str
    status: str
    created_at: int
    destroyed_at: int | None = None


class ProvisionedNetwork(BaseModel):
    engagement_id: str
    handle_id: str
    name: str
    substrate_name: str
    driver: str
    cidr: str | None = None
    created_at: int
    destroyed_at: int | None = None


class ProvisionResult(BaseModel):
    engagement_id: str
    template: str
    network: ProvisionedNetwork
    vms: list[ProvisionedVM]


def _default_factories() -> dict[str, object]:
    from .substrate import DockerSubstrate, ProxmoxSubstrate

    return {"docker": DockerSubstrate, "proxmox": ProxmoxSubstrate}


def _row_to_vm(row: sqlite3.Row) -> ProvisionedVM:
    return ProvisionedVM(
        handle_id=row["handle_id"],
        engagement_id=row["engagement_id"],
        vm_name=row["vm_name"],
        driver=row["driver"],
        network=row["network"],
        address=row["address"],
        template_name=row["template_name"],
        status=row["status"],
        created_at=row["created_at"],
        destroyed_at=row["destroyed_at"],
    )


def _row_to_network(row: sqlite3.Row) -> ProvisionedNetwork:
    return ProvisionedNetwork(
        engagement_id=row["engagement_id"],
        handle_id=row["handle_id"],
        name=row["name"],
        substrate_name=row["substrate_name"],
        driver=row["driver"],
        cidr=row["cidr"],
        created_at=row["created_at"],
        destroyed_at=row["destroyed_at"],
    )


class Provisioner:
    """Orchestrates substrate calls for an engagement.

    Picks the substrate by name (template-supported list intersected with
    a host-specified default), creates the per-engagement network, issues
    a vm token per VM, then provisions each VM and persists handles.

    State persists in SQLite (engagement_networks, engagement_vms,
    vm_agents). Teardown reads those tables back and reverses the steps.
    """

    def __init__(
        self,
        *,
        substrates: dict[str, Substrate] | None = None,
        engagement_store: EngagementStore | None = None,
    ) -> None:
        self._substrates = substrates or {}
        self._engagement_store = engagement_store or EngagementStore()
        self._vm_agents = get_vm_agent_store()

    def _resolve(self, name: SubstrateName) -> Substrate:
        if name in self._substrates:
            return self._substrates[name]
        factories = _default_factories()
        if name not in factories:
            raise ProvisionError(400, f"substrate_unsupported:{name}")
        cls = factories[name]
        try:
            return cls()  # type: ignore[operator,no-any-return]
        except Exception as exc:
            raise ProvisionError(503, f"substrate_unavailable:{name}") from exc

    def _pick(self, template: LoadedTemplate) -> tuple[SubstrateName, Substrate]:
        for candidate in template.template.substrate_support:
            try:
                return candidate, self._resolve(candidate)
            except ProvisionError:
                continue
        raise ProvisionError(503, "no_substrate_available")

    def provision(
        self,
        *,
        engagement_id: str,
        template: LoadedTemplate,
    ) -> ProvisionResult:
        engagement = self._engagement_store.get(engagement_id)
        if engagement is None:
            raise ProvisionError(404, "engagement_not_found")
        if engagement.status != EngagementStatus.active:
            raise ProvisionError(409, f"engagement_{engagement.status.value}")
        if self._existing_network(engagement_id) is not None:
            raise ProvisionError(409, "already_provisioned")

        substrate_name, substrate = self._pick(template)
        net_spec = NetworkSpec(
            engagement_id=engagement_id,
            name=template.template.network.name.replace(
                "{{engagement_id}}", engagement_id
            ),
            cidr=template.template.network.cidr,
            labels={"eidolon_engagement": engagement_id},
        )
        net_handle = substrate.network_create(net_spec)
        now = int(time.time())
        with write_tx() as conn:
            conn.execute(
                """
                INSERT INTO engagement_networks (
                    engagement_id, substrate_name, driver, handle_id, name,
                    cidr, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    engagement_id,
                    substrate_name,
                    substrate.driver_name,
                    net_handle.id,
                    net_handle.name,
                    net_handle.cidr,
                    now,
                ),
            )
        emit_audit(
            "substrate_network_created",
            engagement_id=engagement_id,
            driver=substrate.driver_name,
            network=net_handle.name,
        )

        vms: list[ProvisionedVM] = []
        for tpl_vm in template.template.vms:
            vm_token = self._vm_agents.issue(
                engagement_id=engagement_id, vm_name=tpl_vm.name
            )
            env = dict(tpl_vm.env)
            env["EIDOLON_VM_TOKEN"] = vm_token
            env["EIDOLON_ENGAGEMENT_ID"] = engagement_id
            spec = VMSpec(
                name=tpl_vm.name,
                image=tpl_vm.image,
                network=net_handle.name,
                cpu=tpl_vm.cpu,
                memory_mb=tpl_vm.memory_mb,
                env=env,
                cmd=tpl_vm.cmd,
                privileged=tpl_vm.privileged,
                capabilities=list(tpl_vm.capabilities),
                volumes=list(tpl_vm.volumes),
                labels={"eidolon_engagement": engagement_id},
            )
            try:
                handle = substrate.provision(spec)
            except Exception:
                self._vm_agents.revoke(vm_token)
                raise
            with write_tx() as conn:
                conn.execute(
                    """
                    INSERT INTO engagement_vms (
                        handle_id, engagement_id, vm_name, driver, network,
                        address, vm_token, template_name, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'provisioned', ?)
                    """,
                    (
                        handle.id,
                        engagement_id,
                        handle.name,
                        handle.driver,
                        handle.network,
                        handle.address,
                        vm_token,
                        template.template.name,
                        now,
                    ),
                )
            emit_audit(
                "substrate_vm_provisioned",
                engagement_id=engagement_id,
                driver=handle.driver,
                vm_name=handle.name,
            )
            vms.append(
                ProvisionedVM(
                    handle_id=handle.id,
                    engagement_id=engagement_id,
                    vm_name=handle.name,
                    driver=handle.driver,
                    network=handle.network,
                    address=handle.address,
                    template_name=template.template.name,
                    status="provisioned",
                    created_at=now,
                )
            )
        return ProvisionResult(
            engagement_id=engagement_id,
            template=template.template.name,
            network=ProvisionedNetwork(
                engagement_id=engagement_id,
                handle_id=net_handle.id,
                name=net_handle.name,
                substrate_name=substrate_name,
                driver=substrate.driver_name,
                cidr=net_handle.cidr,
                created_at=now,
            ),
            vms=vms,
        )

    def teardown(self, engagement_id: str) -> dict[str, int]:
        net_row = self._existing_network(engagement_id)
        if net_row is None:
            return {"vms_destroyed": 0, "network_destroyed": 0}

        substrate = self._resolve(net_row.substrate_name)  # type: ignore[arg-type]
        vm_rows = self._existing_vms(engagement_id)
        destroyed_vms = 0
        for vm in vm_rows:
            if vm.status != "provisioned":
                continue
            handle = VMHandle(
                id=vm.handle_id,
                name=vm.vm_name,
                driver=vm.driver,
                network=vm.network,
                address=vm.address,
            )
            try:
                substrate.destroy(handle)
            except Exception as exc:
                emit_audit(
                    "substrate_vm_destroy_failed",
                    engagement_id=engagement_id,
                    vm_name=vm.vm_name,
                    reason=str(exc)[:200],
                )
                continue
            token = self._vm_token_for(vm.handle_id)
            if token:
                self._vm_agents.revoke(token)
            with write_tx() as conn:
                conn.execute(
                    "UPDATE engagement_vms SET status = 'destroyed', destroyed_at = ? "
                    "WHERE handle_id = ?",
                    (int(time.time()), vm.handle_id),
                )
            emit_audit(
                "substrate_vm_destroyed",
                engagement_id=engagement_id,
                vm_name=vm.vm_name,
            )
            destroyed_vms += 1

        net_handle = NetworkHandle(
            id=net_row.handle_id,
            name=net_row.name,
            driver=net_row.driver,
            cidr=net_row.cidr,
        )
        net_destroyed = 0
        try:
            substrate.network_destroy(net_handle)
            net_destroyed = 1
            emit_audit(
                "substrate_network_destroyed",
                engagement_id=engagement_id,
                network=net_row.name,
            )
        except Exception as exc:
            emit_audit(
                "substrate_network_destroy_failed",
                engagement_id=engagement_id,
                network=net_row.name,
                reason=str(exc)[:200],
            )
        with write_tx() as conn:
            conn.execute(
                "UPDATE engagement_networks SET destroyed_at = ? WHERE engagement_id = ?",
                (int(time.time()), engagement_id),
            )
        return {"vms_destroyed": destroyed_vms, "network_destroyed": net_destroyed}

    def list_vms(self, engagement_id: str) -> list[ProvisionedVM]:
        return self._existing_vms(engagement_id)

    def get_network(self, engagement_id: str) -> ProvisionedNetwork | None:
        return self._existing_network(engagement_id)

    def _existing_network(self, engagement_id: str) -> ProvisionedNetwork | None:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM engagement_networks WHERE engagement_id = ? "
            "AND destroyed_at IS NULL",
            (engagement_id,),
        ).fetchone()
        return _row_to_network(row) if row is not None else None

    def _existing_vms(self, engagement_id: str) -> list[ProvisionedVM]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM engagement_vms WHERE engagement_id = ? "
            "ORDER BY created_at ASC",
            (engagement_id,),
        ).fetchall()
        return [_row_to_vm(r) for r in rows]

    def _vm_token_for(self, handle_id: str) -> str | None:
        conn = get_db()
        row = conn.execute(
            "SELECT vm_token FROM engagement_vms WHERE handle_id = ?",
            (handle_id,),
        ).fetchone()
        return row["vm_token"] if row is not None else None
