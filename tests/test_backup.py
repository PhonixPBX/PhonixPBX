# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import io
import json
import re
import stat
import tarfile

import pytest
import zstandard
from fastapi.testclient import TestClient

from phonix.core.db import session_scope
from phonix.core.models import MediaFile
from phonix.services import backup, configdoc, phones, privileged, users
from phonix.services.common import ServiceError, dirty_areas


@pytest.fixture
def pbx(initialized):
    """A configured system with media, a certificate, an ACME account and an astdb."""
    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
        phones.create_phone(s, phones.parse_phone({"extension": "101", "callerid": "Before"}))
        (initialized.media_dir / "moh").mkdir(parents=True)
        (initialized.media_dir / "moh" / "song.wav").write_bytes(b"RIFF-song")
        s.add(MediaFile(kind="moh", name="song.mp3", path="moh/song.wav", size=9))
    tls = initialized.data_dir / "tls"
    tls.mkdir()
    (tls / "server.crt").write_text("CERT-1")
    (tls / "server.key").write_text("KEY-1")
    acme = initialized.data_dir / "acme"
    acme.mkdir()
    (acme / "account.key").write_text("ACCOUNT-1")
    (acme / "lock").write_text("")
    astdb = initialized.data_dir / "asterisk"
    astdb.mkdir()
    (astdb / "astdb.sqlite3").write_text("ASTDB")
    return initialized


def _members(path):
    with (
        path.open("rb") as raw,
        zstandard.ZstdDecompressor().stream_reader(raw) as zfh,
        tarfile.open(fileobj=zfh, mode="r|") as tar,
    ):
        return {m.name: (tar.extractfile(m).read() if m.isfile() else None) for m in tar}


def _archive(path, files):
    with (
        path.open("wb") as raw,
        zstandard.ZstdCompressor().stream_writer(raw) as zfh,
        tarfile.open(fileobj=zfh, mode="w|") as tar,
    ):
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_backup_contents(pbx):
    path = backup.create()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    members = _members(path)
    manifest = json.loads(members["manifest.json"])
    assert manifest["format"] == 2 and manifest["config_version"] == configdoc.CONFIG_VERSION
    doc = json.loads(members["config.json"])
    assert [p["extension"] for p in doc["phones"]] == ["101"]
    assert members["media/moh/song.wav"] == b"RIFF-song"
    assert members["tls/server.key"] == b"KEY-1"
    assert members["acme/account.key"] == b"ACCOUNT-1"
    assert "acme/lock" not in members
    assert not any(name.startswith("asterisk") or name == "phonix.db" for name in members)


def test_backup_restore_roundtrip(pbx):
    path = backup.create()
    with session_scope() as s:
        phones.create_phone(s, phones.parse_phone({"extension": "102", "callerid": "After"}))
        users.create_user(s, "later", "laterlater")
    (pbx.media_dir / "moh" / "song.wav").unlink()
    (pbx.media_dir / "moh" / "other.wav").write_bytes(b"other")
    (pbx.data_dir / "tls" / "server.crt").write_text("CERT-2")
    (pbx.data_dir / "asterisk" / "astdb.sqlite3").write_text("ASTDB-2")
    privileged.recorder.calls.clear()

    result = backup.restore(path, user="admin")

    assert result.counts["phones"] == 1 and result.apply_errors == []
    assert result.files == ["media", "tls", "acme"]
    with session_scope() as s:
        assert [p.extension for p in phones.list_phones(s)] == ["101"]
        assert [u.username for u in users.list_users(s)] == ["admin"]
        assert s.query(MediaFile).one().path == "moh/song.wav"
        # applied right away
        assert dirty_areas(s) == []
    assert (pbx.media_dir / "moh" / "song.wav").read_bytes() == b"RIFF-song"
    assert not (pbx.media_dir / "moh" / "other.wav").exists()
    assert (pbx.data_dir / "tls" / "server.crt").read_text() == "CERT-1"
    # runtime state is left alone
    assert (pbx.data_dir / "asterisk" / "astdb.sqlite3").read_text() == "ASTDB-2"
    assert (pbx.data_dir / "acme" / "lock").exists() is False
    assert ("nginx-reload",) in privileged.recorder.calls
    # modes as set up by phonix-firstboot, no leftovers
    assert stat.S_IMODE((pbx.media_dir).stat().st_mode) == 0o2750
    assert stat.S_IMODE((pbx.media_dir / "moh" / "song.wav").stat().st_mode) == 0o640
    assert stat.S_IMODE((pbx.data_dir / "acme").stat().st_mode) == 0o700
    assert not [p for p in pbx.data_dir.iterdir() if p.name.startswith((".", "tmp"))]
    # the state before restoring was saved as well
    assert len(backup.list_backups()) == 2


def test_inspect_changes_nothing(pbx):
    path = backup.create()
    with session_scope() as s:
        phones.create_phone(s, phones.parse_phone({"extension": "102", "callerid": "After"}))
    preview = backup.inspect(path)
    assert preview.counts["phones"] == 1 and preview.manifest["format"] == 2
    with session_scope() as s:
        assert len(phones.list_phones(s)) == 2
    assert len(backup.list_backups()) == 1


