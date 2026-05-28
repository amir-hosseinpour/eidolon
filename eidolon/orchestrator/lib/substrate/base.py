from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NetworkSpec:
    engagement_id: str
    name: str
    cidr: str | None = None
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NetworkHandle:
    id: str
    name: str
    driver: str
    cidr: str | None = None


@dataclass(frozen=True)
class VMSpec:
    name: str
    image: str
    network: str
    cpu: int = 2
    memory_mb: int = 2048
    env: dict[str, str] = field(default_factory=dict)
    cmd: list[str] | None = None
    privileged: bool = False
    capabilities: list[str] = field(default_factory=list)
    volumes: list[tuple[str, str]] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class VMHandle:
    id: str
    name: str
    driver: str
    network: str
    address: str | None = None


@dataclass(frozen=True)
class SnapshotHandle:
    vm_id: str
    snapshot_id: str
    driver: str


class Substrate(ABC):
    """Provisioning interface for engagement workspaces.

    Implementations isolate AI-driven offsec workloads at network and host
    level. v0.1 ships Docker (default) and Proxmox; Mac/Windows are stubs.
    """

    driver_name: str = "abstract"

    @abstractmethod
    def network_create(self, spec: NetworkSpec) -> NetworkHandle: ...

    @abstractmethod
    def network_destroy(self, handle: NetworkHandle) -> None: ...

    @abstractmethod
    def provision(self, spec: VMSpec) -> VMHandle: ...

    @abstractmethod
    def destroy(self, handle: VMHandle) -> None: ...

    @abstractmethod
    def snapshot(self, handle: VMHandle) -> SnapshotHandle: ...

    @abstractmethod
    def secrets_inject(self, handle: VMHandle, secrets: dict[str, str]) -> None: ...
