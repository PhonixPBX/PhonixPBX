"""Firmware updates: signed A/B update bundles.

Bundle format (built by image/mkbundle.sh): an uncompressed tar containing
``manifest.json`` (``{"version", "board", "files": {name: sha256}}``),
``manifest.sig`` (raw ed25519 signature over manifest.json) and the payload
files. The Python side verifies signature, board and hashes; the root helper
writes the payload into the inactive slot.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from phonix import __version__, config
from phonix.services import privileged
from phonix.services.common import ServiceError

MAX_BUNDLE = 1024**3


@dataclass
class BundleInfo:
    version: str
    board: str
    files: dict[str, str]


def current_board() -> str:
    path = config.get().path("/etc/phonix/board")
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return "dev"


def current_slot() -> str:
    try:
        cmdline = Path("/proc/cmdline").read_text()
    except OSError:
        return "?"
    for token in cmdline.split():
        if token.startswith("phonix.slot="):
            return token.split("=", 1)[1]
    return "?"


def _public_key() -> Ed25519PublicKey:
    path = config.get().update_pubkey_path
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (FileNotFoundError, ValueError) as exc:
        raise ServiceError("No update signing key installed on this system") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ServiceError("Update signing key is not an ed25519 key")
    return key


def verify_bundle(path: Path) -> BundleInfo:
    if path.stat().st_size > MAX_BUNDLE:
        raise ServiceError("Update file is too large")
    try:
        with tarfile.open(path, mode="r:") as tar:
            names = {m.name: m for m in tar.getmembers()}
            if "manifest.json" not in names or "manifest.sig" not in names:
                raise ServiceError("Not a PhonixPBX update bundle")
            manifest_raw = tar.extractfile(names["manifest.json"]).read()  # type: ignore[union-attr]
            signature = tar.extractfile(names["manifest.sig"]).read()  # type: ignore[union-attr]
            try:
                _public_key().verify(signature, manifest_raw)
            except InvalidSignature as exc:
                raise ServiceError("Update signature is invalid") from exc
            manifest = json.loads(manifest_raw)
            info = BundleInfo(manifest["version"], manifest["board"], dict(manifest["files"]))
            if info.board != current_board():
                raise ServiceError(f"Update is for board {info.board}, this system is {current_board()}")
            for name, digest in info.files.items():
                member = names.get(name)
                if member is None or not member.isfile():
                    raise ServiceError(f"Update bundle is missing {name}")
                h = hashlib.sha256()
                fh = tar.extractfile(member)
                assert fh is not None
                while chunk := fh.read(1024 * 1024):
                    h.update(chunk)
                if h.hexdigest() != digest:
                    raise ServiceError(f"Checksum mismatch for {name}")
    except (tarfile.TarError, KeyError, ValueError) as exc:
        raise ServiceError(f"Not a valid update bundle: {exc}") from exc
    return info


def install(path: Path) -> BundleInfo:
    info = verify_bundle(path)
    privileged.run("install-update", str(path), timeout=900)
    return info


def status() -> dict[str, str]:
    return {"version": __version__, "board": current_board(), "slot": current_slot()}
