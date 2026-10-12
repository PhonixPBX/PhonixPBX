from askozia.services import apply, phones, privileged
from askozia.services.common import dirty_areas


def test_apply_writes_and_is_idempotent(session, runtime):
    privileged.recorder.calls.clear()
    phones.create_phone(session, phones.parse_phone({"extension": "101", "callerid": "A"}))
    first = apply.apply(session, user="t")
    assert "/etc/asterisk/pjsip.conf" in first.changed_files
    assert (runtime.root / "etc/asterisk/pjsip.conf").exists()
    # privileged files are staged and installed by the (dry-run) helper
    assert (runtime.staged_dir / "etc/network/interfaces").exists()
    assert ("install-staged", "system:network") in privileged.recorder.calls
    # Asterisk is not running in tests -> restart through the helper
    assert ("asterisk-restart",) in privileged.recorder.calls
    assert dirty_areas(session) == []
    second = apply.apply(session, user="t")
    assert second.changed_files == [] and second.components == []


def test_boot_apply_does_not_reload(session, runtime):
    privileged.recorder.calls.clear()
    result = apply.apply(session, boot=True)
    assert result.changed_files
    assert privileged.recorder.calls == []
    assert (runtime.root / "etc/network/interfaces").exists()


def test_privileged_rejects_bad_input():
    import pytest

    with pytest.raises(privileged.PrivilegedError):
        privileged.run("rm-rf")
    with pytest.raises(privileged.PrivilegedError):
        privileged.run("ban", "1.2.3.4; reboot", "60")
