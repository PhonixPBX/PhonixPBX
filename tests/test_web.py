# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import base64
import re

import jinja2
import pytest
from factories import sample_pbx
from fastapi.testclient import TestClient

from phonix.core.db import session_scope
from phonix.services import users


@pytest.fixture
def client(initialized):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
        sample_pbx(s)
    with TestClient(create_app()) as c:
        yield c


def csrf(c, url="/login"):
    return re.search(r'name="csrf-token" content="([^"]+)"', c.get(url).text).group(1)


def bearer(read_only=False, expires_in_days=None, name="test", allow_calls=False):
    """Authorization header with a new API token of ``admin``."""
    from phonix.services import tokens

    with session_scope() as s:
        _, plain = tokens.create(
            s,
            users.get_by_name(s, "admin"),
            name,
            read_only=read_only,
            allow_calls=allow_calls,
            expires_in_days=expires_in_days,
        )
    return {"Authorization": f"Bearer {plain}"}


def login(c, password="adminadmin"):
    return c.post(
        "/login",
        data={"username": "admin", "password": password, "csrf_token": csrf(c), "next": "/"},
        follow_redirects=False,
    )


def test_requires_login(client):
    r = client.get("/accounts/phones", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    r = client.get("/accounts/phones", headers={"HX-Request": "true"}, follow_redirects=False)
    assert r.headers.get("HX-Redirect", "").startswith("/login")


def test_login_and_security_headers(client):
    assert login(client, "wrong").status_code == 401
    r = login(client)
    assert r.status_code == 303
    r = client.get("/")
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_login_rate_limit(client):
    for _ in range(5):
        login(client, "wrong")
    assert login(client).status_code == 429


def test_csrf_enforced(client):
    login(client)
    r = client.post("/accounts/phones/new", data={"extension": "150", "callerid": "X"})
    assert r.status_code == 403


def test_create_phone_via_form(client):
    login(client)
    token = csrf(client, "/accounts/phones/new")
    r = client.post(
        "/accounts/phones/new",
        data={
            "csrf_token": token,
            "tech": "pjsip",
            "extension": "150",
            "callerid": "Form Phone",
            "codecs__present": "1",
            "codecs": ["alaw", "g722"],
            "vm_enabled__present": "1",
            "vm_enabled": "true",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get("/accounts/phones").text
    assert "Form Phone" in page and "Phone 150 created" in page


def test_voicemail_texts_per_language(client):
    from phonix.core import settings as st

    login(client)
    page = client.get("/services/voicemail?lang=de").text
    assert "Neue Sprachnachricht von ${VM_CALLERID}" in page and 'value="de"' in page
    # preview with sample values
    assert "Verpasster Anruf von &#34;Bob&#34; &lt;0441234567&gt;" in page

    def post(url, **data):
        token = csrf(client, "/services/voicemail?lang=de")
        return client.post(url, data={"csrf_token": token, "lang": "de", **data}, follow_redirects=False)

    r = post(
        "/services/voicemail/texts", vm_subject="Mailbox ${VM_MAILBOX}", vm_body="", missed_subject="", missed_body=""
    )
    assert r.status_code == 303 and r.headers["location"] == "/services/voicemail?lang=de#texts"
    with session_scope() as s:
        assert st.load(s, st.VoicemailSettings).templates["de"].vm_subject == "Mailbox ${VM_MAILBOX}"
    page = client.get("/services/voicemail?lang=de").text
    assert 'value="Mailbox ${VM_MAILBOX}"' in page and "Mailbox 101" in page
    assert post("/services/voicemail/texts", vm_subject="a\x01b").status_code == 422
    assert post("/services/voicemail/texts/reset").status_code == 303
    with session_scope() as s:
        assert st.load(s, st.VoicemailSettings).templates == {}
    # the other voicemail settings form leaves the texts alone
    post("/services/voicemail/texts", vm_subject="Mailbox ${VM_MAILBOX}")
    token = csrf(client, "/services/voicemail")
    client.post("/services/voicemail", data={"csrf_token": token, "from_name": "VM", "max_message_seconds": "120"})
    with session_scope() as s:
        assert "de" in st.load(s, st.VoicemailSettings).templates


def test_phone_notify_language(client):
    from sqlalchemy import select

    from phonix.core.models import Phone

    login(client)
    assert "Same as phone language" in client.get("/accounts/phones/new").text
    token = csrf(client, "/accounts/phones/new")
    data = {"csrf_token": token, "tech": "pjsip", "extension": "151", "callerid": "Lang", "notify_language": "fr"}
    assert client.post("/accounts/phones/new", data=data, follow_redirects=False).status_code == 303
    with session_scope() as s:
        assert s.scalar(select(Phone).where(Phone.extension == "151")).notify_language == "fr"


def test_form_validation_errors(client):
    login(client)
    token = csrf(client, "/accounts/phones/new")
    r = client.post(
        "/accounts/phones/new", data={"csrf_token": token, "tech": "pjsip", "extension": "101", "callerid": "Dup"}
    )
    assert r.status_code == 422 and "already used" in r.text


def test_htmx_delete_and_dirty_trigger(client):
    login(client)
    token = csrf(client, "/accounts/phones")
    r = client.delete("/accounts/phones/2", headers={"HX-Request": "true", "X-CSRF-Token": token})
    assert r.status_code == 200 and r.headers["HX-Trigger"] == "phonix:dirty"


def test_settings_page_roundtrip(client):
    login(client)
    token = csrf(client, "/system/general")
    r = client.post(
        "/system/general",
        data={
            "csrf_token": token,
            "hostname": "pbx1",
            "domain": "example.org",
            "timezone": "Europe/Berlin",
            "tonezone": "de",
            "prompt_language": "de",
            "ui_language": "en",
            "ntp_servers": "pool.ntp.org\nntp.example.org",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get("/system/general").text
    assert 'value="pbx1"' in page and "ntp.example.org" in page


def test_ssh_root_password(client):
    from phonix.core import settings as st

    login(client)
    form = {
        "hostname": "pbx1",
        "domain": "example.org",
        "timezone": "UTC",
        "tonezone": "us",
        "prompt_language": "en",
        "ui_language": "en",
        "ntp_servers": "pool.ntp.org",
        "ssh_enabled": "true",
    }

    def post(**extra):
        token = csrf(client, "/system/general")
        return client.post("/system/general", data={"csrf_token": token, **form, **extra}, follow_redirects=False)

    def stored():
        with session_scope() as s:
            return st.load(s, st.SystemSettings).ssh_password_hash

    assert post(ssh_password="short").status_code == 422 and stored() == ""
    assert post(ssh_password="geheim123").status_code == 303
    pw = stored()
    assert pw.startswith("$6$") and "geheim123" not in pw
    assert "A password is set" in client.get("/system/general").text
    # empty field keeps it, the API never shows it
    assert post(ssh_password="").status_code == 303 and stored() == pw
    auth = bearer()
    assert client.get("/api/v1/settings/system", headers=auth).json()["ssh_password_hash"] == ""
    assert client.patch("/api/v1/settings/system", headers=auth, json={"ssh_password_hash": ""}).status_code == 200
    assert stored() == pw
    assert post(ssh_password_clear="true").status_code == 303 and stored() == ""


def test_mdns_checkbox(client):
    from phonix.core import settings as st

    login(client)
    page = client.get("/system/general").text
    assert 'name="mdns_enabled"' in page and "https://phonix.local/" in page
    form = {
        "hostname": "phonix",
        "domain": "local",
        "timezone": "UTC",
        "tonezone": "us",
        "prompt_language": "en",
        "ntp_servers": "pool.ntp.org",
        "mdns_enabled__present": "1",
    }
    r = client.post("/system/general", data={"csrf_token": csrf(client, "/system/general"), **form})
    assert r.status_code == 200
    with session_scope() as s:
        assert st.load(s, st.SystemSettings).mdns_enabled is False


def test_apply_via_htmx(client):
    login(client)
    token = csrf(client)
    r = client.post("/apply", headers={"HX-Request": "true", "X-CSRF-Token": token})
    assert r.status_code == 200 and "Configuration applied" in r.text


def test_api_token_auth(client):
    basic = {"Authorization": "Basic " + base64.b64encode(b"admin:adminadmin").decode()}
    assert client.get("/api/v1/phones").status_code == 401
    r = client.get("/api/v1/phones", headers=basic)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    auth = bearer()
    phones = client.get("/api/v1/phones", headers=auth).json()
    assert any(p["extension"] == "101" for p in phones) and "secret" not in phones[0]
    r = client.post("/api/v1/phones", headers=auth, json={"extension": "160", "callerid": "API"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/phones", headers=auth, json={"extension": "160", "callerid": "API"})
    assert r.status_code == 422
    r = client.patch("/api/v1/settings/rtp", headers=auth, json={"port_start": 12000})
    assert r.json()["port_start"] == 12000
    assert "telephony" in client.get("/api/v1/pending", headers=auth).json()["pending"]
    assert client.get("/api/v1/settings/email", headers=auth).json()["password"] == ""


def test_must_change_password(initialized):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "initialpw1", must_change=True)
    with TestClient(create_app()) as c:
        r = c.post(
            "/login",
            data={"username": "admin", "password": "initialpw1", "csrf_token": csrf(c)},
            follow_redirects=False,
        )
        assert r.headers["location"] == "/password"
        assert c.get("/", follow_redirects=False).headers["location"] == "/password"
        token = csrf(c, "/password")
        r = c.post(
            "/password",
            data={"csrf_token": token, "current": "initialpw1", "password": "newpassword1", "confirm": "newpassword1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert c.get("/").status_code == 200


def test_password_change_ends_other_sessions(client):
    from phonix.web.app import create_app

    login(client)
    with TestClient(client.app) as other:
        login(other)
        token = csrf(client, "/password")
        r = client.post(
            "/password",
            data={"csrf_token": token, "current": "adminadmin", "password": "newpassword1", "confirm": "newpassword1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert client.get("/", follow_redirects=False).status_code == 200
        assert other.get("/", follow_redirects=False).headers["location"].startswith("/login")
    # a reset on the console (or a restored backup with another password) ends this one too
    with session_scope() as s:
        users.set_password(s, "admin", "consolepw1", actor="console")
    assert client.get("/", follow_redirects=False).headers["location"].startswith("/login")
    with TestClient(create_app()) as fresh:
        assert login(fresh, "consolepw1").status_code == 303


def test_api_token_states(client):
    from phonix.core.models import ApiToken, utcnow
    from phonix.services import tokens

    ro = bearer(read_only=True, name="ro")
    assert client.get("/api/v1/phones", headers=ro).status_code == 200
    r = client.patch("/api/v1/settings/rtp", headers=ro, json={"port_start": 12000})
    assert r.status_code == 403 and r.json()["detail"] == "token is read-only"
    with session_scope() as s:
        token = s.query(ApiToken).filter_by(name="ro").one()
        assert token.last_used_at is not None
        tokens.set_enabled(s, token.id, False)
    assert client.get("/api/v1/phones", headers=ro).status_code == 401
    with session_scope() as s:
        token = s.query(ApiToken).filter_by(name="ro").one()
        tokens.set_enabled(s, token.id, True)
        assert tokens.status(token) == "active"
    assert client.get("/api/v1/phones", headers=ro).status_code == 200
    # expired
    with session_scope() as s:
        token = s.query(ApiToken).filter_by(name="ro").one()
        token.expires_at = utcnow()
    assert client.get("/api/v1/phones", headers=ro).status_code == 401
    # deleted
    rw = bearer(name="rw")
    with session_scope() as s:
        tokens.delete(s, s.query(ApiToken).filter_by(name="rw").one().id)
    assert client.get("/api/v1/phones", headers=rw).status_code == 401
    # repeated bad tokens are rate limited
    for _ in range(5):
        client.get("/api/v1/phones", headers={"Authorization": "Bearer phx_wrong"})
    assert client.get("/api/v1/phones", headers=bearer(name="late")).status_code == 429


def test_token_ui(client):
    from phonix.core.models import ApiToken

    login(client)
    data = {
        "csrf_token": csrf(client, "/advanced/tokens"),
        "name": "monitoring",
        "access": "read",
        "expires_in_days": "30",
    }
    r = client.post("/advanced/tokens", data=data)
    assert r.status_code == 200
    plain = re.search(r'id="new-token"[^>]*value="(phx_[^"]+)"', r.text).group(1)
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {plain}"}).status_code == 200
    page = client.get("/advanced/tokens").text
    assert plain not in page and plain[:12] in page and "read-only" in page and "active" in page
    for bad in ("0", "3654", "abc"):
        data["expires_in_days"] = bad
        assert client.post("/advanced/tokens", data=data).status_code == 422
    r = client.post(
        "/advanced/tokens",
        data={**data, "name": "deploy", "access": "write", "expires_in_days": ""},
    )
    assert r.status_code == 200 and "unlimited" in r.text and "read-write" in r.text
    r = client.post("/advanced/tokens", data={**data, "name": "dialer", "expires_in_days": "", "allow_calls": "true"})
    assert r.status_code == 200 and "calls" in r.text
    with session_scope() as s:
        assert s.query(ApiToken).filter_by(name="dialer").one().allow_calls is True
        token = s.query(ApiToken).filter_by(name="monitoring").one()
        assert token.allow_calls is False
        token_id = token.id
        assert (token.expires_at - token.created_at).days == 30
    headers = {"X-CSRF-Token": csrf(client, "/advanced/tokens"), "HX-Request": "true"}
    r = client.post(f"/advanced/tokens/{token_id}/toggle", headers=headers)
    assert r.status_code == 200 and "disabled" in r.text
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {plain}"}).status_code == 401
    assert client.delete(f"/advanced/tokens/{token_id}", headers=headers).status_code == 200
    with session_scope() as s:
        assert s.query(ApiToken).filter_by(name="monitoring").count() == 0


def test_deleting_admin_removes_tokens(client):
    from phonix.core.models import ApiToken

    with session_scope() as s:
        other = users.create_user(s, "ops", "opsopsops")
        from phonix.services import tokens

        tokens.create(s, other, "ops token")
    with session_scope() as s:
        users.delete_user(s, "ops")
    with session_scope() as s:
        assert s.query(ApiToken).count() == 0


class _InlinePopen:
    """Runs ``phonix update install`` in the test process instead of detaching it."""

    calls: list[list[str]] = []

    def __init__(self, cmd, **kwargs):
        import os

        from phonix import cli

        type(self).calls.append(cmd)
        self.pid = os.getpid()
        self.returncode = cli.main(cmd[cmd.index("update") :])

    def wait(self):
        return self.returncode


@pytest.fixture
def inline_install(monkeypatch):
    from phonix.services import update

    _InlinePopen.calls = []
    monkeypatch.setattr(update.subprocess, "Popen", _InlinePopen)
    return _InlinePopen


def test_firmware_upload_runs_install_job(client, monkeypatch, runtime, inline_install):
    from phonix.services import update
    from phonix.services.common import ServiceError

    seen = []

    def fake_install(path, step=None):
        seen.append((path, path.read_bytes()))
        step("verify", 50)
        if len(seen) == 1:
            raise ServiceError("Update signature is invalid")
        step("write", None)
        return update.BundleInfo("9.9.9", "pc-amd64", {})

    monkeypatch.setattr(update, "install", fake_install)
    login(client)
    headers = {"HX-Request": "true", "X-CSRF-Token": csrf(client, "/system/firmware")}
    files = {"file": ("x.update", b"bundle", "application/octet-stream")}
    r = client.post("/system/firmware/upload", headers=headers, files=files)
    # the upload returns the job, which failed
    assert r.status_code == 200 and "Update rejected: Update signature is invalid" in r.text
    assert "Update rejected" in client.get("/system/firmware/job").text
    r = client.post("/system/firmware/upload", headers=headers, files=files)
    assert r.status_code == 200
    assert "9.9.9" in r.text and "Reboot into the new firmware" in r.text
    assert 'name="next" value="/system/firmware"' in r.text
    assert [content for _, content in seen] == [b"bundle", b"bundle"]
    assert seen[0][0] != seen[1][0]  # unique per upload
    assert all("--remove" in cmd and cmd[cmd.index("--user") + 1] == "admin" for cmd in inline_install.calls)
    assert not list(runtime.data_dir.glob("update*"))
    # the pending reboot stays on the page, the upload field too
    page = client.get("/system/firmware").text
    assert "Reboot into the new firmware" in page and "data-dropzone" in page
    from phonix.core.models import AuditLog

    with session_scope() as s:
        assert [a.summary for a in s.query(AuditLog).filter_by(action="firmware")] == ["installed 9.9.9"]


def test_firmware_job_running(client, runtime, inline_install):
    from phonix.services import update

    login(client)
    update.write_job("running", "verify", progress=40)
    page = client.get("/system/firmware").text
    assert 'hx-get="/system/firmware/job"' in page and 'aria-valuenow="40"' in page
    assert "data-dropzone" not in page  # no second upload while one runs
    update.write_job("running", "write")
    r = client.get("/system/firmware/job")
    assert "inactive system slot" in r.text and "progress-bar-indeterminate" in r.text
    headers = {"HX-Request": "true", "X-CSRF-Token": csrf(client, "/system/firmware")}
    files = {"file": ("x.update", b"bundle", "application/octet-stream")}
    r = client.post("/system/firmware/upload", headers=headers, files=files)
    assert r.status_code == 422 and "already being installed" in r.text
    assert not inline_install.calls
    assert not list(runtime.data_dir.glob("update*"))


def test_firmware_job_interrupted(client, runtime, monkeypatch):
    from phonix.services import update

    login(client)
    update.write_job("running", "write", pid=2**22 + 12345)  # no such process
    job = update.read_job()
    assert job["state"] == "error" and job["interrupted"]
    r = client.get("/system/firmware/job")
    assert "interrupted" in r.text and "hx-get" not in r.text


def test_firmware_reboot_result(client, runtime, monkeypatch):
    from phonix import __version__
    from phonix.services import update

    login(client)
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-1")
    update.write_job("installed", version="9.9.9")
    # not rebooted yet: still pending
    assert update.reboot_result() is None
    assert "Reboot into the new firmware" in client.get("/system/firmware").text
    # rebooted, but the old version runs: the trial boot was rolled back
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-2")
    page = client.get("/system/firmware").text
    assert "Version 9.9.9 did not start" in page and "Reboot into the new firmware" not in page
    assert update.read_job()["state"] == "none"
    # rebooted into the new version
    update.write_job("installed", version=__version__)
    page = client.get("/system/firmware").text
    assert "The update was successful" in page
    assert "The update was successful" not in client.get("/system/firmware").text  # reported once


def test_reboot_banner_while_update_pending(client, runtime, monkeypatch):
    from phonix import __version__
    from phonix.services import update

    login(client)
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-1")
    assert "Reboot required" not in client.get("/").text
    update.write_job("installed", version="9.9.9")
    assert update.pending_reboot() == "9.9.9"
    page = client.get("/accounts/phones").text
    assert "Reboot required" in page and "9.9.9" in page
    assert 'action="/system/reboot"' in page and 'name="next" value="/system/firmware"' in page
    # the firmware page has its own reboot button
    page = client.get("/system/firmware").text
    assert "Reboot required" not in page and "Reboot into the new firmware" in page
    # rebooted, but the trial boot was rolled back: nothing pending any more
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-2")
    assert update.pending_reboot() is None
    assert "Reboot required" not in client.get("/accounts/phones").text
    # running the installed version
    update.write_job("installed", version=__version__)
    assert update.pending_reboot() is None


def test_reboot_banner_in_lxc(client, runtime, monkeypatch):
    from phonix.services import update

    login(client)
    monkeypatch.setattr(update.platform, "is_container", lambda name=None: True)
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-1")
    update.write_job("installed", version="9.9.9")
    # a container shares the host's boot id: a restart does not change it
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-2")
    assert update.pending_reboot() == "9.9.9"


def test_templates_are_read_at_startup(tmp_path, monkeypatch):
    """An in-place update (LXC) replaces the templates before the restart; the
    running version keeps rendering its own."""
    from phonix.web import templating

    tpl = tmp_path / "pages" / "x.html"
    tpl.parent.mkdir()
    tpl.write_text("old")
    loader = templating._loader(tmp_path, dev=False)
    tpl.write_text("new")
    (tmp_path / "pages" / "added.html").write_text("added")
    env = jinja2.Environment(loader=loader, autoescape=True)
    assert env.get_template("pages/x.html").render() == "old"
    with pytest.raises(jinja2.TemplateNotFound):
        env.get_template("pages/added.html")
    # dev: edits show up without a restart
    env = jinja2.Environment(loader=templating._loader(tmp_path, dev=True), autoescape=True)
    assert env.get_template("pages/x.html").render() == "new"


def test_reboot_next_is_whitelisted(client, runtime):
    login(client)
    token = csrf(client, "/system/reboot")
    r = client.post("/system/reboot", data={"csrf_token": token, "action": "reboot", "next": "/system/firmware"})
    assert 'data-next="/system/firmware"' in r.text
    r = client.post("/system/reboot", data={"csrf_token": token, "action": "reboot", "next": "https://evil.example/"})
    assert 'data-next="/"' in r.text and "evil" not in r.text


def test_cli_update_install(runtime, monkeypatch, tmp_path, capsys):
    from phonix import cli
    from phonix.services import update

    bundle = tmp_path / "x.update"
    bundle.write_bytes(b"bundle")
    monkeypatch.setattr(update, "install", lambda path, step=None: update.BundleInfo("9.9.9", "pc-amd64", {}))
    cli.main(["migrate"])
    assert cli.main(["update", "install", str(bundle)]) == 0
    assert "9.9.9 installed" in capsys.readouterr().out
    assert bundle.exists()  # only removed with --remove
    assert update.read_job()["state"] == "installed"
    assert cli.main(["update", "install"]) == 2


def test_firmware_check_github_release(client, monkeypatch):
    import io
    import json

    from phonix.core import settings as st
    from phonix.services import update as update_svc
    from phonix.web.routes.ui import system as system_routes

    requests = []

    def fake_urlopen(req, timeout):
        requests.append(req)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(update_svc.urllib.request, "urlopen", fake_urlopen)
    login(client)
    token = csrf(client, "/system/firmware")
    headers = {"HX-Request": "true", "X-CSRF-Token": token}

    payload = {"tag_name": "v9.9.9", "html_url": "https://github.com/PhonixPBX/PhonixPBX/releases/tag/v9.9.9"}
    r = client.post("/system/firmware/check", headers=headers)
    assert "Version 9.9.9 is available" in r.text
    assert "releases/tag/v9.9.9" in r.text
    assert requests[0].full_url == st.DEFAULT_UPDATE_CHECK_URL
    assert requests[0].get_header("User-agent").startswith("phonix/")
    assert 'href="https://github.com/PhonixPBX/PhonixPBX/releases/tag/v9.9.9"' in r.text
    assert "Download phonix-" not in r.text  # no bundle for this board in the release
    # the dashboard shows the result of the last check
    assert "PhonixPBX 9.9.9 is available" in client.get("/").text

    # the release lists the bundle of this board: a direct download link
    base = "https://github.com/PhonixPBX/PhonixPBX/releases/download/v9.9.9"
    payload["assets"] = [
        {"name": "phonix-9.9.9-rpi.update", "browser_download_url": f"{base}/phonix-9.9.9-rpi.update"},
        {"name": "phonix-9.9.9-dev.update", "browser_download_url": f"{base}/phonix-9.9.9-dev.update"},
        {"name": "phonix-9.9.9-dev.img.zst", "browser_download_url": f"{base}/phonix-9.9.9-dev.img.zst"},
    ]
    r = client.post("/system/firmware/check", headers=headers)
    assert f'href="{base}/phonix-9.9.9-dev.update"' in r.text and "Download phonix-9.9.9-dev.update" in r.text
    assert "rpi.update" not in r.text and "img.zst" not in r.text
    # System > Firmware shows the last result without a new check
    page = client.get("/system/firmware").text
    assert f'href="{base}/phonix-9.9.9-dev.update"' in page
    # only https links
    payload["assets"] = [{"name": "phonix-9.9.9-dev.update", "browser_download_url": "javascript:alert(1)"}]
    payload["html_url"] = "javascript:alert(2)"
    r = client.post("/system/firmware/check", headers=headers)
    assert "javascript:" not in r.text and "Version 9.9.9 is available" in r.text
    payload = {"tag_name": "v9.9.9", "html_url": "https://github.com/PhonixPBX/PhonixPBX/releases/tag/v9.9.9"}

    payload = {"version": "9.9.8", "url": "https://updates.example.com/phonix-9.9.8.update"}
    r = client.post("/system/firmware/check", headers=headers)
    assert "Version 9.9.8 is available" in r.text
    assert "phonix-9.9.8.update" in r.text

    monkeypatch.setattr(system_routes, "__version__", "1.1.0.dev0")
    payload = {"tag_name": "v1.0.1", "html_url": "https://github.com/PhonixPBX/PhonixPBX/releases/tag/v1.0.1"}
    r = client.post("/system/firmware/check", headers=headers)
    assert "is available" not in r.text
    assert "running the latest version (1.1.0.dev0)" in r.text

    payload = {"tag_name": "v1.1.0", "html_url": "https://github.com/PhonixPBX/PhonixPBX/releases/tag/v1.1.0"}
    r = client.post("/system/firmware/check", headers=headers)
    assert "Version 1.1.0 is available" in r.text

    payload = {"url": "https://updates.example.com/phonix.update"}
    r = client.post("/system/firmware/check", headers=headers)
    assert "Update check failed: the response contains no version" in r.text


@pytest.mark.parametrize(
    "latest,current,newer",
    [
        ("1.0.1", "1.1.0.dev0", False),
        ("1.1.0", "1.1.0.dev0", True),
        ("1.1.0-rc.1", "1.1.0.dev0", True),
        ("1.1.0", "1.1.0-rc.1", True),
        ("1.1.0-rc.2", "1.1.0-rc.10", False),
        ("1.1.0-alpha", "1.1.0-alpha.1", False),
        ("1.1.0-beta", "1.1.0-alpha.1", True),
        ("1.1.0", "1.2.0rc1", False),
        ("1.2.0", "1.2.0rc1", True),
        ("1.2.0rc1", "1.2.0b2", True),
        ("1.2.0a1", "1.2.0.dev0", True),
        ("1.2.0.dev1", "1.2.0.dev0", True),
        ("1.2.0.post1", "1.2.0", True),
        ("1.2.0", "1.2.0.post1", False),
        ("1.2", "1.2.0", False),
        ("v1.0.0+build.5", "1.0.0", False),
        ("v2.0.0", "1.9.9", True),
        ("1.10.0", "1.9.0", True),
        ("nightly", "1.0.0", True),
        ("nightly", "nightly", False),
    ],
)
def test_update_is_newer(latest, current, newer):
    from phonix.services import update

    assert update.is_newer(latest, current) is newer


def test_application_logs(client, runtime, tmp_path):
    path = runtime.log_files["web"] = tmp_path / "web.log"
    path.write_text("INFO: started <server>\n")
    login(client)
    r = client.get("/status/logs?log=web")
    assert r.status_code == 200
    assert "INFO: started &lt;server&gt;" in r.text
    assert "/status/logs?log=monitor" in r.text


def test_api_calls(client, fake_ami):
    from sqlalchemy import select

    from phonix.core.models import AuditLog, Phone

    body = {"extension": "101", "number": "0441234567"}
    assert client.post("/api/v1/calls", json=body).status_code == 401
    assert client.post("/api/v1/calls", json=body, headers=bearer()).status_code == 403
    r = client.post("/api/v1/calls", json=body, headers=bearer(read_only=True, allow_calls=True))
    assert r.status_code == 202, r.text
    assert r.json() == {"extension": "101", "number": "0441234567", "status": "ringing"}
    name, fields = fake_ami.actions[0]
    assert name == "Originate"
    assert fields["Channel"] == "PJSIP/101" and fields["Context"] == "phone-101" and fields["Exten"] == "0441234567"
    with session_scope() as s:
        assert s.query(AuditLog).filter_by(action="originate").one().summary == "101 -> 0441234567 (API)"

    auth = bearer(allow_calls=True)
    r = client.post("/api/v1/calls", json={**body, "number": "1\r\nAction: Command"}, headers=auth)
    assert r.status_code == 422 and "number" in r.json()["detail"]["fields"]
    assert client.post("/api/v1/calls", json={**body, "extension": "999"}, headers=auth).status_code == 404
    with session_scope() as s:
        s.scalar(select(Phone).where(Phone.extension == "102")).enabled = False
    assert client.post("/api/v1/calls", json={**body, "extension": "102"}, headers=auth).status_code == 422
    r = client.post("/api/v1/calls", json={**body, "extension": "103"}, headers=auth)
    assert r.status_code == 202 and fake_ami.actions[-1][1]["Channel"] == "IAX2/103"
    fake_ami.response = {"Response": "Error", "Message": "Extension does not exist."}
    r = client.post("/api/v1/calls", json=body, headers=auth)
    assert r.status_code == 422 and "Extension does not exist" in r.json()["detail"]["message"]

    fake_ami.response = {"Response": "Success"}
    login(client)
    assert client.post("/api/v1/calls", json=body).status_code == 403  # CSRF
    r = client.post("/api/v1/calls", json=body, headers={"X-CSRF-Token": csrf(client, "/")})
    assert r.status_code == 202

    schema = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/calls" in schema["paths"]


def test_api_legacy_import_export(client):
    from pathlib import Path

    from sqlalchemy import func, select

    from phonix.core.models import Phone

    xml = (Path(__file__).parent / "legacy" / "fixtures" / "generic-pc.xml").read_bytes()
    auth = bearer()
    with session_scope() as s:
        before = s.scalar(select(func.count()).select_from(Phone))
    # preview by default: nothing changes
    r = client.post("/api/v1/legacy/import", content=xml, headers=auth)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["dry_run"]
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Phone)) == before
    assert client.post("/api/v1/legacy/import", content=b"<nope/>", headers=auth).status_code == 422
    read_only = bearer(read_only=True)
    assert client.post("/api/v1/legacy/import?dry_run=false", content=xml, headers=read_only).status_code == 403
    r = client.post("/api/v1/legacy/import?dry_run=false&mode=replace", content=xml, headers=auth)
    assert r.status_code == 200 and not r.json()["dry_run"]
    # the export has plaintext secrets: no read-only tokens, even though it is a GET
    assert client.get("/api/v1/legacy/export", headers=read_only).status_code == 403
    r = client.get("/api/v1/legacy/export", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"] == "application/xml"
    assert r.content.startswith(b"<?xml")


def test_firstboot_legacy_report_on_dashboard(client, runtime):
    import json

    report = {"ok": True, "dry_run": False, "mode": "replace", "source_version": "2.2", "items": [], "summary": {}}
    report |= {"counts": {"phones": {"create": 3}}, "dropped_sections": ["isdn"]}
    runtime.state_dir.mkdir(parents=True, exist_ok=True)
    (runtime.state_dir / "legacy-import-report.json").write_text(json.dumps(report))
    login(client)
    page = client.get("/").text
    assert "was imported at first boot" in page and "config.xml version 2.2" in page and "isdn" in page
    r = client.post("/legacy-report/dismiss", data={"csrf_token": csrf(client, "/")}, follow_redirects=False)
    assert r.status_code == 303
    assert "was imported at first boot" not in client.get("/").text


def test_firmware_job_guards(client, runtime, monkeypatch, tmp_path):
    import fcntl

    from phonix.services import privileged, update
    from phonix.services.common import ServiceError

    login(client)
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-1")
    update.write_job("running", "write")
    # no reboot or factory reset in the middle of an install
    privileged.recorder.calls.clear()
    token = csrf(client, "/system/reboot")
    client.post("/system/reboot", data={"csrf_token": token, "action": "reboot"})
    client.post("/system/defaults", data={"csrf_token": token, "confirm": "RESET"})
    assert not privileged.recorder.calls
    # after a reboot the stored pid means nothing: the job was interrupted
    monkeypatch.setattr(update, "_boot_id", lambda: "boot-2")
    assert update.read_job()["interrupted"] and not update.is_running()
    # one install at a time, also from the console
    bundle = tmp_path / "x.update"
    bundle.write_bytes(b"bundle")
    runtime.state_dir.mkdir(parents=True, exist_ok=True)
    with open(runtime.state_dir / "update.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(ServiceError, match="already being installed"):
            update.run_install(bundle, "cli")
    # --remove only for web uploads
    with pytest.raises(ServiceError, match="--remove"):
        update.run_install(bundle, "cli", remove=True)
    assert bundle.exists()
