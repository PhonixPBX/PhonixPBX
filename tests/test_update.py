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
