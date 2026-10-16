# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
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
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from phonix import __version__, config
from phonix.i18n import _
from phonix.services import platform, privileged
from phonix.services.common import ServiceError

MAX_BUNDLE = 1024**3
MAX_MANIFEST = 1024**2
MAX_SIGNATURE = 1024

# PEP 440 (1.2.0, 1.2.0rc1, 1.2.0.post1, 1.3.0.dev0), with an optional "v" prefix; the
# semver spellings 1.2.0-rc.1 and 1.2.0-alpha normalise the same way. Local versions (+build) are ignored.
_VERSION_RE = re.compile(
    r"v?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-_.]?(?P<pre_l>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pre_n>\d+)?)?"
    r"(?:-(?P<post_n1>\d+)|[-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n2>\d+)?)?"
    r"(?:[-_.]?(?P<dev_l>dev)[-_.]?(?P<dev_n>\d+)?)?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?",
    re.IGNORECASE,
)
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}


def version_key(value: str) -> tuple[Any, ...] | None:
    """PEP 440 sort key, or None if ``value`` isn't a version."""
    m = _VERSION_RE.fullmatch(value.strip())
    if not m:
        return None
    release = tuple(int(x) for x in m["release"].split("."))
    while len(release) > 1 and release[-1] == 0:
        release = release[:-1]
    has_post = m["post_n1"] is not None or m["post_l"] is not None
    if m["pre_l"]:
        pre: tuple[int, ...] = (1, _PRE_RANK[m["pre_l"].lower()], int(m["pre_n"] or 0))
    elif m["dev_l"] and not has_post:
        pre = (0,)  # 1.2.0.dev0 sorts before 1.2.0a1
    else:
        pre = (2,)  # a release sorts after its pre-releases
    post = (int(m["post_n1"] or m["post_n2"] or 0),) if has_post else (-1,)
    dev = (0, int(m["dev_n"] or 0)) if m["dev_l"] else (1,)
    return (release, pre, post, dev)


def is_newer(latest: str, current: str) -> bool:
    """True if ``latest`` is a newer release than ``current``; falls back to inequality for unknown formats."""
    a, b = version_key(latest), version_key(current)
    if a is None or b is None:
        return latest.removeprefix("v") != current.removeprefix("v")
    return a > b


@dataclass
class BundleInfo:
    version: str
    board: str
    files: dict[str, str]


def current_board() -> str:
    return platform.board()


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
        raise ServiceError(_("No update signing key installed on this system")) from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ServiceError(_("Update signing key is not an ed25519 key"))
    return key


def verify_bundle(path: Path) -> BundleInfo:
    if platform.is_container():
        raise ServiceError(_(platform.CONTAINER_UPDATE_HINT))
    if path.stat().st_size > MAX_BUNDLE:
        raise ServiceError(_("Update file is too large"))
    try:
        with tarfile.open(path, mode="r:") as tar:
            names = {m.name: m for m in tar.getmembers()}
            if "manifest.json" not in names or "manifest.sig" not in names:
                raise ServiceError(_("Not a PhonixPBX update bundle"))
            # read into memory before the signature check: same limits as verify-manifest
            if names["manifest.json"].size > MAX_MANIFEST or names["manifest.sig"].size > MAX_SIGNATURE:
                raise ServiceError(_("Not a PhonixPBX update bundle"))
            manifest_raw = tar.extractfile(names["manifest.json"]).read()  # type: ignore[union-attr]
            signature = tar.extractfile(names["manifest.sig"]).read()  # type: ignore[union-attr]
            try:
                _public_key().verify(signature, manifest_raw)
            except InvalidSignature as exc:
                raise ServiceError(_("Update signature is invalid")) from exc
            manifest = json.loads(manifest_raw)
            info = BundleInfo(manifest["version"], manifest["board"], dict(manifest["files"]))
            if info.board != current_board():
                raise ServiceError(
                    _(
                        "Update is for board %(board)s, this system is %(current)s",
                        board=info.board,
                        current=current_board(),
                    )
                )
            for name, digest in info.files.items():
                member = names.get(name)
                if member is None or not member.isfile():
                    raise ServiceError(_("Update bundle is missing %(name)s", name=name))
                h = hashlib.sha256()
                fh = tar.extractfile(member)
                assert fh is not None
                while chunk := fh.read(1024 * 1024):
                    h.update(chunk)
                if h.hexdigest() != digest:
                    raise ServiceError(_("Checksum mismatch for %(name)s", name=name))
    except (tarfile.TarError, KeyError, ValueError) as exc:
        raise ServiceError(_("Not a valid update bundle: %(error)s", error=exc)) from exc
    return info


def install(path: Path) -> BundleInfo:
    info = verify_bundle(path)
    privileged.run("install-update", str(path), timeout=900)
    return info


def status() -> dict[str, str]:
    board = current_board()
    return {
        "version": __version__,
        "board": board,
        "slot": "-" if platform.is_container(board) else current_slot(),
        "platform": platform.kind(board),
    }
