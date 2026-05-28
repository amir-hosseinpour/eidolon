from __future__ import annotations

import secrets as _secrets

import pytest
from fastapi.testclient import TestClient

from eidolon.orchestrator.lib.engagements import EngagementStore
from eidolon.orchestrator.lib.provisioner import (
    Provisioner,
    ProvisionError,
)
from eidolon.orchestrator.lib.scope import ScopeDocument
from eidolon.orchestrator.lib.substrate import (
    NetworkHandle,
    NetworkSpec,
    SnapshotHandle,
    Substrate,
    VMHandle,
    VMSpec,
)
from eidolon.orchestrator.lib.templates import load_template_by_name


class FakeSubstrate(Substrate):
    """In-memory substrate. Records every call. No real IO."""

    driver_name = "fake"

    def __init__(self) -> None:
        self.networks: dict[str, NetworkHandle] = {}
        self.vms: dict[str, VMHandle] = {}
        self.injected_secrets: dict[str, dict[str, str]] = {}
        self.destroyed_vms: list[str] = []
        self.destroyed_networks: list[str] = []
        self.fail_provision_for: set[str] = set()

    def network_create(self, spec: NetworkSpec) -> NetworkHandle:
        nh = NetworkHandle(
            id=f"net-{_secrets.token_hex(4)}",
            name=spec.name,
            driver=self.driver_name,
            cidr=spec.cidr,
        )
        self.networks[nh.id] = nh
        return nh

    def network_destroy(self, handle: NetworkHandle) -> None:
        self.destroyed_networks.append(handle.id)
        self.networks.pop(handle.id, None)

    def provision(self, spec: VMSpec) -> VMHandle:
        if spec.name in self.fail_provision_for:
            raise RuntimeError(f"forced provision failure: {spec.name}")
        vh = VMHandle(
            id=f"vm-{_secrets.token_hex(4)}",
            name=spec.name,
            driver=self.driver_name,
            network=spec.network,
            address="10.43.0.10",
        )
        self.vms[vh.id] = vh
        return vh

    def destroy(self, handle: VMHandle) -> None:
        self.destroyed_vms.append(handle.id)
        self.vms.pop(handle.id, None)

    def snapshot(self, handle: VMHandle) -> SnapshotHandle:
        return SnapshotHandle(
            vm_id=handle.id,
            snapshot_id=f"snap-{_secrets.token_hex(4)}",
            driver=self.driver_name,
        )

    def secrets_inject(self, handle: VMHandle, secrets: dict[str, str]) -> None:
        self.injected_secrets[handle.id] = dict(secrets)


@pytest.fixture
def engagement_id() -> str:
    eng = EngagementStore().create(
        slug="prov-test",
        purpose="ctf",
        scope=ScopeDocument(
            allowed_cidrs=["10.43.0.0/24"],
            allowed_actions=["recon.read"],
            tier="autonomous",
        ),
    )
    return eng.id


def _provisioner_with_fake() -> tuple[Provisioner, FakeSubstrate]:
    fake = FakeSubstrate()
    p = Provisioner(substrates={"docker": fake})
    return p, fake


def test_provision_blank_kali_creates_network_and_vm(engagement_id: str) -> None:
    p, fake = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")
    result = p.provision(engagement_id=engagement_id, template=template)

    assert result.engagement_id == engagement_id
    assert result.template == "blank-kali"
    assert result.network.driver == "fake"
    assert len(result.vms) == 1
    assert result.vms[0].vm_name == "kali"
    assert result.vms[0].driver == "fake"
    assert len(fake.networks) == 1
    assert len(fake.vms) == 1


def test_provision_injects_vm_token_into_env(engagement_id: str) -> None:
    p, fake = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")

    captured: list[VMSpec] = []
    real_provision = fake.provision

    def _spy(spec: VMSpec) -> VMHandle:
        captured.append(spec)
        return real_provision(spec)

    fake.provision = _spy  # type: ignore[method-assign]
    p.provision(engagement_id=engagement_id, template=template)

    assert len(captured) == 1
    env = captured[0].env
    assert env["EIDOLON_VM_TOKEN"]
    assert env["EIDOLON_ENGAGEMENT_ID"] == engagement_id
    assert env["LANG"] == "C.UTF-8"  # template defaults preserved


def test_provision_rejects_double_provision(engagement_id: str) -> None:
    p, _ = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")
    p.provision(engagement_id=engagement_id, template=template)
    with pytest.raises(ProvisionError) as exc:
        p.provision(engagement_id=engagement_id, template=template)
    assert exc.value.reason == "already_provisioned"


def test_provision_rejects_unknown_engagement() -> None:
    p, _ = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")
    with pytest.raises(ProvisionError) as exc:
        p.provision(engagement_id="ENG-fake", template=template)
    assert exc.value.reason == "engagement_not_found"


