# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
from phonix.core.db import session_scope
from phonix.services import backup, phones
from phonix.services.common import dirty_areas


def test_backup_restore_roundtrip(initialized):
    with session_scope() as s:
        phones.create_phone(s, phones.parse_phone({"extension": "101", "callerid": "Before"}))
    (initialized.media_dir / "moh").mkdir(parents=True, exist_ok=True)
    (initialized.media_dir / "moh" / "song.wav").write_bytes(b"RIFF")
    path = backup.create()
    with session_scope() as s:
        phones.create_phone(s, phones.parse_phone({"extension": "102", "callerid": "After"}))
    (initialized.media_dir / "moh" / "song.wav").unlink()
    manifest = backup.restore(path)
    assert manifest["format"] == 1
    with session_scope() as s:
        assert [p.extension for p in phones.list_phones(s)] == ["101"]
        assert "accounts" in dirty_areas(s)
    assert (initialized.media_dir / "moh" / "song.wav").exists()
    # the state before restoring was saved as well
    assert len(backup.list_backups()) == 2


def test_restore_rejects_garbage(initialized, tmp_path):
    import pytest

    from phonix.services.common import ServiceError

    bad = tmp_path / "x.tar.zst"
    bad.write_bytes(b"not a backup")
    with pytest.raises(ServiceError):
        backup.restore(bad)
