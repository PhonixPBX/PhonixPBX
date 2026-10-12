"""Runtime configuration: filesystem locations and process-level options.

Everything is overridable through ``ASKOZIA_*`` environment variables so the
same code runs on the appliance (defaults below), in the dev container and in
tests (which point everything at a temporary directory).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"ASKOZIA_{name}", default)


@dataclass(frozen=True)
class RuntimeConfig:
    # persistent data partition (ASKDATA)
    data_dir: Path
    # prefix for every generated system file ("/" on the appliance)
    root: Path
    # how privileged actions are executed: "doas" (appliance) or "dry-run"
    privileged_mode: str
    libexec_dir: Path
    boot_dir: Path
    ami_host: str
    ami_port: int
    # dev mode relaxes cookie "Secure" flag and enables autoreload helpers
    dev: bool
    log_files: dict[str, Path] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "askozia.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def secrets_path(self) -> Path:
        return self.data_dir / "secrets.json"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def state_dir(self) -> Path:
        """Small runtime state files that must survive reboots (reports etc.)."""
        return self.data_dir / "state"

    def path(self, absolute: str) -> Path:
        """Map an absolute target path (e.g. ``/etc/asterisk``) below ``root``."""
        return self.root / absolute.lstrip("/")

    @property
    def asterisk_conf_dir(self) -> Path:
        return self.path("/etc/asterisk")

    @property
    def askozia_etc_dir(self) -> Path:
        return self.path("/etc/askozia")

    @property
    def staged_dir(self) -> Path:
        """Files that a privileged helper installs into root-owned places."""
        return self.path("/run/askozia/staged")

    @property
    def update_pubkey_path(self) -> Path:
        return self.path("/etc/askozia/update-key.pub")

    @property
    def tls_cert_path(self) -> Path:
        return self.data_dir / "tls" / "server.crt"

    @property
    def tls_key_path(self) -> Path:
        return self.data_dir / "tls" / "server.key"


def load() -> RuntimeConfig:
    root = Path(_env("ROOT", "/"))
    return RuntimeConfig(
        data_dir=Path(_env("DATA_DIR", "/data")),
        root=root,
        privileged_mode=_env("PRIVILEGED", "doas"),
        libexec_dir=Path(_env("LIBEXEC_DIR", "/usr/libexec/askozia")),
        boot_dir=Path(_env("BOOT_DIR", "/media/boot")),
        ami_host=_env("AMI_HOST", "127.0.0.1"),
        ami_port=int(_env("AMI_PORT", "5038")),
        dev=_env("DEV", "0") == "1",
        log_files={
            "asterisk": Path(_env("LOG_ASTERISK", "/var/log/asterisk/messages")),
            "system": Path(_env("LOG_SYSTEM", "/var/log/messages")),
        },
    )


@lru_cache(maxsize=1)
def get() -> RuntimeConfig:
    return load()


def reset_cache() -> None:
    get.cache_clear()
