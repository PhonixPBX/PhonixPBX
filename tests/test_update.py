# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Firmware update bundles."""

import io
import tarfile

import pytest

from phonix.services import update
from phonix.services.common import ServiceError


def _bundle(path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


@pytest.mark.parametrize(
    "members",
    [
        {"manifest.json": b" " * (update.MAX_MANIFEST + 1), "manifest.sig": b"sig"},
        {"manifest.json": b"{}", "manifest.sig": b"s" * (update.MAX_SIGNATURE + 1)},
    ],
)
def test_oversized_manifest_is_rejected_before_reading(runtime, tmp_path, monkeypatch, members):
    def no_key():  # the signature check must not be reached
        raise AssertionError("manifest was read")

    monkeypatch.setattr(update, "_public_key", no_key)
    bundle = tmp_path / "x.update"
    _bundle(bundle, members)
    with pytest.raises(ServiceError, match="Not a PhonixPBX update bundle"):
        update.verify_bundle(bundle)


def test_scheduled_check(initialized, monkeypatch, capsys):
    import json

    from phonix import cli
    from phonix.core import settings as st
    from phonix.core.db import session_scope

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return io.BytesIO(json.dumps({"version": "99.0.0", "url": "https://example.com/r"}).encode())

    monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
    assert update.available() is None
    # periodic job: nothing happens unless "Check automatically" is on
    assert cli.main(["update", "check", "--auto"]) == 0
    assert calls == [] and update.available() is None
    with session_scope() as s:
        st.save(s, st.UpdateSettings(auto_check=True))
    assert cli.main(["update", "check", "--auto"]) == 0
    assert "version 99.0.0 is available" in capsys.readouterr().out
    assert update.available() == update.Release("99.0.0", "https://example.com/r")
    # after updating, the stored result is no longer newer
    monkeypatch.setattr(update, "__version__", "99.0.0")
    assert update.available() is None


def test_check_online_errors(runtime):
    with pytest.raises(ServiceError, match="https://"):
        update.check_online("http://example.com/latest")


def test_verify_bundle_reports_progress(runtime, tmp_path, monkeypatch):
    import hashlib
    import json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(update, "_public_key", key.public_key)
    monkeypatch.setattr(update, "current_board", lambda: "pc-amd64")
    payload = {"rootfs.squashfs": b"r" * (3 * 1024 * 1024), "vmlinuz": b"k" * 1024}
    files = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    manifest = json.dumps({"version": "9.9.9", "board": "pc-amd64", "files": files}).encode()
    bundle = tmp_path / "x.update"
    _bundle(bundle, {"manifest.json": manifest, "manifest.sig": key.sign(manifest), **payload})
    seen: list[int] = []
    assert update.verify_bundle(bundle, seen.append).version == "9.9.9"
    assert seen == sorted(seen) and seen[-1] == 100 and len(seen) > 2
