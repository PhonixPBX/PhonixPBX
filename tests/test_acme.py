# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import datetime as dt
import re
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_web import bearer, csrf, login

from phonix.core import settings as st
from phonix.core.db import session_scope
from phonix.services import acme, privileged, tls, users
from phonix.services.common import ServiceError

CF = {"CF_DNS_API_TOKEN": "cf-secret-token"}


def _issue_pem(names, days=90):
    """Certificate for ``names`` signed by a throwaway CA (PEM chain, PEM key)."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


class FakeLego:
    """Stands in for subprocess.run: writes what lego would write."""

    def __init__(self, returncode=0, days=90):
        self.returncode = returncode
        self.days = days
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs["env"]))
        if argv[1] == "migrate":
            return subprocess.CompletedProcess(argv, 0, stdout="")
        names = [argv[i + 1] for i, a in enumerate(argv) if a == "--domains"]
        if self.returncode == 0:
            crt, key = acme.issued_files(names)
            crt.parent.mkdir(parents=True, exist_ok=True)
            crt_pem, key_pem = _issue_pem(names, self.days)
            crt.write_bytes(crt_pem)
            key.write_bytes(key_pem)
            out = '2026-10-25T16:31:42.7Z INFO  Server responded with a certificate. domains="pbx.example.org"\n'
        else:
            out = (
                "2026-10-25T16:30:47.472653920Z INFO  dns01: Trying to solve DNS-01. domain=pbx.example.org\n"
                '2026-10-25T16:30:51.607662001Z ERROR Error error="obtain certificate: resolver: one or more domains'
                ' had a problem: [pbx.example.org: NXDOMAIN for \\"_acme-challenge\\"]"\n'
            )
        return subprocess.CompletedProcess(argv, self.returncode, stdout=out)


@pytest.fixture
def fake_lego(monkeypatch):
    fake = FakeLego()
    monkeypatch.setattr(acme.subprocess, "run", fake)
    monkeypatch.setattr(acme.ami, "is_running", lambda: False)
    return fake


def _enable(session, **kw):
    values = {"enabled": True, "email": "admin@example.org", "domains": ["pbx.example.org"], **kw}
    st.save(session, st.AcmeSettings(**values))


def test_build_command_http(runtime):
    s = st.AcmeSettings(enabled=True, email="a@example.org")
    argv, env = acme.build_command(s, ["pbx.example.org", "sip.example.org"])
    assert argv[:2] == ["lego", "run"]
    assert {"--renew-force", "--no-random-sleep", "--force-cert-domains"} <= set(argv)
    assert argv[argv.index("--server") + 1] == st.ACME_SERVERS["letsencrypt"]
    assert argv[argv.index("--http.webroot") + 1] == str(runtime.acme_webroot)
    assert argv.count("--domains") == 2 and "--dns" not in argv
    assert env == {"PATH": env["PATH"], "HOME": str(runtime.acme_dir)}


def test_build_command_dns_and_eab(runtime):
    s = st.AcmeSettings(
        enabled=True,
        email="a@example.org",
        server="zerossl",
        eab_kid="kid1",
        eab_hmac="hmacsecret",
        challenge="dns",
        dns_provider="cloudflare",
        dns_env=CF,
        dns_resolvers=["1.1.1.1:53"],
    )
    argv, env = acme.build_command(s, ["*.example.org"])
    assert argv[argv.index("--dns") + 1] == "cloudflare"
    assert argv[argv.index("--dns.resolvers") + 1] == "1.1.1.1:53"
    assert "--http" not in argv and "hmacsecret" not in argv
    assert env["CF_DNS_API_TOKEN"] == "cf-secret-token"
    assert env["LEGO_EAB_HMAC"] == "hmacsecret" and env["LEGO_EAB_KID"] == "kid1"
    assert acme.issued_files(["*.example.org"])[0].name == "_.example.org.crt"


@pytest.mark.parametrize(
    "values",
    [
        {"domains": ["*.example.org"], "challenge": "http"},
        {"domains": ["localhost"]},
        {"enabled": True, "email": "a@example.org", "server": "zerossl"},
        {"enabled": True, "email": "a@example.org", "challenge": "dns"},
        {"enabled": True},
        {"dns_env": {"LD_PRELOAD": "/tmp/x.so"}},
        {"dns_env": {"lower": "x"}},
        {"server_url": "http://acme.example.org/dir"},
    ],
)
def test_settings_rejected(values):
    with pytest.raises(ValidationError):
        st.AcmeSettings(**values)


def test_issue_and_renewal(session, fake_lego):
    assert acme.issue(session) == "ACME is disabled."
    _enable(session)
    assert acme.renewal_reason(["pbx.example.org"]) == "no certificate installed"
    tls.generate_self_signed("phonix.local")
    assert acme.renewal_reason(["pbx.example.org"]) == "self-signed certificate installed"
    privileged.recorder.calls.clear()
    message = acme.issue(session)
    assert "installed" in message and len(fake_lego.calls) == 1
    cert = tls.current_certificate()
    assert tls.dns_names(cert) == ["pbx.example.org"]
    assert ("nginx-reload",) in privileged.recorder.calls
    assert acme.read_status()["state"] == "ok"
    # valid for 90 days: nothing to do until forced or the names change
    assert "nothing to do" in acme.issue(session)
    assert len(fake_lego.calls) == 1
    _enable(session, domains=["pbx.example.org", "sip.example.org"])
    assert acme.renewal_reason(["pbx.example.org", "sip.example.org"]) == "domain names changed"
    acme.issue(session)
    assert len(fake_lego.calls) == 2


def test_renewal_when_expiring(session, fake_lego):
    _enable(session)
    fake_lego.days = 10
    acme.issue(session)
    assert acme.renewal_reason(["pbx.example.org"]).startswith("expires in")


def test_issue_failure_keeps_certificate(session, fake_lego):
    before = tls.certificate_info()
    _enable(session, challenge="dns", dns_provider="cloudflare", dns_env=CF)
    fake_lego.returncode = 1
    with pytest.raises(ServiceError, match="NXDOMAIN"):
        acme.issue(session, force=True)
    status = acme.read_status()
    assert status["state"] == "error" and "NXDOMAIN" in status["message"]
    assert any("DNS-01" in line for line in status["log"])
    assert tls.certificate_info() == before


def test_lego_error():
    out = (
        "2026-10-25T16:30:51.604819344Z INFO  Deactivating authorization. url=https://x\n"
        '2026-10-25T16:30:51.607662001Z ERROR Error error="obtain certificate: \\"a\\" failed"\n\n'
    )
    assert acme._lego_error(out) == 'obtain certificate: "a" failed'
    assert acme._lego_error("2026-10-25T16:30:51.6Z WARN  something odd\n") == "something odd"
    assert acme._lego_error("") == ""


def _v4_state(base):
    account = base / "accounts" / "acme-v02.api.letsencrypt.org" / "admin@example.org"
    (account / "keys").mkdir(parents=True)
    (account / "keys" / "admin@example.org.key").write_text("KEY")
    (account / "account.json").write_text('{"email": "admin@example.org"}')
    (base / "certificates").mkdir()
    (base / "certificates" / "pbx.example.org.json").write_text('{"domain": "pbx.example.org"}')


def test_needs_migration(runtime):
    base = runtime.acme_dir
    assert not acme.needs_migration()
    _v4_state(base)
    assert acme.needs_migration()
    # what lego migrate leaves behind
    account = base / "accounts" / "acme-v02.api.letsencrypt.org" / "admin@example.org"
    (account / "account.json").write_text('{"id": "admin@example.org", "origin": "migration"}')
    assert acme.needs_migration()
    (base / "certificates" / "pbx.example.org.json").write_text('{"id": "pbx.example.org", "origin": "migration"}')
    assert not acme.needs_migration()


def test_issue_migrates_v4_state(session, runtime, fake_lego):
    _enable(session)
    _v4_state(runtime.acme_dir)
    (runtime.acme_dir / "certificates" / "pbx.example.org.json").unlink()
    (runtime.acme_dir / "certificates").rmdir()
    acme.issue(session, force=True)
    assert (runtime.acme_dir / "certificates").is_dir()
    (migrate_argv, migrate_env), (run_argv, _) = fake_lego.calls
    assert migrate_argv == ["lego", "migrate", "--path", str(runtime.acme_dir)]
    assert migrate_env == {"PATH": migrate_env["PATH"], "HOME": str(runtime.acme_dir)}
    assert run_argv[1] == "run"


def test_interrupted_status(runtime):
    acme.write_status("running", "busy", pid=2**22 + 12345)
    assert acme.read_status()["state"] == "error"


def test_tls_transport_used(session):
    assert not acme.tls_transport_used(session)
    sip = st.load(session, st.SipSettings)
    sip.tls_enabled = True
    st.save(session, sip)
    assert acme.tls_transport_used(session)


@pytest.fixture
def client(initialized):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
    tls.generate_self_signed("phonix.local")
    with TestClient(create_app()) as c:
        login(c)
        yield c


def _form(c, **extra):
    data = {
        "csrf_token": csrf(c, "/advanced/certificate"),
        "enabled__present": "1",
        "enabled": "true",
        "server": "letsencrypt",
        "email": "admin@example.org",
        "domains": "pbx.example.org",
        "challenge": "dns",
        "dns_provider_choice": "cloudflare",
        "env__cloudflare__CF_DNS_API_TOKEN": "",
        "dns_resolvers": "",
    }
    data.update(extra)
    return c.post("/advanced/certificate/acme", data=data, follow_redirects=False)


def test_acme_form_keeps_secrets(client):
    page = client.get("/advanced/certificate").text
    assert "Automatic (ACME)" in page and "phonix.local is not a public DNS name" in page
    # the token is required for the chosen provider
    r = _form(client)
    assert r.status_code == 422 and "Missing DNS provider credentials" in r.text
    r = _form(client, env__cloudflare__CF_DNS_API_TOKEN="cf-secret-token")
    assert r.status_code == 303
    page = client.get("/advanced/certificate").text
    assert "cf-secret-token" not in page and "unchanged - leave empty to keep" in page
    # saving again without the token keeps it
    assert _form(client, domains="pbx.example.org\nsip.example.org").status_code == 303
    with session_scope() as s:
        saved = st.load(s, st.AcmeSettings)
    assert saved.dns_env == CF and saved.domains == ["pbx.example.org", "sip.example.org"]
    # the API does not return it either
    r = client.get("/api/v1/settings/acme", headers=bearer(read_only=True))
    assert r.status_code == 200 and r.json()["dns_env"] == {"CF_DNS_API_TOKEN": ""}


def test_acme_form_other_provider(client):
    r = _form(
        client,
        dns_provider_choice="other",
        dns_provider_other="powerdns",
        dns_env_text="PDNS_API_URL=https://ns.example.org\nPDNS_API_KEY=secret",
    )
    assert r.status_code == 303
    r = _form(client, dns_provider_choice="other", dns_provider_other="powerdns", dns_env_text="PDNS_API_KEY=")
    with session_scope() as s:
        assert st.load(s, st.AcmeSettings).dns_env == {"PDNS_API_KEY": "secret"}
    r = _form(client, dns_provider_choice="other", dns_provider_other="x", dns_env_text="PATH=/tmp")
    assert r.status_code == 422


def test_acme_request_and_status(client, monkeypatch):
    started = []
    monkeypatch.setattr(acme, "start_background", lambda: started.append(True))
    assert _form(client, env__cloudflare__CF_DNS_API_TOKEN="t").status_code == 303
    assert started == []
    r = client.post(
        "/advanced/certificate/acme?issue=1",
        data={
            "csrf_token": csrf(client, "/advanced/certificate"),
            "enabled__present": "1",
            "enabled": "true",
            "email": "admin@example.org",
            "domains": "pbx.example.org",
            "challenge": "http",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and started == [True]
    acme.write_status("ok", "Certificate installed.")
    r = client.get("/advanced/certificate/acme/status?was=running")
    assert "Certificate installed." in r.text and r.headers.get("HX-Refresh") == "true"


def test_regenerate_turns_acme_off(client):
    with session_scope() as s:
        _enable(s)
    r = client.post(
        "/advanced/certificate/regenerate",
        data={"csrf_token": csrf(client, "/advanced/certificate")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with session_scope() as s:
        assert not st.load(s, st.AcmeSettings).enabled


def test_certificate_tab_follows_source(client):
    def active(page):
        return re.search(r'class="tab-pane active show" id="tab-(\w+)"', page).group(1)

    page = client.get("/advanced/certificate").text
    assert active(page) == "selfsigned" and "days left" in page
    # an upload error opens the upload tab
    r = client.post(
        "/advanced/certificate",
        data={"csrf_token": csrf(client, "/advanced/certificate")},
        files={"certificate": ("c.pem", b"junk"), "private_key": ("k.pem", b"junk")},
    )
    assert r.status_code == 422 and active(r.text) == "upload"
    with session_scope() as s:
        _enable(s)
    page = client.get("/advanced/certificate").text
    assert active(page) == "acme" and "renewed automatically" in page


def test_self_signed_includes_mdns_name():
    tls.generate_self_signed("pbx.example.org")
    assert {"pbx.example.org", "pbx.local"} <= set(tls.dns_names(tls.current_certificate()))
    tls.generate_self_signed("phonix.local")
    assert tls.dns_names(tls.current_certificate()).count("phonix.local") == 1
