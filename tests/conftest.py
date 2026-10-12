from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from askozia import config
from askozia.core import db


@pytest.fixture(autouse=True)
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[config.RuntimeConfig]:
    """Every test gets its own data dir and generated-files root."""
    monkeypatch.setenv("ASKOZIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASKOZIA_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("ASKOZIA_PRIVILEGED", "dry-run")
    monkeypatch.setenv("ASKOZIA_BOOT_DIR", str(tmp_path / "boot"))
    monkeypatch.setenv("ASKOZIA_DEV", "1")
    config.reset_cache()
    db.dispose()
    from askozia.web import security

    security.login_limiter._hits.clear()
    yield config.get()
    db.dispose()
    config.reset_cache()


@pytest.fixture
def initialized(runtime: config.RuntimeConfig) -> config.RuntimeConfig:
    from askozia.services import setup

    setup.initialize()
    return runtime


@pytest.fixture
def session(initialized: config.RuntimeConfig) -> Iterator[Session]:
    with db.session_scope() as s:
        yield s


@pytest.fixture
def empty_session(runtime: config.RuntimeConfig) -> Iterator[Session]:
    from askozia.core import migrate

    migrate.upgrade()
    with db.session_scope() as s:
        yield s
