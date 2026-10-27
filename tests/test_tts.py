# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import io
import json
import re
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from factories import sample_pbx
from fastapi.testclient import TestClient

from phonix.core import settings as st
from phonix.core.db import session_scope
from phonix.services import media, tts, users
from phonix.services.common import ServiceError

VOICES = [
    {"id": "thorsten", "language": "de", "label": "Thorsten (neutral)", "gender": "male"},
    {"id": "af_heart", "language": "en", "label": "Heart (US)"},
]


def _wav(rate=8000, seconds=0.3):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x10\x00" * int(rate * seconds))
    return buf.getvalue()


class FakeTts(BaseHTTPRequestHandler):
    """The RestfulTTS API, as far as Phonix uses it."""

    requests: list = []
    token = ""

    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if FakeTts.token and self.headers.get("Authorization") != f"Bearer {FakeTts.token}":
            self._send(401, {"detail": "bad token"})
            return False
        return True

    def do_GET(self):
        FakeTts.requests.append(("GET", self.path, dict(self.headers)))
        if self.path.startswith("/moved/"):
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/steal")
            self.end_headers()
            return
        if not self._authorized():
            return
        if self.path == "/tts/api/v1/voices":
            self._send(200, VOICES)
        else:
            self._send(404, {"detail": "Not Found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeTts.requests.append(("POST", self.path, body))
        if not self._authorized():
            return
        if self.path != "/tts/api/v1/synthesize":
            self._send(404, {"detail": "Not Found"})
        elif body.get("voice") not in (None, "thorsten", "af_heart"):
            self._send(422, {"detail": f"unknown voice '{body['voice']}'"})
        elif body.get("text") == "huge":
            self._send(200, b"\0" * (tts.MAX_AUDIO + 1), "audio/wav")
        elif not body.get("text"):
            self._send(422, {"detail": [{"msg": "String should have at least 1 character"}]})
        else:
            self._send(200, _wav(), "audio/wav")


@pytest.fixture
def server():
    FakeTts.requests = []
    FakeTts.token = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeTts)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/tts"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def configured(session, server):
    st.save(session, st.TtsSettings(url=server + "/", voice="", speed=1.0))
    return server


@pytest.fixture
def no_sox(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _name: None)


def test_settings_validation():
    assert st.TtsSettings(url="https://tts.example.com:8000/").url == "https://tts.example.com:8000"
    for bad in ("ftp://x", "tts.example.com", "http://"):
        with pytest.raises(ValueError):
            st.TtsSettings(url=bad)
    with pytest.raises(ValueError):
        st.TtsSettings(url="https://user:pass@tts.example.com")
    with pytest.raises(ValueError):
        st.TtsSettings(voice="a b")
    with pytest.raises(ValueError):
        st.TtsSettings(speed=3)


def test_create_announcement(session, configured, no_sox):
    st.save(session, st.SystemSettings(prompt_language="de"))
    item = tts.create(session, "ivr_prompt", "Welcome", "Willkommen bei PhonixPBX.", user="admin")
    assert item.kind == "ivr_prompt" and item.path == "ivr_prompt/Welcome.wav"
    method, path, body = FakeTts.requests[-1]
    assert (method, path) == ("POST", "/tts/api/v1/synthesize")
    # no voice: the server picks the voice for the prompt language; always telephone format
    assert body == {"text": "Willkommen bei PhonixPBX.", "speed": 1.0, "format": "wav8", "language": "de"}

    item = tts.create(session, "vm_greeting", "", "Bitte sprechen Sie nach dem Ton.", voice="thorsten", speed=1.2)
    assert item.path == "vm_greeting/greeting.wav" and st.load(session, st.MediaSettings).custom_vm_greeting
    assert FakeTts.requests[-1][2]["voice"] == "thorsten" and FakeTts.requests[-1][2]["speed"] == 1.2


def test_voices_and_token(session, configured):
    FakeTts.token = "s3cret"
    with pytest.raises(ServiceError) as exc:
        tts.voices(session)
    assert "bad token" in str(exc.value)
    tts_settings = st.load(session, st.TtsSettings)
    tts_settings.token = "s3cret"
    st.save(session, tts_settings)
    assert [v["id"] for v in tts.voices(session)] == ["thorsten", "af_heart"]


def test_errors(session, server):
    with pytest.raises(ServiceError) as exc:
        tts.synthesize(session, "Hallo")
    assert "No text-to-speech server" in str(exc.value)
    st.save(session, st.TtsSettings(url=server))
    with pytest.raises(ServiceError) as exc:
        tts.synthesize(session, "Hallo", voice="nope")
    assert "unknown voice 'nope'" in str(exc.value)
    with pytest.raises(ServiceError) as exc:
        tts.synthesize(session, "   ")
    assert "text" in exc.value.fields
    with pytest.raises(ServiceError) as exc:
        tts.synthesize(session, "x" * (tts.MAX_TEXT + 1))
    assert "text" in exc.value.fields
    with pytest.raises(ServiceError) as exc:
        tts.create(session, "ivr_prompt", "", "Hallo")
    assert "name" in exc.value.fields
    with pytest.raises(ServiceError) as exc:
        tts.create(session, "moh", "x", "Hallo")
    assert "kind" in exc.value.fields
    st.save(session, st.TtsSettings(url="http://127.0.0.1:9", timeout=5))
    with pytest.raises(ServiceError) as exc:
        tts.voices(session)
    assert "not reachable" in str(exc.value)


def test_redirect_and_size_limits(session, server):
    st.save(session, st.TtsSettings(url=server.replace("/tts", "/moved"), token="tok"))
    with pytest.raises(ServiceError) as exc:
        tts.voices(session)
    assert "redirect" in str(exc.value)
    # only the one request: the token never went to the redirect target
    assert [r[1] for r in FakeTts.requests] == ["/moved/api/v1/voices"]
    st.save(session, st.TtsSettings(url=server))
    with pytest.raises(ServiceError) as exc:
        tts.synthesize(session, "huge")
    assert "16 MB" in str(exc.value)


def test_changed_url_drops_kept_token(session, server):
    from phonix.services import settings_api

    st.save(session, st.TtsSettings(url=server, token="tok"))
    settings_api.patch_group(session, "tts", {"voice": "thorsten", "token": ""}, "admin")
    assert st.load(session, st.TtsSettings).token == "tok"
    settings_api.patch_group(session, "tts", {"url": "https://elsewhere.example.com", "token": ""}, "admin")
    assert st.load(session, st.TtsSettings).token == ""
    settings_api.patch_group(session, "tts", {"url": server, "token": "new"}, "admin")
    assert st.load(session, st.TtsSettings).token == "new"


# --- web, REST, MCP -----------------------------------------------------------------------


@pytest.fixture
def client(initialized, server):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
        sample_pbx(s)
    with TestClient(create_app()) as c:
        c.tts_url = server  # type: ignore[attr-defined]
        yield c


def _csrf(text):
    return re.search(r'name="csrf-token" content="([^"]+)"', text).group(1)


def _login(c):
    c.post("/login", data={"username": "admin", "password": "adminadmin", "csrf_token": _csrf(c.get("/login").text)})
    return {"X-CSRF-Token": _csrf(c.get("/services/media").text), "HX-Request": "true"}


def test_media_page(client, no_sox):
    headers = _login(client)
    page = client.get("/services/media").text
    assert "Text-to-speech server" in page and 'action="/services/media/tts-settings"' in page
    assert 'hx-post="/services/media/tts"' not in page  # not configured yet

    form = {
        "csrf_token": headers["X-CSRF-Token"],
        "url": "nope",
        "token": "",
        "voice": "",
        "speed": "1",
        "timeout": "60",
    }
    r = client.post("/services/media/tts-settings", data=form, follow_redirects=False)
    assert r.status_code == 422 and "http://" in r.text
    # back on the text-to-speech tab with the server settings open
    assert 'href="#tab-tts" class="nav-link active"' in r.text and '<details class="mt-3" open>' in r.text
    form.update(url=client.tts_url, token="s3cret-tts-token")
    r = client.post("/services/media/tts-settings", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/services/media#tab-tts")
    with session_scope() as s:
        assert st.load(s, st.TtsSettings).token == "s3cret-tts-token"
    FakeTts.token = "s3cret-tts-token"
    # an empty token keeps the stored one; it is never sent to the browser
    form.update(token="", voice="thorsten")
    client.post("/services/media/tts-settings", data=form, follow_redirects=False)
    page = client.get("/services/media").text
    assert 'hx-post="/services/media/tts"' in page and "s3cret-tts-token" not in page
    with session_scope() as s:
        assert st.load(s, st.TtsSettings).token == "s3cret-tts-token"

    r = client.get("/services/media/tts/voices?target=tts-voice&selected=thorsten")
    assert '<option value="thorsten" selected>Thorsten (neutral) (de)</option>' in r.text

    r = client.post("/services/media/tts/player", data={"ctx": "media", "text": "Hallo"}, headers=headers)
    src = re.search(r'src="(/services/media/tts/preview/[0-9a-f]{32})"', r.text).group(1)
    audio = client.get(src)
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert FakeTts.requests[-1][2]["voice"] == "thorsten"  # the default voice
    assert client.get("/services/media/tts/preview/phonix.db").status_code == 404

    data = {"ctx": "media", "kind": "ivr_prompt", "name": "Hello", "text": "Hallo", "tts_voice": "af_heart"}
    r = client.post("/services/media/tts", data=data, headers=headers)
    assert "created as Hello.wav" in r.text and 'id="media-files" hx-swap-oob="true"' in r.text
    assert r.headers.get("HX-Trigger") == "phonix:dirty"
    r = client.post("/services/media/tts", data={**data, "tts_voice": "nope"}, headers=headers)
    assert "alert-danger" in r.text and "unknown voice" in r.text

    # another server address without a new token: the old token is not sent there
    form.update(url="https://other.example.com", token="")
    client.post("/services/media/tts-settings", data=form, follow_redirects=False)
    with session_scope() as s:
        assert st.load(s, st.TtsSettings).token == ""


def test_ivr_editor(client, no_sox):
    headers = _login(client)
    assert "Create from text" not in client.get("/dialplan/ivr/new").text
    with session_scope() as s:
        st.save(s, st.TtsSettings(url=client.tts_url))
    assert "Create announcement" in client.get("/dialplan/ivr/new").text
    # the button sends the whole menu form: the menu name and its recording script
    data = {"ctx": "ivr", "name": "Main", "prompt_text": "Für Vertrieb drücken Sie 1.", "tts_voice": ""}
    r = client.post("/services/media/tts", data=data, headers=headers)
    assert 'id="prompt-select" hx-swap-oob="true"' in r.text
    assert re.search(r'<option value="\d+" selected>Main.wav</option>', r.text)
    assert FakeTts.requests[-1][2]["text"] == "Für Vertrieb drücken Sie 1."


def test_api_and_mcp(client, no_sox):
    from test_mcp import rpc
    from test_web import bearer

    with session_scope() as s:
        st.save(s, st.TtsSettings(url=client.tts_url, token="tok"))
    auth = bearer()
    r = client.get("/api/v1/settings/tts", headers=auth)
    assert r.json()["token"] == "" and r.json()["url"] == client.tts_url
    assert [v["id"] for v in client.get("/api/v1/tts/voices", headers=auth).json()] == ["thorsten", "af_heart"]
    body = {"kind": "ivr_prompt", "name": "api", "text": "Hallo", "voice": "thorsten"}
    r = client.post("/api/v1/media/tts", json=body, headers=auth)
    assert r.status_code == 201 and r.json()["path"] == "ivr_prompt/api.wav"
    assert client.post("/api/v1/media/tts", json=body, headers=bearer(read_only=True)).status_code == 403
    r = client.post("/api/v1/media/tts", json={**body, "voice": "nope"}, headers=auth)
    assert r.status_code == 422 and "unknown voice" in r.json()["detail"]["message"]

    def tool(headers, tool_name, **arguments):
        r = rpc(client, "tools/call", {"name": tool_name, "arguments": arguments}, headers)
        return r.json()["result"]

    voices = tool(bearer(read_only=True), "list_tts_voices")["structuredContent"]["items"]
    assert voices[0]["id"] == "thorsten"
    result = tool(auth, "create_media_from_text", kind="ivr_prompt", name="mcp", text="Hallo")
    assert result["structuredContent"]["path"] == "ivr_prompt/mcp.wav"
    assert tool(bearer(read_only=True), "create_media_from_text", kind="ivr_prompt", text="x")["isError"]
