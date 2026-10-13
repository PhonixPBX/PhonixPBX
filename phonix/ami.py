# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Minimal synchronous Asterisk Manager Interface client.

Used for reloads, status queries and (in a background thread) security events.
Kept dependency free on purpose; AMI is a simple line based protocol.
"""

from __future__ import annotations

import contextlib
import itertools
import socket
from collections.abc import Iterator
from typing import Any

from phonix import config
from phonix.services import secrets

Message = dict[str, str]


class AmiError(Exception):
    pass


class AmiClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str = "phonix",
        secret: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        cfg = config.get()
        self.host = host or cfg.ami_host
        self.port = port or cfg.ami_port
        self.username = username
        self.secret = secret
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = b""
        self._ids = itertools.count(1)

    # -- connection -------------------------------------------------------------

    def __enter__(self) -> AmiClient:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            banner = self._readline()
        except OSError as exc:
            raise AmiError(f"cannot connect to Asterisk manager: {exc}") from exc
        if not banner.startswith("Asterisk Call Manager"):
            raise AmiError("unexpected AMI banner")
        secret = self.secret if self.secret is not None else secrets.get("ami_internal")
        resp = self.action("Login", Username=self.username, Secret=secret, Events="off")
        if resp.get("Response") != "Success":
            raise AmiError(resp.get("Message", "login failed"))

    def close(self) -> None:
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._send({"Action": "Logoff"})
            self._sock.close()
            self._sock = None

    # -- protocol -----------------------------------------------------------------

    def _readline(self) -> str:
        assert self._sock is not None
        while b"\r\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise AmiError("connection closed by Asterisk")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line.decode("utf-8", "replace")

    def read_message(self) -> Message:
        msg: Message = {}
        last_key = ""
        while True:
            line = self._readline()
            if line == "":
                if msg:
                    return msg
                continue
            if ": " in line:
                key, value = line.split(": ", 1)
                if key in msg:  # repeated keys (e.g. Output) are joined
                    msg[key] += "\n" + value
                else:
                    msg[key] = value
                last_key = key
            elif line.endswith(":"):
                msg[line[:-1]] = ""
                last_key = line[:-1]
            elif last_key:
                msg[last_key] += "\n" + line

    def _send(self, fields: dict[str, Any]) -> None:
        assert self._sock is not None
        data = "".join(f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"
        self._sock.sendall(data.encode())

    def action(self, name: str, **fields: Any) -> Message:
        action_id = str(next(self._ids))
        self._send({"Action": name, "ActionID": action_id, **fields})
        while True:
            msg = self.read_message()
            if msg.get("ActionID") == action_id and "Response" in msg:
                return msg

    def action_list(self, name: str, **fields: Any) -> list[Message]:
        """Actions answering with an event list (e.g. PJSIPShowContacts)."""
        action_id = str(next(self._ids))
        self._send({"Action": name, "ActionID": action_id, **fields})
        events: list[Message] = []
        while True:
            msg = self.read_message()
            if msg.get("ActionID") != action_id:
                continue
            if msg.get("Response") == "Error":
                raise AmiError(msg.get("Message", "action failed"))
            if msg.get("EventList") == "Complete":
                return events
            if "Event" in msg:
                events.append(msg)

    def command(self, cli: str) -> str:
        resp = self.action("Command", Command=cli)
        if resp.get("Response") == "Error":
            raise AmiError(resp.get("Message", "command failed"))
        return resp.get("Output", resp.get("Message", ""))

    def events(self) -> Iterator[Message]:
        """Enable events and yield them forever (blocking, no timeout)."""
        self.action("Events", EventMask="on")
        assert self._sock is not None
        self._sock.settimeout(None)
        while True:
            msg = self.read_message()
            if "Event" in msg:
                yield msg


def run_commands(commands: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    with AmiClient() as ami:
        for cmd in commands:
            out[cmd] = ami.command(cmd)
    return out


def is_running() -> bool:
    try:
        with AmiClient(timeout=2.0) as ami:
            ami.action("Ping")
        return True
    except AmiError:
        return False
