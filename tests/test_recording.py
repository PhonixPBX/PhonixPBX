# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import io
import re
import stat
import time
import wave

import pytest
from factories import sample_pbx
from fastapi.testclient import TestClient

from phonix import config
from phonix.core.db import session_scope
from phonix.services import media, recording, users
from phonix.services.common import NotFound, ServiceError


def _wav(rate=8000, seconds=0.2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x10\x00" * int(rate * seconds))
    return buf.getvalue()


@pytest.fixture
def no_sox(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _name: None)


def _asterisk(fake_ami, token, state, audio=None):
    """What Asterisk does in phonix-record: the database state and the recorded file."""
    if state:
        fake_ami.astdb[(recording.ASTDB_FAMILY, token)] = state
    if audio is not None:
        (config.get().media_dir / recording.INCOMING / f"{token}.wav").write_bytes(audio)


def test_record_and_save(session, fake_ami, no_sox):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "Welcome", "admin")
    assert recording.TOKEN_RE.match(token)
    name, fields = fake_ami.actions[-1]
    assert name == "Originate" and fields["Channel"] == "PJSIP/101"
    assert fields["Context"] == "phonix-record" and fields["Exten"] == "s"
    assert fields["Variable"] == f"PHX_REC={token}"
    incoming = config.get().media_dir / recording.INCOMING
    assert stat.S_IMODE(incoming.stat().st_mode) == 0o2770

    assert recording.poll(session, token).state == "ringing"
    _asterisk(fake_ami, token, "recording")
    assert recording.poll(session, token).state == "recording"
    _asterisk(fake_ami, token, "review", _wav(16000))
    status = recording.poll(session, token)
    assert status.state == "review" and not status.done

    _asterisk(fake_ami, token, "saved")
    status = recording.poll(session, token, "admin")
    assert status.state == "saved" and status.done
    assert status.media is not None and status.media.kind == "ivr_prompt" and status.media.name == "Welcome.wav"
    with wave.open(str(media.media_path(status.media))) as wf:
        assert wf.getframerate() == 8000
    # everything about the pending recording is gone, so it is stored only once
    assert not (incoming / f"{token}.wav").exists()
    assert (recording.ASTDB_FAMILY, token) not in fake_ami.astdb
    # a later poll (another tab) shows the same file instead of storing it again
    again = recording.poll(session, token)
    assert again.state == "saved" and again.media is not None and again.media.id == status.media.id
    assert len(media.list_media(session)) == 1


def test_concurrent_poll_while_saving(session, fake_ami, no_sox):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "x")
    _asterisk(fake_ami, token, "saved", _wav())
    pending = config.get().state_dir / "recordings"
    # another request claimed it and is still converting
    (pending / f"{token}.json").rename(pending / f"{token}.claimed")
    status = recording.poll(session, token)
    assert status.state == "saving" and not status.done
    assert not media.list_media(session)


def test_voicemail_greeting(session, fake_ami, no_sox):
    from phonix.core import settings as st

    sample_pbx(session)
    token = recording.start(session, "102", "vm_greeting", "", "admin")
    _asterisk(fake_ami, token, "saved", _wav())
    status = recording.poll(session, token)
    assert status.media is not None and status.media.path == "vm_greeting/greeting.wav"
    assert st.load(session, st.MediaSettings).custom_vm_greeting


@pytest.mark.parametrize("state", ["cancel", "hangup"])
def test_discarded(session, fake_ami, state):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "x")
    _asterisk(fake_ami, token, state, _wav())
    assert recording.poll(session, token).state == "cancelled"
    assert not media.list_media(session)
    assert not (config.get().media_dir / recording.INCOMING / f"{token}.wav").exists()


def test_not_answered_and_expired(session, fake_ami):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "x")
    later = time.time() + recording.ANSWER_TIMEOUT + 1
    assert recording.poll(session, token, now=later).state == "no-answer"

    token = recording.start(session, "101", "ivr_prompt", "x")
    _asterisk(fake_ami, token, "recording")
    assert recording.poll(session, token, now=time.time() + recording.MAX_AGE + 1).state == "expired"


def test_saved_without_file(session, fake_ami):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "x")
    _asterisk(fake_ami, token, "saved")
    status = recording.poll(session, token)
    assert status.state == "failed" and status.error


def test_start_errors(session, fake_ami):
    sample_pbx(session)
    with pytest.raises(ServiceError) as exc:
        recording.start(session, "101", "moh", "x")
    assert "kind" in exc.value.fields
    with pytest.raises(ServiceError) as exc:
        recording.start(session, "101", "ivr_prompt", "  ")
    assert "name" in exc.value.fields
    with pytest.raises(NotFound):
        recording.start(session, "999", "ivr_prompt", "x")
    with pytest.raises(NotFound):
        recording.poll(session, "../../etc/passwd")
    # Asterisk refuses the call: nothing stays pending
    fake_ami.response = {"Response": "Error", "Message": "Extension does not exist."}
    with pytest.raises(ServiceError):
        recording.start(session, "101", "ivr_prompt", "x")
    assert not list((config.get().state_dir / "recordings").glob("*.json"))


