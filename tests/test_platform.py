# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Container boards (LXC/Incus, OCI): host-managed network; package updates for LXC, none for OCI."""

import subprocess

import pytest
from test_web import client, csrf, login  # noqa: F401 - fixture

from phonix import config
from phonix.services import apply, platform, privileged, update
from phonix.services.common import ServiceError


def _set_board(runtime, name: str) -> None:
    path = runtime.path("/etc/phonix/board")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name + "\n")


@pytest.mark.parametrize(
    ("board", "kind", "container", "updates"),
    [
        ("dev", "dev", False, True),
        ("pc-amd64", "appliance", False, True),
        ("rpi-arm64", "appliance", False, True),
        ("lxc-amd64", "lxc", True, True),
        ("lxc-arm64", "lxc", True, True),
        ("oci-amd64", "oci", True, False),
    ],
)
def test_board_kinds(runtime, board, kind, container, updates):
    if board != "dev":
        _set_board(runtime, board)
    assert platform.board() == board
    assert platform.kind() == kind
    assert platform.is_container() is container
    assert platform.supports_updates() is updates


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


def test_lxc_install_takes_a_backup_first(session, runtime, tmp_path, monkeypatch):
    _set_board(runtime, "lxc-amd64")
    bundle = tmp_path / "x.update"
    bundle.write_bytes(b"verified elsewhere")
    monkeypatch.setattr(
        update, "verify_bundle", lambda path, progress=None, force=False: update.BundleInfo("9.9.9", "lxc-amd64", {})
    )
    privileged.recorder.calls.clear()
    assert update.install(bundle).version == "9.9.9"
    assert ("install-update", str(bundle)) in privileged.recorder.calls
    assert len(list(runtime.backup_dir.glob("phonix-backup-*.tar.zst"))) == 1
    assert update.status()["slot"] == "-"


def test_lxc_install_stops_when_the_backup_fails(session, runtime, tmp_path, monkeypatch):
    from phonix.services import backup

    _set_board(runtime, "lxc-amd64")
    monkeypatch.setattr(
        update, "verify_bundle", lambda path, progress=None, force=False: update.BundleInfo("9.9.9", "lxc-amd64", {})
    )

    def full_disk(target=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backup, "create", full_disk)
    privileged.recorder.calls.clear()
    with pytest.raises(ServiceError, match="Backup before the update failed"):
        update.install(tmp_path / "x.update")
    assert not privileged.recorder.calls


def test_firmware_page_in_container(client, runtime):  # noqa: F811
    login(client)
    page = client.get("/system/firmware").text
    assert "Install an update" in page
    assert "snapshot" not in page
    _set_board(runtime, "lxc-amd64")
    page = client.get("/system/firmware").text
    assert "Install an update" in page
    assert "Take a snapshot of the container first" in page
    for command in ("pct snapshot", "pct rollback", "incus snapshot create", "lxc-snapshot"):
        assert command in page
    assert 'id="snapshot-confirm"' in page
    assert 'data-requires="#snapshot-confirm"' in page
    assert "Updates: replace the container image" not in page
    assert "configured on the container host" in client.get("/system/network").text
    _set_board(runtime, "oci-amd64")
    page = client.get("/system/firmware").text
    assert "Updates: replace the container image" in page
    assert "Install an update" not in page
    assert "snapshot-confirm" not in page


def test_firmware_done_in_lxc(client, runtime):  # noqa: F811
    login(client)
    _set_board(runtime, "lxc-amd64")
    update.write_job("running", "backup")
    r = client.get("/system/firmware/job")
    assert "Backup" in r.text and "Saving a backup" in r.text
    update.write_job("installed", version="9.9.9")
    r = client.get("/system/firmware/job")
    assert "Restart the container" in r.text and "roll back to the snapshot" in r.text
    assert "inactive slot" not in r.text


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


def test_tui_follow_log(tmp_path):
    from phonix import tui

    path = tmp_path / "web.log"
    path.write_text("old line\n")
    follow = tui._follow(path, interval=0.01)
    with path.open("a") as fh:
        fh.write("new line\n")
    assert next(follow) == "new line\n"
    path.write_text("rotated\n")  # shorter than before: starts over
    assert next(follow) == "rotated\n"


def test_logs_in_oci_point_to_the_container_output(client, runtime, tmp_path):  # noqa: F811
    runtime.log_files["asterisk"] = tmp_path / "messages"
    runtime.log_files["asterisk"].write_text("NOTICE secret line\n")
    login(client)
    assert "NOTICE secret line" in client.get("/status/logs").text
    _set_board(runtime, "oci-amd64")
    page = client.get("/status/logs").text
    assert "Logs are in the container output" in page and "docker logs" in page
    assert "NOTICE secret line" not in page and "hx-sse:connect" not in page
    assert client.get("/status/logs/stream?log=asterisk").status_code == 404
