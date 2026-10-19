# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from factories import sample_pbx
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_web import bearer

from phonix.core.db import session_scope
from phonix.core.models import AuditLog, Phone
from phonix.services import privileged, users


@pytest.fixture
def client(initialized):
    from phonix.web.app import create_app

    with session_scope() as s:
        users.create_user(s, "admin", "adminadmin")
        sample_pbx(s)
    with TestClient(create_app()) as c:
        yield c


def rpc(c, method, params=None, headers=None, msg_id=1):
    msg = {"jsonrpc": "2.0", "method": method, "id": msg_id}
    if params is not None:
        msg["params"] = params
    return c.post("/api/mcp", json=msg, headers=headers if headers is not None else bearer())


def call(c, name, headers=None, **arguments):
    r = rpc(c, "tools/call", {"name": name, "arguments": arguments}, headers)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_initialize_and_protocol(client):
    auth = bearer()
    r = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}, auth)
    result = r.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "phonix" and "tools" in result["capabilities"]
    r = rpc(client, "initialize", {"protocolVersion": "1999-01-01"}, auth)
    assert r.json()["result"]["protocolVersion"] == "2025-11-25"

    r = client.post("/api/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=auth)
    assert r.status_code == 202 and r.content == b""
    assert rpc(client, "ping", headers=auth).json() == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert rpc(client, "nope", headers=auth).json()["error"]["code"] == -32601
    assert (
        client.post("/api/mcp", json=[{"jsonrpc": "2.0", "method": "ping", "id": 1}], headers=auth).json()["error"][
            "code"
        ]
        == -32600
    )
    r = client.post("/api/mcp", content=b"{not json", headers={**auth, "content-type": "application/json"})
    assert r.json()["error"]["code"] == -32700
    assert rpc(client, "tools/call", {"name": "nope"}, auth).json()["error"]["code"] == -32602


def test_http_rules(client):
    assert rpc(client, "ping", headers={}).status_code == 401
    assert rpc(client, "ping", headers={"Authorization": "Bearer phx_wrong"}).status_code == 401
    auth = bearer()
    assert rpc(client, "ping", headers={**auth, "Origin": "https://evil.example"}).status_code == 403
    assert rpc(client, "ping", headers={**auth, "Origin": "http://testserver"}).status_code == 200
    assert rpc(client, "ping", headers={**auth, "Origin": "https://testserver:8443"}).status_code == 200
    assert rpc(client, "ping", headers={**auth, "Origin": "https://testserver.evil.example"}).status_code == 403
    assert rpc(client, "ping", headers={**auth, "MCP-Protocol-Version": "1999-01-01"}).status_code == 400
    assert rpc(client, "ping", headers={**auth, "MCP-Protocol-Version": "2025-06-18"}).status_code == 200
    r = client.get("/api/mcp", headers=auth)
    assert r.status_code == 405 and r.headers["allow"] == "POST"


def test_tools_list(client):
    tools = {t["name"]: t for t in rpc(client, "tools/list").json()["result"]["tools"]}
    for name in ("list_phones", "create_provider", "update_callgroup", "delete_conference", "list_ami_users"):
        assert name in tools
    assert "set_phone_enabled" in tools and "set_callgroup_enabled" not in tools
    assert set(tools["create_phone"]["inputSchema"]["required"]) == {"extension", "callerid"}
    assert tools["update_phone"]["inputSchema"]["required"] == ["id"]
    assert tools["delete_phone"]["annotations"]["destructiveHint"] is True
    assert tools["get_status"]["annotations"]["readOnlyHint"] is True

    ro = {t["name"] for t in rpc(client, "tools/list", headers=bearer(read_only=True)).json()["result"]["tools"]}
    assert "list_phones" in ro and "tail_log" in ro
    assert not ro & {"create_phone", "apply_changes", "update_settings"}


def test_read_only_token(client):
    ro = bearer(read_only=True)
    phones = call(client, "list_phones", ro)["structuredContent"]["items"]
    assert {p["extension"] for p in phones} >= {"101", "102"} and "secret" not in phones[0]
    status = call(client, "get_status", ro)["structuredContent"]
    assert "system" in status and "asterisk" in status
    result = call(client, "create_phone", ro, extension="160", callerid="RO")
    assert result["isError"] is True and "read-only" in result["content"][0]["text"]


def test_phone_crud(client):
    created = call(client, "create_phone", extension="160", callerid="MCP")
    assert "isError" not in created, created
    phone_id = created["structuredContent"]["id"]
    with session_scope() as s:
        secret = s.get(Phone, phone_id).secret
    assert secret

    updated = call(client, "update_phone", id=phone_id, callerid="Renamed")["structuredContent"]
    assert updated["callerid"] == "Renamed" and updated["extension"] == "160"
    with session_scope() as s:
        assert s.get(Phone, phone_id).secret == secret

    dup = call(client, "create_phone", extension="160", callerid="Dup")
    assert dup["isError"] is True and "extension" in dup["structuredContent"]["fields"]
    assert call(client, "get_phone", id=9999)["isError"] is True
    assert call(client, "get_phone", id="x")["isError"] is True
    assert call(client, "set_phone_enabled", id=phone_id, enabled=False)["structuredContent"]["enabled"] is False
    assert call(client, "delete_phone", id=phone_id)["structuredContent"] == {"deleted": True}

    with session_scope() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.object_type == "phone", AuditLog.object_id == str(phone_id)))
        assert {(a.username, a.action) for a in rows} == {
            ("admin (mcp)", "create"),
            ("admin (mcp)", "update"),
            ("admin (mcp)", "disable"),
            ("admin (mcp)", "delete"),
        }


