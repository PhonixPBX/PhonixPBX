# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Import a legacy AskoziaPBX ``config.xml`` into the PhonixPBX database.

Flow: parse (:mod:`.parse`) -> upgrade to 2.1 (:mod:`.upgrade`) -> map every
object (:mod:`.mapping`) -> create/update it through the service layer, so the
validation is exactly the one the web UI applies. Objects that fail are
skipped and reported; the import itself only fails for unreadable files.

Everything happens in one database transaction. A dry run performs the very
same work and rolls it back, so its report (including validation errors and
extension conflicts) is exactly what a real import would do.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from phonix.core import db
from phonix.core import settings as st
from phonix.core import validation as v
from phonix.core.models import (
    AmiUser,
    Application,
    CallGroup,
    CallGroupMember,
    ConferenceRoom,
    Phone,
    PhoneBlockedProvider,
    PhoneProviderCallerId,
    Provider,
    ProviderDialPattern,
    ProviderIncomingRoute,
)
from phonix.legacy import mapping as m
from phonix.legacy import upgrade
from phonix.legacy.parse import MAX_BYTES, LegacyConfig, LegacyParseError, Node, parse_bytes
from phonix.legacy.report import ImportReport
from phonix.services import dialplan as dp
from phonix.services import manager as mgr
from phonix.services import phones as ph
from phonix.services import providers as pv
from phonix.services import users
from phonix.services.common import AREAS, ServiceError, audit, mark_dirty, parse

log = logging.getLogger(__name__)

MODES = ("replace", "merge")
T = TypeVar("T")

# model per reference kind (legacy uniqid lookups in merge mode)
KIND_MODELS: dict[str, Any] = {
    "phone": Phone,
    "provider": Provider,
    "callgroup": CallGroup,
    "application": Application,
    "conference": ConferenceRoom,
}