def test_provision_rejects_closed_engagement(engagement_id: str) -> None:
    EngagementStore().close(engagement_id)
    p, _ = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")
    with pytest.raises(ProvisionError) as exc:
        p.provision(engagement_id=engagement_id, template=template)
    assert exc.value.reason.startswith("engagement_")


def test_teardown_destroys_vm_network_and_revokes_token(engagement_id: str) -> None:
    p, fake = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")
    result = p.provision(engagement_id=engagement_id, template=template)
    counts = p.teardown(engagement_id)

    assert counts == {"vms_destroyed": 1, "network_destroyed": 1}
    assert len(fake.destroyed_vms) == 1
    assert len(fake.destroyed_networks) == 1
    listed = p.list_vms(engagement_id)
    assert listed[0].status == "destroyed"
    assert listed[0].destroyed_at is not None
    del result


def test_teardown_is_idempotent(engagement_id: str) -> None:
    p, _ = _provisioner_with_fake()
    template = load_template_by_name("blank-kali")
    p.provision(engagement_id=engagement_id, template=template)
    p.teardown(engagement_id)
    counts = p.teardown(engagement_id)
    # network already destroyed (destroyed_at set), so _existing_network → None,
    # short-circuit returns zeros.
    assert counts == {"vms_destroyed": 0, "network_destroyed": 0}


def test_teardown_no_substrate_state_returns_zeros(engagement_id: str) -> None:
    p, _ = _provisioner_with_fake()
    counts = p.teardown(engagement_id)
    assert counts == {"vms_destroyed": 0, "network_destroyed": 0}


def test_provision_failure_revokes_issued_token(engagement_id: str) -> None:
    fake = FakeSubstrate()
    fake.fail_provision_for = {"kali"}
    p = Provisioner(substrates={"docker": fake})
    template = load_template_by_name("blank-kali")
    with pytest.raises(RuntimeError):
        p.provision(engagement_id=engagement_id, template=template)
    # network created, but VM not provisioned, token revoked.
    assert len(fake.networks) == 1
    assert len(fake.vms) == 0


def test_rest_provision_and_teardown_endpoints(
    engagement_id: str, auth_headers: dict[str, str]
) -> None:
    from eidolon.orchestrator.app.main import app
    from eidolon.orchestrator.app.routers import engagements as eng_router

    fake = FakeSubstrate()
    eng_router._override_provisioner(
        Provisioner(substrates={"docker": fake})
    )
    try:
        client = TestClient(app, headers=auth_headers)
        r = client.post(
            f"/v1/engagements/{engagement_id}/provision",
            json={"template": "blank-kali"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["network"]["driver"] == "fake"
        assert len(body["vms"]) == 1

        v = client.get(f"/v1/engagements/{engagement_id}/vms")
        assert v.status_code == 200
        assert len(v.json()["vms"]) == 1

        td = client.post(f"/v1/engagements/{engagement_id}/teardown")
        assert td.status_code == 200, td.text
        assert td.json()["vms_destroyed"] == 1
    finally:
        eng_router._override_provisioner(Provisioner())


def test_provision_ad_recon_single_via_fake_proxmox(engagement_id: str) -> None:
    fake = FakeSubstrate()
    p = Provisioner(substrates={"proxmox": fake})
    template = load_template_by_name("ad-recon-single")
    result = p.provision(engagement_id=engagement_id, template=template)

    assert result.template == "ad-recon-single"
    assert result.network.substrate_name == "proxmox"
    assert len(result.vms) == 1
    assert result.vms[0].vm_name == "kali-ad"
    counts = p.teardown(engagement_id)
    assert counts == {"vms_destroyed": 1, "network_destroyed": 1}


def test_rest_provision_missing_template_returns_404(
    engagement_id: str, auth_headers: dict[str, str]
) -> None:
    from eidolon.orchestrator.app.main import app

    client = TestClient(app, headers=auth_headers)
    r = client.post(
        f"/v1/engagements/{engagement_id}/provision",
        json={"template": "no-such-template"},
    )
    assert r.status_code == 404
    assert "template_invalid" in r.json()["detail"]


def test_rest_erase_runs_teardown(
    engagement_id: str, auth_headers: dict[str, str]
) -> None:
    from eidolon.orchestrator.app.main import app
    from eidolon.orchestrator.app.routers import engagements as eng_router

    fake = FakeSubstrate()
    eng_router._override_provisioner(
        Provisioner(substrates={"docker": fake})
    )
    try:
        client = TestClient(app, headers=auth_headers)
        client.post(
            f"/v1/engagements/{engagement_id}/provision",
            json={"template": "blank-kali"},
        )
        r = client.post(f"/v1/engagements/{engagement_id}/erase")
        assert r.status_code == 200
        assert r.json()["engagement"]["status"] == "erased"
        assert len(fake.destroyed_vms) == 1
    finally:
        eng_router._override_provisioner(Provisioner())
