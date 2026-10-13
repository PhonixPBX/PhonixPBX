# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Reports produced by the legacy ``config.xml`` importer and exporter.

The import report is shown after a dry run (so the administrator can decide
whether to commit), stored after the first-boot import and printed by the CLI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

LEVELS = ("info", "warning", "error")
ACTIONS = ("create", "update", "skip")
SECTIONS = (
    "phones",
    "providers",
    "callgroups",
    "rooms",
    "applications",
    "ami_users",
    "settings",
    "users",
)


@dataclass
class ReportItem:
    level: str
    section: str
    name: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "section": self.section,
            "name": self.name,
            "message": self.message,
        }

    def to_text(self) -> str:
        where = f"{self.section}/{self.name}" if self.name else self.section
        return f"[{self.level.upper():7}] {where}: {self.message}"


@dataclass
class _ItemsMixin:
    items: list[ReportItem] = field(default_factory=list)

    def add(self, level: str, section: str, name: str, message: str) -> None:
        assert level in LEVELS, level
        self.items.append(ReportItem(level, section, str(name), message))

    def info(self, section: str, name: str, message: str) -> None:
        self.add("info", section, name, message)

    def warning(self, section: str, name: str, message: str) -> None:
        self.add("warning", section, name, message)

    def error(self, section: str, name: str, message: str) -> None:
        self.add("error", section, name, message)

    @property
    def errors(self) -> list[ReportItem]:
        return [i for i in self.items if i.level == "error"]

    @property
    def warnings(self) -> list[ReportItem]:
        return [i for i in self.items if i.level == "warning"]


@dataclass
class ImportReport(_ItemsMixin):
    """Outcome of a (dry run) import.

    ``ok`` is False only when the import as a whole failed (unreadable or
    hostile XML, unsupported version, aborted transaction). Single objects that
    could not be imported are reported as ``error`` items and counted as
    ``skip`` but do not make the import fail.
    """

    ok: bool = True
    dry_run: bool = False
    mode: str = "replace"
    source_version: str = ""
    counts: dict[str, dict[str, int]] = field(default_factory=lambda: {s: dict.fromkeys(ACTIONS, 0) for s in SECTIONS})
    dropped_sections: list[str] = field(default_factory=list)

    def count(self, section: str, action: str) -> None:
        assert action in ACTIONS, action
        self.counts.setdefault(section, dict.fromkeys(ACTIONS, 0))
        self.counts[section][action] += 1

    def fatal(self, message: str, section: str = "file") -> None:
        self.ok = False
        self.error(section, "", message)

    def drop_section(self, path: str, message: str = "") -> None:
        if path not in self.dropped_sections:
            self.dropped_sections.append(path)
            self.warning("dropped", path, message or "Not supported by PhonixPBX, not imported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "source_version": self.source_version,
            "counts": {k: dict(v) for k, v in self.counts.items()},
            "dropped_sections": list(self.dropped_sections),
            "items": [i.to_dict() for i in self.items],
            "summary": {lvl: sum(1 for i in self.items if i.level == lvl) for lvl in LEVELS},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_text(self) -> str:
        head = "Legacy config.xml import"
        if self.dry_run:
            head += " (dry run, nothing was changed)"
        lines = [
            head,
            f"mode: {self.mode}   source version: {self.source_version or '?'}   "
            f"result: {'OK' if self.ok else 'FAILED'}",
            "",
            f"{'section':<14}{'create':>8}{'update':>8}{'skip':>8}",
        ]
        for section, c in self.counts.items():
            if any(c.values()):
                row = "".join(f"{c.get(action, 0):>8}" for action in ACTIONS)
                lines.append(f"{section:<14}{row}")
        if self.dropped_sections:
            lines += ["", "dropped sections: " + ", ".join(self.dropped_sections)]
        if self.items:
            lines += ["", *[i.to_text() for i in self.items]]
        return "\n".join(lines) + "\n"


@dataclass
class ExportReport(_ItemsMixin):
    """Outcome of an export: what could not be represented in config.xml 2.1."""

    ok: bool = True
    counts: dict[str, int] = field(default_factory=dict)
    # "<object>: <field>" entries for PhonixPBX-only data left out of the file
    omitted: list[str] = field(default_factory=list)

    def omit(self, section: str, name: str, what: str) -> None:
        entry = f"{section}/{name}: {what}" if name else f"{section}: {what}"
        if entry not in self.omitted:
            self.omitted.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "counts": dict(self.counts),
            "omitted": list(self.omitted),
            "items": [i.to_dict() for i in self.items],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_text(self) -> str:
        lines = ["Legacy config.xml export (version 2.1)"]
        exported = ", ".join(f"{n} {k}" for k, n in self.counts.items() if n)
        lines.append(f"exported: {exported or 'nothing'}")
        lines.append("WARNING: the file contains plaintext secrets and passwords - store it safely.")
        if self.items:
            lines += ["", *[i.to_text() for i in self.items]]
        if self.omitted:
            lines += ["", "Not representable in config.xml 2.1 (omitted):"]
            lines += [f"  - {o}" for o in self.omitted]
        return "\n".join(lines) + "\n"
