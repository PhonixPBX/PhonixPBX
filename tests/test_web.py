# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import base64
import re

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


def test_firmware_upload_removes_bundle(client, monkeypatch, runtime):
    from phonix.services import update
    from phonix.services.common import ServiceError

    seen = []

    def fake_install(path):
        seen.append((path, path.read_bytes()))
        if len(seen) == 1:
            raise ServiceError("Update signature is invalid")
        return update.BundleInfo("9.9.9", "pc-amd64", {})

    monkeypatch.setattr(update, "install", fake_install)
    login(client)
    headers = {"HX-Request": "true", "X-CSRF-Token": csrf(client, "/system/firmware")}
    files = {"file": ("x.update", b"bundle", "application/octet-stream")}
    r = client.post("/system/firmware/upload", headers=headers, files=files)
    assert r.status_code == 422 and "Update signature is invalid" in r.text
    r = client.post("/system/firmware/upload", headers=headers, files=files)
    assert r.status_code == 200
    assert [content for _, content in seen] == [b"bundle", b"bundle"]
    assert seen[0][0] != seen[1][0]  # unique per upload
    assert not list(runtime.data_dir.glob("update*"))


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
    # the dashboard shows the result of the last check
    assert "PhonixPBX 9.9.9 is available" in client.get("/").text

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
