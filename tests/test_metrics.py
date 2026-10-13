# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import re

from test_web import bearer, client  # noqa: F401 - fixture

from phonix.core.db import session_scope
from phonix.core.models import Provider
from phonix.services import status

LINE = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{([a-z_]+="([^"\\]|\\.)*",?)*\})? -?[0-9.e+-]+$')


def _samples(text):
    out = {}
    for line in text.splitlines():
        if line.startswith("#"):
            assert re.match(r"^# (HELP|TYPE) [a-z_]+ .+$", line), line
            continue
        assert LINE.match(line), line
        name, _, value = line.rpartition(" ")
        out[name] = float(value)
    return out


def test_metrics_requires_token(client):  # noqa: F811
    assert client.get("/api/v1/metrics").status_code == 401
    r = client.get("/api/v1/metrics", headers=bearer(read_only=True))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")
    m = _samples(r.text)
    assert m["phonix_asterisk_up"] == 0  # no Asterisk in the test environment
    assert m['phonix_phones{tech="pjsip",enabled="true"}'] >= 1
    assert m["phonix_providers"] == 3
    assert "phonix_memory_total_bytes" in m and "phonix_data_disk_used_bytes" in m
    assert not any(k.startswith("phonix_phone_registered") for k in m)


def test_metrics_with_asterisk(client, runtime, monkeypatch):  # noqa: F811
    with session_scope() as s:
        trunk = s.query(Provider).filter_by(name="Example Trunk").one()
        trunk.name = 'Trunk "A"'
        trunk_id, iax_id = trunk.id, s.query(Provider).filter_by(name="IAX Trunk").one().id
    fake = {
        "running": True,
        "version": "22.5.0",
        "uptime": "",
        "started": "2026-10-12 08:00:00",
        "current_calls": 2,
        "endpoints": {"101": {"state": "Not in use", "addresses": [{"uri": "sip:101@10.0.0.5"}]}},
        "registrations": {f"prov-{trunk_id}-reg": "Registered"},
        "iax_peers": {f"prov-{iax_id}": "UNREACHABLE", "103": "OK (12 ms)"},
        "channels": [{}, {}, {}, {}],
        "error": "",
    }
    monkeypatch.setattr(status, "asterisk_status", lambda: fake)
    inbox = runtime.path("/var/spool/asterisk/voicemail/default/101/INBOX")
    inbox.mkdir(parents=True)
    for n in range(3):
        (inbox / f"msg{n:04}.txt").write_text("")
        (inbox / f"msg{n:04}.wav").write_bytes(b"")
    m = _samples(client.get("/api/v1/metrics", headers=bearer(read_only=True)).text)
    assert m["phonix_asterisk_up"] == 1 and m["phonix_asterisk_active_calls"] == 2
    assert m["phonix_asterisk_active_channels"] == 4
    assert 'phonix_build_info{version="' in next(k for k in m if k.startswith("phonix_build_info"))
    assert m['phonix_phone_registered{extension="101",tech="pjsip"}'] == 1
    assert m['phonix_phone_registered{extension="102",tech="pjsip"}'] == 0
    assert m['phonix_phone_registered{extension="103",tech="iax"}'] == 1
    assert m[f'phonix_provider_up{{provider="prov-{trunk_id}",name="Trunk \\"A\\"",tech="pjsip"}}'] == 1
    assert m[f'phonix_provider_up{{provider="prov-{iax_id}",name="IAX Trunk",tech="iax"}}'] == 0
    assert m['phonix_voicemail_messages{context="default",mailbox="101",folder="INBOX"}'] == 3
    assert m['phonix_voicemail_messages{context="default",mailbox="101",folder="Old"}'] == 0
    assert m["phonix_asterisk_start_time_seconds"] > 0
