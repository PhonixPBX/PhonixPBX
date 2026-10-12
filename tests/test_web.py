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
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:adminadmin").decode()}
    assert client.get("/api/v1/settings/system", headers=auth).json()["ssh_password_hash"] == ""
    assert client.patch("/api/v1/settings/system", headers=auth, json={"ssh_password_hash": ""}).status_code == 200
    assert stored() == pw
    assert post(ssh_password_clear="true").status_code == 303 and stored() == ""


def test_apply_via_htmx(client):
    login(client)
    token = csrf(client)
    r = client.post("/apply", headers={"HX-Request": "true", "X-CSRF-Token": token})
    assert r.status_code == 200 and "Configuration applied" in r.text


def test_api_basic_auth(client):
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:adminadmin").decode()}
    assert client.get("/api/v1/phones").status_code == 401
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
