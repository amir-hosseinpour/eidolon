from .base import (
    NetworkHandle,
    NetworkSpec,
    SnapshotHandle,
    Substrate,
    VMHandle,
    VMSpec,
)
from .docker_substrate import DockerSubstrate
from .proxmox_substrate import ProxmoxConfig, ProxmoxError, ProxmoxSubstrate
from .stubs import MacSubstrate, WindowsSubstrate

__all__ = [
    "DockerSubstrate",
    "MacSubstrate",
    "NetworkHandle",
    "NetworkSpec",
    "ProxmoxConfig",
    "ProxmoxError",
    "ProxmoxSubstrate",
    "SnapshotHandle",
    "Substrate",
    "VMHandle",
    "VMSpec",
    "WindowsSubstrate",
]