def test_settings(client):
    assert "email" in call(client, "list_settings_groups")["structuredContent"]["groups"]
    email = call(client, "get_settings", group="email")["structuredContent"]
    assert email["password"] == "" and email["host"] == "smtp.example.com"
    r = call(client, "update_settings", group="email", values={"host": "mail.example.com", "password": ""})
    assert r["structuredContent"]["host"] == "mail.example.com"
    from phonix.core import settings as st

    with session_scope() as s:
        assert st.load(s, st.EmailSettings).password == 'p"w;d'
    assert call(client, "update_settings", group="rtp", values={"port_start": "x"})["isError"] is True
    assert call(client, "get_settings", group="nope")["isError"] is True
    assert "email" in call(client, "get_pending_changes")["structuredContent"]["pending"]


def test_preview_and_apply(client):
    preview = call(client, "preview_apply")["structuredContent"]
    assert preview["changed_files"] and preview["components"]
    privileged.recorder.calls.clear()
    result = call(client, "apply_changes")["structuredContent"]
    assert sorted(result["changed_files"]) == sorted(preview["changed_files"])
    assert call(client, "preview_apply")["structuredContent"]["changed_files"] == []
    assert result["ok"], result
    assert call(client, "get_pending_changes")["structuredContent"]["pending"] == []


def test_tail_log(client, runtime, tmp_path):
    path = runtime.log_files["asterisk"] = tmp_path / "messages"
    path.write_text("".join(f"line {i}\n" for i in range(10)))
    r = call(client, "tail_log", bearer(read_only=True), log="asterisk", lines=3)["structuredContent"]
    assert r["lines"] == ["line 7", "line 8", "line 9"]
    runtime.log_files["monitor"] = tmp_path / "monitor.log"
    runtime.log_files["monitor"].write_text("banned 192.0.2.1\n")
    r = call(client, "tail_log", log="monitor")["structuredContent"]
    assert r["lines"] == ["banned 192.0.2.1"]
    assert call(client, "tail_log", log="/etc/shadow")["isError"] is True
    assert call(client, "tail_log", log="asterisk", lines=5000)["isError"] is True
    board = runtime.path("/etc/phonix/board")
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text("oci-amd64\n")
    r = call(client, "tail_log", log="asterisk")
    assert r["isError"] is True and "container output" in r["content"][0]["text"]


def test_unexpected_tool_error_is_a_jsonrpc_error(client, monkeypatch):
    from phonix import mcp

    def boom(ctx, args):
        raise RuntimeError("boom")

    import dataclasses

    broken = dataclasses.replace(mcp.tools()["get_pending_changes"], handler=boom)
    monkeypatch.setattr(mcp, "_TOOLS", {**mcp.tools(), broken.name: broken})
    r = rpc(client, "tools/call", {"name": "get_pending_changes", "arguments": {}})
    assert r.status_code == 200
    assert r.json()["error"] == {"code": -32603, "message": "internal error in tool get_pending_changes"}


def test_read_only_tokens_get_no_pins(client):
    ro = bearer(read_only=True, name="ro")
    phones = call(client, "list_phones", ro)["structuredContent"]["items"]
    assert phones and all("vm_pin" not in p for p in phones)
    rooms = call(client, "list_conferences", ro)["structuredContent"]["items"]
    assert rooms and all("pin" not in r and "admin_pin" not in r for r in rooms)
    assert "vm_pin" in call(client, "get_phone", None, id=phones[0]["id"])["structuredContent"]

    assert all("vm_pin" not in p for p in client.get("/api/v1/phones", headers=ro).json())
    assert "pin" not in client.get(f"/api/v1/conferences/{rooms[0]['id']}", headers=ro).json()
    assert "pin" in client.get(f"/api/v1/conferences/{rooms[0]['id']}", headers=bearer()).json()


def test_originate_call(client, fake_ami):
    tools = {t["name"]: t for t in rpc(client, "tools/list").json()["result"]["tools"]}
    assert "originate_call" not in tools
    result = call(client, "originate_call", extension="101", number="0441234567")
    assert result["isError"] is True and "may not place calls" in result["content"][0]["text"]
    assert fake_ami.actions == []

    auth = bearer(read_only=True, allow_calls=True)
    tools = {t["name"]: t for t in rpc(client, "tools/list", headers=auth).json()["result"]["tools"]}
    assert tools["originate_call"]["annotations"]["openWorldHint"] is True
    assert "create_phone" not in tools
    result = call(client, "originate_call", auth, extension="101", number="0441234567")
    assert "isError" not in result
    assert result["structuredContent"] == {"extension": "101", "number": "0441234567", "status": "ringing"}
    assert fake_ami.actions[0][1]["Context"] == "phone-101"
    with session_scope() as s:
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "originate"))
        assert audit.summary == "101 -> 0441234567 (MCP)" and audit.username == "admin (mcp)"

    for args in ({"extension": "101", "number": "abc"}, {"extension": "999", "number": "1"}, {"extension": "101"}):
        assert call(client, "originate_call", auth, **args)["isError"] is True
