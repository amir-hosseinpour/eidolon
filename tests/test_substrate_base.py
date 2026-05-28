from __future__ import annotations

import pytest

from eidolon.orchestrator.lib.substrate import (
    DockerSubstrate,
    MacSubstrate,
    NetworkHandle,
    NetworkSpec,
    Substrate,
    VMHandle,
    VMSpec,
    WindowsSubstrate,
)


def test_substrate_is_abstract() -> None:
    with pytest.raises(TypeError):
        Substrate()  # type: ignore[abstract]


def test_dataclasses_are_frozen() -> None:
    spec = NetworkSpec(engagement_id="ENG-1", name="net")
    with pytest.raises(AttributeError):
        spec.name = "other"  # type: ignore[misc]


@pytest.mark.parametrize("driver", [MacSubstrate(), WindowsSubstrate()])
def test_stub_drivers_raise_not_implemented(driver: Substrate) -> None:
    spec = NetworkSpec(engagement_id="ENG-1", name="n")
    handle = NetworkHandle(id="x", name="n", driver=driver.driver_name)
    vm_spec = VMSpec(name="vm", image="busybox", network="n")
    vm_handle = VMHandle(id="x", name="vm", driver=driver.driver_name, network="n")
    with pytest.raises(NotImplementedError):
        driver.network_create(spec)
    with pytest.raises(NotImplementedError):
        driver.network_destroy(handle)
    with pytest.raises(NotImplementedError):
        driver.provision(vm_spec)
    with pytest.raises(NotImplementedError):
        driver.destroy(vm_handle)
    with pytest.raises(NotImplementedError):
        driver.snapshot(vm_handle)
    with pytest.raises(NotImplementedError):
        driver.secrets_inject(vm_handle, {"k": "v"})


def test_docker_substrate_driver_name() -> None:
    assert DockerSubstrate.driver_name == "docker"


def test_docker_unreachable_returns_stable_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """When docker daemon is unreachable, accessing .client raises DockerError
    with reason='docker_unreachable'."""
    import docker as docker_mod

    from eidolon.orchestrator.lib.substrate.docker_substrate import DockerError

    def _boom() -> None:
        raise RuntimeError("daemon down")

    monkeypatch.setattr(docker_mod, "from_env", _boom)
    sub = DockerSubstrate()
    with pytest.raises(DockerError) as exc:
        _ = sub.client
    assert exc.value.reason == "docker_unreachable"
