from __future__ import annotations

from .base import (
    NetworkHandle,
    NetworkSpec,
    SnapshotHandle,
    Substrate,
    VMHandle,
    VMSpec,
)


def _v02(driver: str) -> NotImplementedError:
    return NotImplementedError(
        f"{driver} substrate is not yet implemented; targeted for v0.2."
    )


class _StubSubstrate(Substrate):
    """Shared base for substrates that only ship roadmap stubs in v0.1."""

    driver_name = "stub"

    def network_create(self, spec: NetworkSpec) -> NetworkHandle:
        raise _v02(self.driver_name)

    def network_destroy(self, handle: NetworkHandle) -> None:
        raise _v02(self.driver_name)

    def provision(self, spec: VMSpec) -> VMHandle:
        raise _v02(self.driver_name)

    def destroy(self, handle: VMHandle) -> None:
        raise _v02(self.driver_name)

    def snapshot(self, handle: VMHandle) -> SnapshotHandle:
        raise _v02(self.driver_name)

    def secrets_inject(self, handle: VMHandle, secrets: dict[str, str]) -> None:
        raise _v02(self.driver_name)


class MacSubstrate(_StubSubstrate):
    """Apple silicon macOS substrate. v0.2 will use Apple Virtualization framework."""

    driver_name = "mac"


class WindowsSubstrate(_StubSubstrate):
    """Windows substrate. v0.2 will use Hyper-V via PowerShell."""

    driver_name = "windows"


class ProxmoxSubstrateStub(_StubSubstrate):
    """Roadmap placeholder until task #96 ships the real Proxmox driver."""

    driver_name = "proxmox"
