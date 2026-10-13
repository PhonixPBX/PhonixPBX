# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Machine-local secrets kept on the data partition (never in backups' DB rows)."""

from __future__ import annotations

import json
import os
import secrets as pysecrets
from typing import Any

from phonix import config

_KEYS = {
    "ami_internal": lambda: pysecrets.token_urlsafe(24),
    "session_key": lambda: pysecrets.token_urlsafe(48),
}


def load() -> dict[str, Any]:
    path = config.get().secrets_path
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            data = {}
    missing = [k for k in _KEYS if not data.get(k)]
    if missing:
        for key in missing:
            data[key] = _KEYS[key]()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    return data


def get(key: str) -> str:
    return str(load()[key])
