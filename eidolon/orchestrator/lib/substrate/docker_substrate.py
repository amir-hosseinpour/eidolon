from __future__ import annotations

import io
import tarfile
import time
from typing import TYPE_CHECKING, Any

from .base import (
    NetworkHandle,
    NetworkSpec,
    SnapshotHandle,
    Substrate,
    VMHandle,
    VMSpec,
)

if TYPE_CHECKING:
    from docker import DockerClient  # type: ignore[import-untyped]


_LABEL_PROJECT = "eidolon"
_LABEL_PROJECT_VALUE = "v0.1"


class DockerError(Exception):
    """Wraps docker SDK exceptions with stable reasons for the orchestrator."""

    def __init__(self, reason: str, cause: Exception | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


class DockerSubstrate(Substrate):
    """Docker driver. Each engagement gets its own bridge network; each VM is a
    container attached to that network. Snapshots are `docker commit` images.
    """

    driver_name = "docker"

    def __init__(self, client: DockerClient | None = None) -> None:
        self._client_override = client

    @property
    def client(self) -> DockerClient:
        if self._client_override is not None:
            return self._client_override
        import docker

        try:
            return docker.from_env()
        except Exception as exc:
            raise DockerError("docker_unreachable", cause=exc) from exc

    @staticmethod
    def _labels(extra: dict[str, str] | None = None) -> dict[str, str]:
        labels = {_LABEL_PROJECT: _LABEL_PROJECT_VALUE}
        if extra:
            labels.update(extra)
        return labels

    def network_create(self, spec: NetworkSpec) -> NetworkHandle:
        labels = self._labels({"engagement_id": spec.engagement_id, **spec.labels})
        ipam: dict[str, Any] | None = None
        if spec.cidr:
            ipam = {
                "Driver": "default",
                "Config": [{"Subnet": spec.cidr}],
            }
        try:
            net = self.client.networks.create(
                name=spec.name,
                driver="bridge",
                internal=False,
                ipam=ipam,
                labels=labels,
                check_duplicate=True,
            )
        except Exception as exc:
            raise DockerError("network_create_failed", cause=exc) from exc
        return NetworkHandle(
            id=net.id,
            name=net.name,
            driver=self.driver_name,
            cidr=spec.cidr,
        )

    def network_destroy(self, handle: NetworkHandle) -> None:
        try:
            net = self.client.networks.get(handle.id)
        except Exception as exc:
            raise DockerError("network_not_found", cause=exc) from exc
        try:
            net.remove()
        except Exception as exc:
            raise DockerError("network_destroy_failed", cause=exc) from exc

    def provision(self, spec: VMSpec) -> VMHandle:
        labels = self._labels({"vm_name": spec.name, **spec.labels})
        host_config: dict[str, Any] = {
            "labels": labels,
            "name": spec.name,
            "image": spec.image,
            "network": spec.network,
            "environment": dict(spec.env),
            "detach": True,
            "privileged": spec.privileged,
            "cap_add": list(spec.capabilities),
            "mem_limit": f"{spec.memory_mb}m",
            "nano_cpus": spec.cpu * 1_000_000_000,
        }
        if spec.cmd is not None:
            host_config["command"] = list(spec.cmd)
        if spec.volumes:
            host_config["volumes"] = {h: {"bind": c, "mode": "rw"} for h, c in spec.volumes}

        try:
            container = self.client.containers.run(**host_config)
        except Exception as exc:
            raise DockerError("provision_failed", cause=exc) from exc

        # Brief poll so the container has an IP on the network.
        address: str | None = None
        for _ in range(10):
            try:
                container.reload()
                nets = container.attrs.get("NetworkSettings", {}).get("Networks", {})
                if spec.network in nets:
                    address = nets[spec.network].get("IPAddress") or None
                    if address:
                        break
            except Exception:  # noqa: S110 — best-effort IP poll; loop bounded
                pass
            time.sleep(0.1)

        return VMHandle(
            id=container.id,
            name=spec.name,
            driver=self.driver_name,
            network=spec.network,
            address=address,
        )

    def destroy(self, handle: VMHandle) -> None:
        try:
            container = self.client.containers.get(handle.id)
        except Exception as exc:
            raise DockerError("vm_not_found", cause=exc) from exc
        try:
            container.remove(force=True, v=True)
        except Exception as exc:
            raise DockerError("destroy_failed", cause=exc) from exc

    def snapshot(self, handle: VMHandle) -> SnapshotHandle:
        try:
            container = self.client.containers.get(handle.id)
        except Exception as exc:
            raise DockerError("vm_not_found", cause=exc) from exc
        repo = f"eidolon-snap/{handle.name}"
        tag = str(int(time.time()))
        try:
            image = container.commit(repository=repo, tag=tag)
        except Exception as exc:
            raise DockerError("snapshot_failed", cause=exc) from exc
        return SnapshotHandle(
            vm_id=handle.id,
            snapshot_id=image.id,
            driver=self.driver_name,
        )

    def secrets_inject(self, handle: VMHandle, secrets: dict[str, str]) -> None:
        """Inject secrets as files under /run/eidolon-secrets/ inside the container.

        Mode 0400. Names follow the secret keys verbatim. Caller is responsible
        for redacting these from logs and rotating after the engagement closes.
        """
        if not secrets:
            return
        try:
            container = self.client.containers.get(handle.id)
        except Exception as exc:
            raise DockerError("vm_not_found", cause=exc) from exc

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for key, value in secrets.items():
                data = value.encode("utf-8")
                info = tarfile.TarInfo(name=f"./{key}")
                info.size = len(data)
                info.mode = 0o400
                info.mtime = int(time.time())
                tar.addfile(info, io.BytesIO(data))
        buf.seek(0)

        try:
            container.exec_run(["mkdir", "-p", "/run/eidolon-secrets"])
            ok = container.put_archive("/run/eidolon-secrets", buf.getvalue())
        except Exception as exc:
            raise DockerError("secrets_inject_failed", cause=exc) from exc
        if not ok:
            raise DockerError("secrets_inject_failed")
