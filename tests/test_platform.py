# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Container boards (LXC/Incus, OCI): host-managed network, no firmware updates."""

import subprocess

import pytest
from test_web import client, login  # noqa: F401 - fixture

from phonix import config
from phonix.services import apply, platform, privileged, update
from phonix.services.common import ServiceError


def _set_board(runtime, name: str) -> None:
    path = runtime.path("/etc/phonix/board")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name + "\n")


@pytest.mark.parametrize(
    ("board", "kind", "container"),
    [
        ("dev", "dev", False),
        ("pc-amd64", "appliance", False),
        ("rpi-arm64", "appliance", False),
        ("lxc-amd64", "lxc", True),
        ("lxc-arm64", "lxc", True),
        ("oci-amd64", "oci", True),
    ],
)
def test_board_kinds(runtime, board, kind, container):
    if board != "dev":
        _set_board(runtime, board)
    assert platform.board() == board
    assert platform.kind() == kind
    assert platform.is_container() is container


def test_container_apply_leaves_network_and_hostname_alone(session, runtime):
    _set_board(runtime, "lxc-amd64")
    privileged.recorder.calls.clear()
    result = apply.apply(session, user="t", boot=True)
    assert "/etc/asterisk/pjsip.conf" in result.changed_files
    assert "/etc/nftables.nft" in result.changed_files
    for path in ("/etc/network/interfaces", "/etc/hostname", "/etc/hosts", "/etc/resolv.conf"):
        assert path not in result.changed_files
        assert not runtime.path(path).exists()
    # a later (non-boot) apply does not ask the helper to install them either
    result = apply.apply(session, user="t", force=True)
    assert ("install-staged", "system:firewall") in privileged.recorder.calls
    assert ("install-staged", "system:network") not in privileged.recorder.calls
    assert ("install-staged", "system:hostname") not in privileged.recorder.calls


def test_container_rejects_firmware_bundles(runtime, tmp_path):
    _set_board(runtime, "oci-amd64")
    bundle = tmp_path / "x.update"
    bundle.write_bytes(b"not relevant")
    with pytest.raises(ServiceError, match="container"):
        update.install(bundle)
    assert update.status()["slot"] == "-"
    assert update.status()["platform"] == "oci"


def test_firmware_page_in_container(client, runtime):  # noqa: F811
    login(client)
    assert "Install an update" in client.get("/system/firmware").text
    _set_board(runtime, "lxc-amd64")
    page = client.get("/system/firmware").text
    assert "Updates: replace the container image" in page
    assert "Install an update" not in page
    assert "configured on the container host" in client.get("/system/network").text


def test_fix_data_ownership_leaves_root_and_asterisk_dirs_alone(runtime, monkeypatch):
    """/data/ssh (root login keys), the voicemail spool and nginx' temp dir
    must not be handed to the web user."""
    import os

    from phonix.services import ownership

    data = runtime.data_dir
    for sub in ("ssh/dropbear", "spool/voicemail", "log", "tmp/nginx", "state", "media"):
        (data / sub).mkdir(parents=True)
    (data / "phonix.db").write_text("")
    chowned: list[str] = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(ownership, "_ids", lambda: (200, 200, 102))
    monkeypatch.setattr(os, "chown", lambda path, *a, **k: chowned.append(os.path.relpath(path, data)))
    ownership.fix_data_ownership()
    assert {"phonix.db", "state", "media", "tmp"} <= set(chowned)
    for untouched in ("ssh", "ssh/dropbear", "spool", "spool/voicemail", "log", "tmp/nginx"):
        assert untouched not in chowned


@pytest.mark.parametrize(("euid", "via_doas"), [(1000, True), (0, False)])
def test_privileged_root_caller_skips_doas(runtime, monkeypatch, euid, via_doas):
    # the console menu runs as root; the doas rule only permits user phonix
    monkeypatch.setenv("PHONIX_PRIVILEGED", "doas")
    config.reset_cache()
    monkeypatch.setattr(privileged.os, "geteuid", lambda: euid)
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(privileged.subprocess, "run", fake_run)
    privileged.run("reboot")
    helper = str(config.get().libexec_dir / "priv")
    assert seen == [(["doas", "-n"] if via_doas else []) + [helper, "reboot"]]


def test_tui_going_down_returns_after_timeout(capsys):
    import signal

    from phonix import tui

    before = signal.getsignal(signal.SIGINT)
    tui._going_down("Rebooting", timeout=0.3)
    out = capsys.readouterr().out
    assert "Rebooting |" in out
    assert "Rebooting did not finish within 0 minutes; back to the menu." in out
    assert signal.getsignal(signal.SIGINT) is before
