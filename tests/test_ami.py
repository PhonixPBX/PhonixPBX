# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import pytest

from phonix import ami
from phonix.services import status


def _frame(**fields):
    return "".join(f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"


class FakeSocket:
    """Answers each AMI action with canned frames, keyed by action name."""

    def __init__(self, replies):
        self.replies = replies
        self.out = b""

    def sendall(self, data):
        fields = dict(line.split(": ", 1) for line in data.decode().split("\r\n") if ": " in line)
        if fields.get("Action") == "Logoff":
            return
        reply = self.replies.get(fields["Action"], [{"Response": "Success"}])
        self.out += "".join(_frame(ActionID=fields["ActionID"], **f) for f in reply).encode()

    def recv(self, size):
        data, self.out = self.out[:size], self.out[size:]
        return data

    def close(self):
        pass


def _list(event, *items):
    return [
        {"Response": "Success", "EventList": "start"},
        *({"Event": event, **i} for i in items),
        {"Event": f"{event}Complete", "EventList": "Complete"},
    ]


def _client(replies):
    client = ami.AmiClient(secret="x")
    client._sock = FakeSocket(replies)  # type: ignore[assignment]
    return client


def test_action_list_empty_error_is_empty_list():
    client = _client({"PJSIPShowContacts": [{"Response": "Error", "Message": "No Contacts found"}]})
    assert client.action_list("PJSIPShowContacts") == []


def test_action_list_other_error_raises():
    client = _client({"Foo": [{"Response": "Error", "Message": "Permission denied"}]})
    with pytest.raises(ami.AmiError, match="Permission denied"):
        client.action_list("Foo")


def test_asterisk_status_without_contacts(monkeypatch):
    replies = {
        "PJSIPShowEndpoints": _list("EndpointList", {"ObjectName": "prov-1", "DeviceState": "Not in use"}),
        "PJSIPShowContacts": [{"Response": "Error", "Message": "No Contacts found"}],
        "PJSIPShowRegistrationsOutbound": _list(
            "OutboundRegistrationDetail", {"ObjectName": "prov-1-reg", "Status": "Registered"}
        ),
        "IAXpeerlist": _list("PeerEntry"),
        "CoreShowChannels": _list("CoreShowChannel"),
    }
    monkeypatch.setattr(ami.AmiClient, "connect", lambda self: setattr(self, "_sock", FakeSocket(replies)))
    out = status.asterisk_status()
    assert out["error"] == ""
    assert out["registrations"] == {"prov-1-reg": "Registered"}
    assert out["endpoints"]["prov-1"]["state"] == "Not in use"
