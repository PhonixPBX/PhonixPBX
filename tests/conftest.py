# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from phonix import config
from phonix.core import db


@pytest.fixture(autouse=True)
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[config.RuntimeConfig]:
    """Every test gets its own data dir and generated-files root."""
    monkeypatch.setenv("PHONIX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PHONIX_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("PHONIX_PRIVILEGED", "dry-run")
    monkeypatch.setenv("PHONIX_BOOT_DIR", str(tmp_path / "boot"))
    monkeypatch.setenv("PHONIX_DEV", "1")
    config.reset_cache()
    db.dispose()
    from phonix.web import security

    security.login_limiter._hits.clear()
    yield config.get()
    db.dispose()
    config.reset_cache()


@pytest.fixture
def initialized(runtime: config.RuntimeConfig) -> config.RuntimeConfig:
    from phonix.services import setup

    setup.initialize()
    return runtime


@pytest.fixture
def session(initialized: config.RuntimeConfig) -> Iterator[Session]:
    with db.session_scope() as s:
        yield s


@pytest.fixture
def empty_session(runtime: config.RuntimeConfig) -> Iterator[Session]:
    from phonix.core import migrate

    migrate.upgrade()
    with db.session_scope() as s:
        yield s


class FakeAmi:
    """Stands in for ``ami.AmiClient``; records the actions and keeps an Asterisk database."""

    actions: list = []
    response = {"Response": "Success", "Message": "Originate successfully queued"}
    astdb: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def action(self, name, **fields):
        FakeAmi.actions.append((name, fields))
        return FakeAmi.response

    def command(self, cli):
        FakeAmi.actions.append(("Command", {"Command": cli}))
        words = cli.split()
        if words[:2] == ["database", "get"]:
            value = FakeAmi.astdb.get((words[2], words[3]))
            return f"Value: {value}\n" if value else "Database entry not found.\n"
        if words[:2] == ["database", "put"]:
            FakeAmi.astdb[(words[2], words[3])] = words[4]
            return "Updated database successfully\n"
        if words[:2] == ["database", "show"]:
            rows = [f"/{f}/{k:<30}: {v}" for (f, k), v in sorted(FakeAmi.astdb.items()) if f == words[2]]
            return "\n".join([*rows, f"{len(rows)} results found."]) + "\n"
        if words[:2] == ["database", "del"]:
            FakeAmi.astdb.pop((words[2], words[3]), None)
            return "Database entry removed.\n"
        if words[:2] == ["database", "deltree"]:
            gone = [key for key in FakeAmi.astdb if key[0] == words[2]]
            for key in gone:
                del FakeAmi.astdb[key]
            return f"{len(gone)} database entries removed.\n"
        return ""


@pytest.fixture
def fake_ami(monkeypatch):
    from phonix.services import calls

    FakeAmi.actions = []
    FakeAmi.astdb = {}
    FakeAmi.response = {"Response": "Success", "Message": "Originate successfully queued"}
    monkeypatch.setattr(calls.ami, "AmiClient", FakeAmi)
    return FakeAmi