def import_file(path: Path, mode: str = "replace", user: str = "") -> ImportReport:
    """Import ``path`` (used by first boot and the CLI)."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        report = ImportReport(mode=mode)
        report.fatal(f"Cannot read {path}: {exc.strerror or exc}")
        return report
    if size > MAX_BYTES:
        report = ImportReport(mode=mode)
        report.fatal(f"File is too large ({size} bytes, at most {MAX_BYTES})")
        return report
    return import_bytes(path.read_bytes(), mode=mode, user=user)


def import_bytes(data: bytes, mode: str = "replace", dry_run: bool = False, user: str = "") -> ImportReport:
    """Import (or with ``dry_run`` only validate) the given config.xml content."""
    report = ImportReport(mode=mode, dry_run=dry_run)
    if mode not in MODES:
        report.fatal(f"Unknown import mode {mode!r} (expected replace or merge)")
        return report
    try:
        cfg = parse_bytes(data)
    except LegacyParseError as exc:
        report.fatal(str(exc))
        return report
    report.source_version = cfg.version or "(missing)"
    try:
        upgrade.upgrade(cfg, report)
    except upgrade.UnsupportedVersion as exc:
        report.fatal(str(exc), section="version")
        return report
    upgrade.normalize(cfg, report)

    if mode == "replace" and not dry_run:
        _backup(report)

    session = db.session_factory()()
    try:
        _begin(session)
        LegacyImporter(session, cfg, report, mode, user).run()
        if dry_run:
            session.rollback()
        else:
            mark_dirty(session, *AREAS)
            audit(
                session,
                user,
                "legacy-import",
                "config",
                "",
                f"Imported legacy config.xml {report.source_version} ({mode})",
                {"mode": mode, "counts": report.counts, "dropped": report.dropped_sections},
            )
            session.commit()
    except Exception as exc:
        session.rollback()
        log.exception("legacy import failed")
        report.fatal(f"Import aborted, nothing was changed: {exc}", section="database")
    finally:
        session.close()
    return report


def _begin(session: Session) -> None:
    """Open the transaction before the first SAVEPOINT.

    phonix.core.db emits an explicit BEGIN (pysqlite recipe), so touching the
    connection is enough to make SAVEPOINT/ROLLBACK behave as documented.
    """
    session.connection()


def _backup(report: ImportReport) -> None:
    try:
        from phonix.services import backup  # type: ignore[attr-defined]

        path = backup.create()
        report.info("file", "backup", f"Automatic backup created before replacing: {path}")
    except Exception as exc:
        report.warning(
            "file",
            "backup",
            f"No automatic backup could be created before replacing the configuration ({exc})",
        )


def _service_message(exc: Exception) -> str:
    if isinstance(exc, ServiceError):
        if exc.fields:
            return "; ".join(f"{k}: {v}" for k, v in exc.fields.items())
        return exc.message or str(exc)
    if isinstance(exc, IntegrityError):
        return f"database constraint violated ({exc.orig})"
    return str(exc)


class LegacyImporter:
    """Writes one parsed configuration into ``session``."""

    def __init__(self, session: Session, cfg: LegacyConfig, report: ImportReport, mode: str, user: str) -> None:
        self.session = session
        self.root: Node = cfg.root
        self.report = report
        self.merge = mode == "merge"
        self.user = user or "legacy-import"
        self.ctx = m.Context(report=report, lookup=self._lookup if self.merge else None)
        self.provider_nodes: list[tuple[Node, dict[str, Any], int]] = []

    # --- helpers ------------------------------------------------------------

    def _lookup(self, uniqid: str) -> tuple[str, int] | None:
        for kind, model in KIND_MODELS.items():
            obj = self.session.scalar(select(model).where(model.legacy_uniqid == uniqid))
            if obj is not None:
                return kind, obj.id
        return None

    def _find(self, model: type[T], uniqid: str, natural: Any, value: Any, label: str) -> T | None:
        """Merge mode matching: legacy uniqid first, then the natural key."""
        if not self.merge:
            return None
        if uniqid:
            obj = self.session.scalar(select(model).where(model.legacy_uniqid == uniqid))  # type: ignore[attr-defined]
            if obj is not None:
                return obj
        if value in (None, ""):
            return None
        obj = self.session.scalar(select(model).where(natural == value))
        if obj is None:
            return None
        other = obj.legacy_uniqid  # type: ignore[attr-defined]
        if other and uniqid and other != uniqid:
            raise ServiceError(
                f"Conflict: {label} {value!r} already exists and belongs to another legacy object ({other})"
            )
        return obj

    def _upsert(
        self,
        section: str,
        name: str,
        uniqid: str,
        find: Callable[[], Any],
        create: Callable[[], Any],
        update: Callable[[Any], Any],
    ) -> Any:
        """Create or update one object inside a savepoint; failures are skipped."""
        action = "create"
        try:
            with self.session.begin_nested():
                existing = find()
                if existing is not None:
                    obj = update(existing)
                    action = "update"
                else:
                    obj = create()
                if uniqid:
                    obj.legacy_uniqid = uniqid
                self.session.flush()
        except (ServiceError, IntegrityError) as exc:
            self.report.error(section, name, f"Skipped: {_service_message(exc)}")
            self.report.count(section, "skip")
            return None
        self.report.count(section, action)
        return obj

    def _seen(self, section: str, name: str, uniqid: str) -> bool:
        if uniqid and uniqid in self.ctx.refs:
            self.report.error(section, name, f"Duplicate uniqid {uniqid!r}: skipped")
            self.report.count(section, "skip")
            return True
        return False

    # --- steps --------------------------------------------------------------------

    def run(self) -> None:
        self._dropped_sections()
        if self.merge:
            self.report.info(
                "settings",
                "",
                "Merge mode: global settings and the web admin password are not changed",
            )
        else:
            self._wipe()
            self._settings()
            self._admin()
        self._providers()
        self._phones()
        self._rooms()
        self._applications()
        self._callgroups()
        self._provider_routes()
        self._ami_users()

    def _dropped_sections(self) -> None:
        root = self.root
        for key in root:
            if key in m.DROPPED_SECTIONS:
                self.report.drop_section(key, f"{m.DROPPED_SECTIONS[key]} - not imported")
                self._collect_dropped(key, root.node(key))
            elif key not in m.KNOWN_SECTIONS:
                self.report.drop_section(key, "Unknown section, not imported")
        system = root.node("system")
        for key in ("shellcmd", "earlyshellcmd"):
            if system.texts(key):
                self.report.drop_section(f"system/{key}", "Boot shell commands are not imported (security)")
        if system.has("regional"):
            self.report.drop_section("system/regional", "Regional analog (DAHDI) settings")
        interfaces = root.node("interfaces")
        for key in interfaces:
            if key != "lan":
                self.report.drop_section(f"interfaces/{key}", "Telephony hardware / additional interfaces not imported")
        for key in root.node("services"):
            if key not in ("sip", "iax", "rtp", "manager"):
                self.report.drop_section(f"services/{key}", "Not supported by PhonixPBX, not imported")

    def _collect_dropped(self, section: str, node: Node) -> None:
        """Remember objects of telephony hardware sections others may reference."""
        tech = {"isdn": "ISDN", "analog": "analog", "skinny": "Skinny", "virtual": "virtual"}
        if section not in tech:
            return
        hint = "; consider a SIP gateway" if section in ("isdn", "analog") else ""
        for key, value in node.items():
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                if isinstance(entry, dict) and entry.get("uniqid"):
                    item = Node(entry)
                    label = item.text("name") or item.text("callerid") or item.text("extension")
                    desc = f"{tech[section]} {key} {label!r}"
                    self.ctx.dropped[item.text("uniqid")] = desc
                    self.report.warning(
                        "dropped",
                        f"{section}/{key}",
                        f"{desc} not imported (not supported by PhonixPBX){hint}",
                    )

    def _wipe(self) -> None:
        counts = {
            "phones": self.session.query(Phone).count(),
            "providers": self.session.query(Provider).count(),
            "call groups": self.session.query(CallGroup).count(),
            "conference rooms": self.session.query(ConferenceRoom).count(),
            "applications": self.session.query(Application).count(),
            "manager users": self.session.query(AmiUser).count(),
        }
        for model in (
            CallGroupMember,
            CallGroup,
            ProviderIncomingRoute,
            ProviderDialPattern,
            PhoneProviderCallerId,
            PhoneBlockedProvider,
            Phone,
            ConferenceRoom,
            Application,
            AmiUser,
        ):
            self.session.execute(delete(model))
        self.session.execute(
            Provider.__table__.update().values(failover_provider_id=None)  # type: ignore[attr-defined]
        )
        self.session.execute(delete(Provider))
        self.session.expire_all()
        removed = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
        self.report.info("file", "replace", f"Replace mode: existing objects removed ({removed or 'none'})")

    def _settings(self) -> None:
        current = st.load_all(self.session)
        for group in m.settings_in(self.root, current, self.report):
            st.save(self.session, group)
            self.report.count("settings", "update")

    def _admin(self) -> None:
        sysn = self.root.node("system")
        password = sysn.text("password")
        username = (sysn.text("username") or "admin").lower()
        if not password:
            return
        if len(password) < users.MIN_PASSWORD:
            self.report.warning(
                "users",
                username,
                f"The legacy web password is shorter than {users.MIN_PASSWORD} characters and "
                "was not imported; the current PhonixPBX password stays in effect",
            )
            self.report.count("users", "skip")
            return
        try:
            with self.session.begin_nested():
                if users.get_by_name(self.session, username):
                    users.set_password(self.session, username, password, must_change=False, actor=self.user)
                    action = "update"
                else:
                    users.create_user(self.session, username, password, must_change=False, actor=self.user)
                    action = "create"
        except ServiceError as exc:
            self.report.error("users", username, f"Web user not imported: {_service_message(exc)}")
            self.report.count("users", "skip")
            return
        self.report.count("users", action)
        self.report.warning(
            "users",
            username,
            "The web login password was set to the legacy password (now stored as an argon2 "
            "hash). It was stored in plaintext before - consider changing it.",
        )

    def _providers(self) -> None:
        for tech in ("sip", "iax"):
            for node in self.root.node(tech).nodes("provider"):
                uniqid = node.text("uniqid")
                name = m.provider_label(node)
                if self._seen("providers", name, uniqid):
                    continue
                data = m.provider_in(node, tech, self.ctx)
                provider_tech = data["tech"]

                def find(uniqid: str = uniqid, name: str = name, tech: str = provider_tech) -> Any:
                    obj = self._find(Provider, uniqid, Provider.name, name, "Provider")
                    if obj is not None and obj.tech != tech:
                        raise ServiceError(f"Conflict: provider {name!r} exists with another type")
                    return obj

                def create(data: dict[str, Any] = data, name: str = name) -> Provider:
                    self._free_patterns(data, None, name)
                    return pv.create_provider(self.session, pv.parse_provider(data), self.user)

                def update(obj: Provider, data: dict[str, Any] = data, name: str = name) -> Provider:
                    self._free_patterns(data, obj.id, name)
                    return pv.update_provider(self.session, obj.id, pv.parse_provider(data), self.user)

                obj = self._upsert("providers", name, uniqid, find, create, update)
                if obj is not None:
                    if uniqid:
                        self.ctx.refs[uniqid] = ("provider", obj.id)
                    self.provider_nodes.append((node, data, obj.id))

    def _free_patterns(self, data: dict[str, Any], own_id: int | None, name: str) -> None:
        """Drop dial patterns another provider already uses (legacy pbx_dialpattern_exists)."""
        kept = []
        for pattern in data.get("dialpatterns", []):
            try:
                pattern = v.dialpattern(pattern)
            except ValueError:
                kept.append(pattern)  # reported by the schema validation
                continue
            stmt = select(ProviderDialPattern).where(ProviderDialPattern.pattern == pattern)
            other = next((p for p in self.session.scalars(stmt) if p.provider_id != own_id), None)
            if other is not None:
                owner = self.session.get(Provider, other.provider_id)
                self.report.warning(
                    "providers",
                    name,
                    f"Dial pattern {pattern} dropped: already used by provider "
                    f"{owner.name if owner else other.provider_id}",
                )
                continue
            kept.append(pattern)
        data["dialpatterns"] = kept

    def _phones(self) -> None:
        for tech in ("sip", "iax", "external"):
            for node in self.root.node(tech).nodes("phone"):
                uniqid = node.text("uniqid")
                name = m.phone_label(node)
                if self._seen("phones", name, uniqid):
                    continue
                data = m.phone_in(node, tech, self.ctx)
                if data is None:
                    self.report.count("phones", "skip")
                    continue

                def find(uniqid: str = uniqid, data: dict[str, Any] = data) -> Any:
                    return self._find(Phone, uniqid, Phone.extension, data["extension"], "Extension")

                def create(data: dict[str, Any] = data) -> Phone:
                    return ph.create_phone(self.session, ph.parse_phone(data), self.user)

                def update(obj: Phone, data: dict[str, Any] = data) -> Phone:
                    return ph.update_phone(self.session, obj.id, ph.parse_phone(data), self.user)

                obj = self._upsert("phones", name, uniqid, find, create, update)
                if obj is not None and uniqid:
                    self.ctx.refs[uniqid] = ("phone", obj.id)

    def _rooms(self) -> None:
        for node in self.root.node("conferencing").nodes("room"):
            uniqid = node.text("uniqid")
            data = m.room_in(node, self.ctx)
            name = data["name"] or "?"
            if self._seen("rooms", name, uniqid):
                continue

            def find(uniqid: str = uniqid, data: dict[str, Any] = data) -> Any:
                return self._find(ConferenceRoom, uniqid, ConferenceRoom.number, data["number"], "Room number")

            def create(data: dict[str, Any] = data) -> ConferenceRoom:
                return dp.create_room(self.session, _parse(dp.ConferenceRoomIn, data), self.user)

            def update(obj: ConferenceRoom, data: dict[str, Any] = data) -> ConferenceRoom:
                return dp.update_room(self.session, obj.id, _parse(dp.ConferenceRoomIn, data), self.user)

            obj = self._upsert("rooms", name, uniqid, find, create, update)
            if obj is not None and uniqid:
                self.ctx.refs[uniqid] = ("conference", obj.id)

    def _applications(self) -> None:
        for node in self.root.node("dialplan").nodes("application"):
            uniqid = node.text("uniqid")
            name = node.text("name") or node.text("extension") or "?"
            if self._seen("applications", name, uniqid):
                continue
            data, builtin = m.application_in(node, self.ctx)
            if data is None:
                self.report.count("applications", "skip")
                continue

            def find(uniqid: str = uniqid, data: dict[str, Any] = data) -> Any:
                return self._find(Application, uniqid, Application.extension, data["extension"], "Extension")

            def create(data: dict[str, Any] = data) -> Application:
                return dp.create_application(self.session, _parse(dp.ApplicationIn, data), self.user)

            def update(obj: Application, data: dict[str, Any] = data, builtin: bool = builtin) -> Application:
                if builtin and m.is_default_application(obj.extension, obj.logic):
                    # the existing PhonixPBX built-in stays as it is, it only gets the uniqid
                    obj.enabled = data["enabled"]
                    return obj
                return dp.update_application(self.session, obj.id, _parse(dp.ApplicationIn, data), self.user)

            obj = self._upsert("applications", name, uniqid, find, create, update)
            if obj is not None and uniqid:
                self.ctx.refs[uniqid] = ("application", obj.id)

    def _callgroups(self) -> None:
        for node in self.root.node("dialplan").nodes("callgroup"):
            uniqid = node.text("uniqid")
            name = node.text("name") or node.text("extension") or "?"
            if self._seen("callgroups", name, uniqid):
                continue
            data = m.callgroup_in(node, self.ctx)
            if data is None:
                self.report.count("callgroups", "skip")
                continue

            def find(uniqid: str = uniqid, data: dict[str, Any] = data) -> Any:
                if data["extension"]:
                    return self._find(CallGroup, uniqid, CallGroup.extension, data["extension"], "Extension")
                return self._find(CallGroup, uniqid, CallGroup.name, data["name"], "Call group")

            def create(data: dict[str, Any] = data) -> CallGroup:
                return dp.create_callgroup(self.session, _parse(dp.CallGroupIn, data), self.user)

            def update(obj: CallGroup, data: dict[str, Any] = data) -> CallGroup:
                return dp.update_callgroup(self.session, obj.id, _parse(dp.CallGroupIn, data), self.user)

            obj = self._upsert("callgroups", name, uniqid, find, create, update)
            if obj is not None and uniqid:
                self.ctx.refs[uniqid] = ("callgroup", obj.id)

    def _provider_routes(self) -> None:
        """Second provider pass: incoming routes and failover need all objects."""
        for node, data, provider_id in self.provider_nodes:
            name = m.provider_label(node)
            routes = m.incoming_routes_in(node, self.ctx)
            failover_id = None
            failover = node.text("failover")
            if failover:
                ref = self.ctx.resolve(failover)
                if ref and ref[0] == "provider" and ref[1] != provider_id:
                    failover_id = ref[1]
                elif failover in self.ctx.dropped:
                    self.report.warning("providers", name, f"Failover to {self.ctx.dropped[failover]} dropped")
                else:
                    self.report.warning("providers", name, f"Unknown failover provider {failover!r}")
            if not routes and failover_id is None:
                continue
            full = {**data, "incoming_routes": routes, "failover_provider_id": failover_id}
            try:
                with self.session.begin_nested():
                    pv.update_provider(self.session, provider_id, pv.parse_provider(full), self.user)
            except (ServiceError, IntegrityError) as exc:
                self.report.error(
                    "providers",
                    name,
                    f"Incoming routes / failover not imported: {_service_message(exc)}",
                )

    def _ami_users(self) -> None:
        for node in self.root.node("services", "manager").nodes("manager-user"):
            data = m.ami_user_in(node, self.ctx)
            name = data["username"] or "?"

            def find(data: dict[str, Any] = data) -> Any:
                if not self.merge:
                    return None
                return self.session.scalar(select(AmiUser).where(AmiUser.username == data["username"]))

            def create(data: dict[str, Any] = data) -> AmiUser:
                return mgr.create_ami_user(self.session, _parse(mgr.AmiUserIn, data), self.user)

            def update(obj: AmiUser, data: dict[str, Any] = data) -> AmiUser:
                return mgr.update_ami_user(self.session, obj.id, _parse(mgr.AmiUserIn, data), self.user)

            self._upsert("ami_users", name, "", find, create, update)


def _parse(model: type[T], data: dict[str, Any]) -> T:
    result: T = parse(model, data)  # type: ignore[arg-type]
    return result
