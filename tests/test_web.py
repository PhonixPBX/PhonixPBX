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


def bearer(read_only=False, expires_in_days=None, name="test"):
    """Authorization header with a new API token of ``admin``."""
    from phonix.services import tokens

    with session_scope() as s:
        _, plain = tokens.create(
            s, users.get_by_name(s, "admin"), name, read_only=read_only, expires_in_days=expires_in_days
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
    with session_scope() as s:
        token = s.query(ApiToken).filter_by(name="monitoring").one()
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
