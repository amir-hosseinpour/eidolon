from __future__ import annotations

import json
import shutil

import pytest
from click.testing import CliRunner

import eidolon.cli.main as cli_main
from eidolon.orchestrator.lib.secrets import (
    EnvBackend,
    KeychainBackend,
    OnePasswordBackend,
    SecretsBroker,
    SecretsError,
    get_backend,
    reset_backend,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_backend()
    monkeypatch.setenv("EIDOLON_SECRETS_BACKEND", "env")
    yield
    reset_backend()


def test_env_backend_roundtrip() -> None:
    b = EnvBackend()
    assert b.get("api_key") is None
    b.put("api_key", "topsecret")
    assert b.get("api_key") == "topsecret"
    assert b.delete("api_key") is True
    assert b.get("api_key") is None
    assert b.delete("api_key") is False


def test_label_validation() -> None:
    b = EnvBackend()
    with pytest.raises(SecretsError):
        b.put("Bad-Label", "x")  # uppercase + dash not allowed
    with pytest.raises(SecretsError):
        b.put("", "x")
    with pytest.raises(SecretsError):
        b.put("-leading-dash", "x")


def test_broker_resolve_required_raises_on_missing() -> None:
    broker = SecretsBroker(EnvBackend())
    broker.put("present_a", "1")
    with pytest.raises(SecretsError) as exc:
        broker.resolve_required(["present_a", "missing_b", "missing_c"])
    assert "missing_secrets" in exc.value.reason
    assert "missing_b" in exc.value.reason
    assert "missing_c" in exc.value.reason


def test_broker_resolve_required_returns_map() -> None:
    broker = SecretsBroker(EnvBackend())
    broker.put("a", "1")
    broker.put("b", "2")
    out = broker.resolve_required(["a", "b"])
    assert out == {"a": "1", "b": "2"}


def test_get_backend_selects_env_by_default() -> None:
    backend = get_backend()
    assert backend.name == "env"
    assert backend.available() is True


def test_unknown_backend_name_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_SECRETS_BACKEND", "snowflake")
    reset_backend()
    with pytest.raises(SecretsError):
        get_backend(force=True)


def test_keychain_unavailable_returns_falsy_when_security_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    b = KeychainBackend()
    assert b.available() is False
    with pytest.raises(SecretsError):
        b.get("anything")


def test_op_unavailable_returns_falsy_when_op_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    b = OnePasswordBackend()
    assert b.available() is False
    with pytest.raises(SecretsError):
        b.get("anything")


# CLI


def test_cli_secrets_backend() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_main.main, ["secrets", "backend"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["backend"] == "env"
    assert body["available"] is True


def test_cli_secrets_store_get_revoke_roundtrip() -> None:
    runner = CliRunner()
    put_res = runner.invoke(
        cli_main.main, ["secrets", "store", "demo_key", "--value", "hunter2"]
    )
    assert put_res.exit_code == 0, put_res.output

    get_res = runner.invoke(cli_main.main, ["secrets", "get", "demo_key"])
    assert get_res.exit_code == 0, get_res.output
    assert get_res.output.strip() == "hunter2"

    list_res = runner.invoke(cli_main.main, ["secrets", "list"])
    assert list_res.exit_code == 0, list_res.output
    list_body = json.loads(list_res.output)
    assert list_body["backend"] == "env"
    assert "demo_key" in list_body["labels"]

    del_res = runner.invoke(cli_main.main, ["secrets", "revoke", "demo_key"])
    assert del_res.exit_code == 0, del_res.output
    body = json.loads(del_res.output)
    assert body["status"] == "ok"

    missing = runner.invoke(cli_main.main, ["secrets", "get", "demo_key"])
    assert missing.exit_code == 1


def test_cli_secrets_store_reads_stdin_when_no_value() -> None:
    runner = CliRunner()
    res = runner.invoke(
        cli_main.main,
        ["secrets", "store", "from_stdin"],
        input="from-stdin-value\n",
    )
    assert res.exit_code == 0, res.output
    get_res = runner.invoke(cli_main.main, ["secrets", "get", "from_stdin"])
    assert get_res.output.strip() == "from-stdin-value"
