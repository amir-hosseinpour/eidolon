"""Integration tests for DockerSubstrate. Skipped unless EIDOLON_DOCKER_TESTS=1
and a Docker daemon is reachable.

Run locally:
    EIDOLON_DOCKER_TESTS=1 pytest -m docker -v
"""
from __future__ import annotations

import os
import time
import uuid

import pytest

from eidolon.orchestrator.lib.substrate import (
    DockerSubstrate,
    NetworkSpec,
    VMSpec,
)


def _docker_available() -> bool:
    if os.environ.get("EIDOLON_DOCKER_TESTS") != "1":
        return False
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not _docker_available(), reason="EIDOLON_DOCKER_TESTS!=1 or daemon unreachable"),
]


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def test_full_lifecycle_busybox() -> None:
    sub = DockerSubstrate()
    eng_id = f"ENG-test-{_suffix()}"
    net_name = f"eidolon-{eng_id}"
    vm_name = f"eidolon-vm-{_suffix()}"

    net = sub.network_create(NetworkSpec(engagement_id=eng_id, name=net_name))
    try:
        vm = sub.provision(
            VMSpec(
                name=vm_name,
                image="busybox:latest",
                network=net.name,
                cmd=["sh", "-c", "sleep 30"],
                memory_mb=64,
                cpu=1,
            )
        )
        try:
            assert vm.name == vm_name
            assert vm.network == net.name
            sub.secrets_inject(vm, {"api_key": "abc123"})
            time.sleep(0.2)
            snap = sub.snapshot(vm)
            assert snap.vm_id == vm.id
            assert snap.driver == "docker"
        finally:
            sub.destroy(vm)
    finally:
        sub.network_destroy(net)
