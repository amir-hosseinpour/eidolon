from __future__ import annotations

import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Literal

BackendName = Literal["env", "keychain", "op"]

_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,62}$")


class SecretsError(Exception):
    """Raised on a secrets-broker operation failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _validate_label(label: str) -> None:
    if not _LABEL_RE.match(label):
        raise SecretsError(f"invalid_label: {label!r}")


class SecretsBackend(ABC):
    """One backend = one storage system. v0.1 ships env, macOS Keychain,
    and 1Password CLI. The broker selects by EIDOLON_SECRETS_BACKEND."""

    name: BackendName

    @abstractmethod
    def get(self, label: str) -> str | None: ...

    @abstractmethod
    def put(self, label: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, label: str) -> bool: ...

    @abstractmethod
    def available(self) -> bool: ...


class EnvBackend(SecretsBackend):
    """Reads from EIDOLON_SECRET_<UPPER_LABEL> env vars. In-process puts use
    os.environ — fine for tests, fine for hand-off scripts that pre-set
    secrets, NOT a long-term store."""

    name: BackendName = "env"

    def _key(self, label: str) -> str:
        return f"EIDOLON_SECRET_{label.upper()}"

    def get(self, label: str) -> str | None:
        _validate_label(label)
        return os.environ.get(self._key(label))

    def put(self, label: str, value: str) -> None:
        _validate_label(label)
        os.environ[self._key(label)] = value

    def delete(self, label: str) -> bool:
        _validate_label(label)
        return os.environ.pop(self._key(label), None) is not None

    def available(self) -> bool:
        return True


class KeychainBackend(SecretsBackend):
    """macOS Keychain via the `security` CLI. Each secret is stored under the
    `eidolon` account, with the engagement-scoped label as the service name."""

    name: BackendName = "keychain"
    ACCOUNT = "eidolon"

    def available(self) -> bool:
        return shutil.which("security") is not None

    def _service(self, label: str) -> str:
        return f"eidolon.{label}"

    def get(self, label: str) -> str | None:
        _validate_label(label)
        if not self.available():
            raise SecretsError("keychain_unavailable")
        try:
            out = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-a", self.ACCOUNT,
                    "-s", self._service(label),
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return out.stdout.rstrip("\n")
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 44:  # SecKeychainItemNotFound
                return None
            raise SecretsError(f"keychain_get_failed: {exc.stderr.strip()}") from exc

    def put(self, label: str, value: str) -> None:
        _validate_label(label)
        if not self.available():
            raise SecretsError("keychain_unavailable")
        try:
            subprocess.run(
                [
                    "security", "add-generic-password",
                    "-a", self.ACCOUNT,
                    "-s", self._service(label),
                    "-w", value,
                    "-U",  # update if exists
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise SecretsError(f"keychain_put_failed: {exc.stderr.strip()}") from exc

    def delete(self, label: str) -> bool:
        _validate_label(label)
        if not self.available():
            raise SecretsError("keychain_unavailable")
        result = subprocess.run(
            [
                "security", "delete-generic-password",
                "-a", self.ACCOUNT,
                "-s", self._service(label),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0


class OnePasswordBackend(SecretsBackend):
    """1Password via the `op` CLI. Secrets are stored in a vault named by
    EIDOLON_OP_VAULT (default 'Eidolon'), one item per label."""

    name: BackendName = "op"

    def __init__(self, vault: str | None = None) -> None:
        self.vault = vault or os.environ.get("EIDOLON_OP_VAULT", "Eidolon")

    def available(self) -> bool:
        if shutil.which("op") is None:
            return False
        return os.environ.get("OP_SESSION") is not None or self._signed_in()

    def _signed_in(self) -> bool:
        try:
            subprocess.run(
                ["op", "account", "get"],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _item_title(self, label: str) -> str:
        return f"eidolon-{label}"

    def get(self, label: str) -> str | None:
        _validate_label(label)
        if not self.available():
            raise SecretsError("op_unavailable")
        ref = f"op://{self.vault}/{self._item_title(label)}/password"
        try:
            out = subprocess.run(
                ["op", "read", ref],
                check=True,
                capture_output=True,
                text=True,
            )
            return out.stdout.rstrip("\n")
        except subprocess.CalledProcessError as exc:
            if "isn't an item" in exc.stderr or "not found" in exc.stderr.lower():
                return None
            raise SecretsError(f"op_get_failed: {exc.stderr.strip()}") from exc

    def put(self, label: str, value: str) -> None:
        _validate_label(label)
        if not self.available():
            raise SecretsError("op_unavailable")
        title = self._item_title(label)
        existing = self.get(label)
        if existing is None:
            cmd = [
                "op", "item", "create",
                "--category=password",
                f"--vault={self.vault}",
                f"--title={title}",
                f"password={value}",
            ]
        else:
            cmd = [
                "op", "item", "edit", title,
                f"--vault={self.vault}",
                f"password={value}",
            ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise SecretsError(f"op_put_failed: {exc.stderr.strip()}") from exc

    def delete(self, label: str) -> bool:
        _validate_label(label)
        if not self.available():
            raise SecretsError("op_unavailable")
        result = subprocess.run(
            [
                "op", "item", "delete", self._item_title(label),
                f"--vault={self.vault}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0


def _select_backend() -> SecretsBackend:
    name = os.environ.get("EIDOLON_SECRETS_BACKEND", "env").strip().lower()
    if name == "env":
        return EnvBackend()
    if name == "keychain":
        return KeychainBackend()
    if name == "op":
        return OnePasswordBackend()
    raise SecretsError(f"unknown_backend: {name!r}")


_backend: SecretsBackend | None = None


def get_backend(force: bool = False) -> SecretsBackend:
    global _backend
    if _backend is None or force:
        _backend = _select_backend()
    return _backend


def reset_backend() -> None:
    global _backend
    _backend = None


class SecretsBroker:
    """Orchestrator-side facade that template/engagement code uses to fetch
    secrets without caring about the backend."""

    def __init__(self, backend: SecretsBackend | None = None) -> None:
        self._backend = backend or get_backend()

    @property
    def backend_name(self) -> BackendName:
        return self._backend.name

    def get(self, label: str) -> str | None:
        return self._backend.get(label)

    def put(self, label: str, value: str) -> None:
        self._backend.put(label, value)

    def delete(self, label: str) -> bool:
        return self._backend.delete(label)

    def resolve_required(self, labels: list[str]) -> dict[str, str]:
        """Resolve every required label to a value. Raises if any are missing.
        Used right before substrate.secrets_inject(...)."""
        out: dict[str, str] = {}
        missing: list[str] = []
        for label in labels:
            value = self._backend.get(label)
            if value is None:
                missing.append(label)
            else:
                out[label] = value
        if missing:
            raise SecretsError(f"missing_secrets: {','.join(sorted(missing))}")
        return out