def test_cleanup(session, fake_ami):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "x")
    incoming = config.get().media_dir / recording.INCOMING
    stray = incoming / "0123.wav"
    stray.write_bytes(b"x")
    recording.cleanup(now=time.time() + recording.MAX_AGE + 1)
    assert not stray.exists()
    with pytest.raises(NotFound):
        recording.poll(session, token)


def test_dialplan_context(session):
    from phonix.generators import dialplan
    from phonix.generators.base import build_snapshot

    text = dialplan.generate(build_snapshot(session))
    block = text.split("[phonix-record]", 1)[1].split("\n[", 1)[0]
    assert "Record(/data/media/incoming/${PHX_REC}.wav,0,300)" in block
    assert "Set(DB(phonix-rec/${PHX_REC})=saved)" in block
    # only reached by AMI Originate: no other context includes or jumps to it
    assert "include => phonix-record" not in text and text.count("phonix-record") == 1


# --- web --------------------------------------------------------------------------------


@pytest.fixture
def client(initialized):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
        sample_pbx(s)
    with TestClient(create_app()) as c:
        yield c


def _login(c):
    token = re.search(r'name="csrf-token" content="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"username": "admin", "password": "adminadmin", "csrf_token": token, "next": "/"})
    page = c.get("/services/media").text
    return {"X-CSRF-Token": re.search(r'name="csrf-token" content="([^"]+)"', page).group(1), "HX-Request": "true"}


def test_media_page(client, fake_ami, no_sox):
    headers = _login(client)
    page = client.get("/services/media").text
    assert "Record by phone" in page and 'name="extension"' in page
    # tabs: upload (open), record by phone, create from text; the file list below them
    assert 'href="#tab-upload" class="nav-link active"' in page and 'href="#tab-record"' in page
    assert page.index('id="tab-tts"') < page.index('id="media-files"')
    # IVR announcements can be uploaded here too
    r = client.post("/services/media/ivr_prompt", files={"file": ("menu.wav", _wav(), "audio/wav")}, headers=headers)
    assert r.status_code == 200 and "menu.wav" in r.text

    r = client.post(
        "/services/media/record",
        data={"ctx": "media", "kind": "ivr_prompt", "name": "Hello", "extension": "101"},
        headers=headers,
    )
    assert r.status_code == 200 and "The phone is ringing" in r.text
    token = re.search(r"/services/media/record/([0-9a-f]{32})\?ctx=media", r.text).group(1)

    _asterisk(fake_ami, token, "saved", _wav())
    r = client.post(f"/services/media/record/{token}?ctx=media", headers=headers)
    assert "saved as Hello.wav" in r.text and 'hx-trigger="every' not in r.text
    # the file list is refreshed out of band, the pending changes banner too
    assert 'id="media-files" hx-swap-oob="true"' in r.text and "Hello.wav" in r.text
    assert r.headers.get("HX-Trigger") == "phonix:dirty"

    r = client.post("/services/media/record/0123456789abcdef0123456789abcdef?ctx=media", headers=headers)
    assert "Recording not found" in r.text

    r = client.post(
        "/services/media/record", data={"kind": "ivr_prompt", "name": "", "extension": "101"}, headers=headers
    )
    assert "alert-danger" in r.text and "Enter a name" in r.text
    # CSRF protected like every other change
    assert (
        client.post("/services/media/record", data={"kind": "ivr_prompt", "name": "x", "extension": "101"}).status_code
        == 403
    )


def test_ivr_page(client, fake_ami, no_sox):
    headers = _login(client)
    page = client.get("/dialplan/ivr/new").text
    assert 'id="ivr-record"' in page and 'form="ivr-record"' in page

    r = client.post(
        "/services/media/record",
        data={"ctx": "ivr", "kind": "ivr_prompt", "name": "Menu", "extension": "102"},
        headers=headers,
    )
    token = re.search(r"/services/media/record/([0-9a-f]{32})\?ctx=ivr", r.text).group(1)
    _asterisk(fake_ami, token, "saved", _wav())
    r = client.post(f"/services/media/record/{token}?ctx=ivr", headers=headers)
    # the announcement select is replaced, with the new recording chosen
    assert 'id="prompt-select" hx-swap-oob="true"' in r.text
    assert re.search(r'<option value="\d+" selected>Menu.wav</option>', r.text)


def test_link_in_incoming_is_not_followed(session, fake_ami, tmp_path):
    sample_pbx(session)
    token = recording.start(session, "101", "ivr_prompt", "x")
    secret = tmp_path / "secret.wav"
    secret.write_bytes(_wav())
    (config.get().media_dir / recording.INCOMING / f"{token}.wav").symlink_to(secret)
    _asterisk(fake_ami, token, "saved")
    assert recording.poll(session, token).state == "failed"
    assert not media.list_media(session) and secret.exists()