def test_failed_restore_changes_nothing(pbx, monkeypatch):
    path = backup.create()
    with session_scope() as s:
        phones.create_phone(s, phones.parse_phone({"extension": "102", "callerid": "After"}))
    (pbx.data_dir / "tls" / "server.crt").write_text("CERT-2")

    real = configdoc.import_document
    calls = []

    def flaky(session, doc, media_root, user=""):
        calls.append(1)
        if len(calls) > 1:  # the dry run passes, the real import fails
            raise ServiceError("boom")
        return real(session, doc, media_root, user)

    monkeypatch.setattr(configdoc, "import_document", flaky)
    with pytest.raises(ServiceError, match="boom"):
        backup.restore(path)
    with session_scope() as s:
        assert len(phones.list_phones(s)) == 2
    assert (pbx.data_dir / "tls" / "server.crt").read_text() == "CERT-2"


def test_swap_failure_rolls_back(pbx, tmp_path, monkeypatch):
    staged = pbx.data_dir / "staged"
    for name in ("media", "tls"):
        (staged / name).mkdir(parents=True)
        (staged / name / "new").write_text("new")
    real_rename = type(staged).rename

    def rename(self, target):
        if self == staged / "tls":
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(type(staged), "rename", rename)
    with pytest.raises(OSError):
        backup._swap(staged, ["media", "tls"])
    assert (pbx.media_dir / "moh" / "song.wav").exists()
    assert not (pbx.media_dir / "new").exists()
    assert (pbx.data_dir / "tls" / "server.key").read_text() == "KEY-1"


def test_restore_rejects_old_format(initialized, tmp_path):
    old = tmp_path / "old.tar.zst"
    _archive(old, {"manifest.json": json.dumps({"format": 1}).encode(), "phonix.db": b"SQLite"})
    with pytest.raises(ServiceError, match="older PhonixPBX release"):
        backup.restore(old)


def test_restore_rejects_newer_config(pbx, tmp_path):
    members = _members(backup.create())
    doc = json.loads(members["config.json"])
    doc.update(version=configdoc.CONFIG_VERSION + 1, phonix_version="9.9")
    newer = tmp_path / "newer.tar.zst"
    _archive(newer, {**{k: v for k, v in members.items() if v is not None}, "config.json": json.dumps(doc).encode()})
    with pytest.raises(ServiceError, match=r"9\.9"):
        backup.inspect(newer)


def test_restore_rejects_damaged_media(pbx, tmp_path):
    members = _members(backup.create())
    members["media/moh/song.wav"] = b"tampered"
    damaged = tmp_path / "damaged.tar.zst"
    _archive(damaged, {k: v for k, v in members.items() if v is not None})
    with pytest.raises(ServiceError, match=r"moh/song\.wav"):
        backup.inspect(damaged)


def test_restore_rejects_garbage(initialized, tmp_path):
    bad = tmp_path / "x.tar.zst"
    bad.write_bytes(b"not a backup")
    with pytest.raises(ServiceError):
        backup.restore(bad)


# --- web ------------------------------------------------------------------------------


@pytest.fixture
def client(pbx):
    from phonix.web.app import create_app

    with TestClient(create_app()) as c:
        token = re.search(r'name="csrf-token" content="([^"]+)"', c.get("/login").text).group(1)
        c.post("/login", data={"username": "admin", "password": "adminadmin", "csrf_token": token, "next": "/"})
        c.headers["X-CSRF-Token"] = re.search(
            r'name="csrf-token" content="([^"]+)"', c.get("/system/backup").text
        ).group(1)
        yield c


def test_web_upload_preview_restore(client, pbx):
    path = backup.create()
    with session_scope() as s:
        phones.create_phone(s, phones.parse_phone({"extension": "102", "callerid": "After"}))

    r = client.post("/system/backup/upload", files={"file": ("b.tar.zst", path.read_bytes())})
    assert r.status_code == 200 and "Restore this backup now?" in r.text
    token = re.search(r'name="token" value="([0-9a-f]+)"', r.text).group(1)
    with session_scope() as s:
        assert len(phones.list_phones(s)) == 2  # only a preview

    r = client.post("/system/backup/restore", data={"token": token}, headers={"HX-Request": "true"})
    assert r.status_code == 204 and r.headers["HX-Redirect"] == "/"
    with session_scope() as s:
        assert len(phones.list_phones(s)) == 1
    assert not list((pbx.state_dir / "restore-uploads").iterdir())


def test_web_preview_stored_backup(client):
    path = backup.create()
    r = client.post(f"/system/backup/preview/{path.name}")
    assert r.status_code == 200 and f'name="name" value="{path.name}"' in r.text
    assert client.post("/system/backup/preview/../../etc").status_code == 404


def test_web_upload_rejects_garbage(client):
    r = client.post("/system/backup/upload", files={"file": ("b.tar.zst", b"garbage")})
    assert r.status_code == 422


def test_web_restore_requires_csrf(client):
    path = backup.create()
    del client.headers["X-CSRF-Token"]
    r = client.post("/system/backup/restore", data={"name": path.name})
    assert r.status_code == 403


def test_session_of_replaced_user_ends(client, pbx):
    # after the restore, the id of the logged in admin belongs to another user
    with session_scope() as s:
        doc = configdoc.export(s)
    doc["users"][0]["username"] = "someone"
    with session_scope() as s:
        configdoc.import_document(s, configdoc.parse_document(doc), pbx.media_dir)
    r = client.get("/system/backup", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
