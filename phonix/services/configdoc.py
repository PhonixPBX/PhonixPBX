# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""The whole configuration as one versioned JSON document (``config.json``).

This is the payload of backups and of ``phonix config export/import``. The
document does not depend on the database schema:

- ``export`` renders it through the service layer.
- ``import_document`` replaces the configuration with it in the caller's
  transaction, creating every object through the same service functions as
  the UI. The first error aborts the whole import.

Objects carry document-local ``id`` values that references (``dial_provider_id``,
``member_ids``, ``incoming_routes[].dest_id``, ...) point to; they are remapped
to new database ids on import. The field names are the ones of the REST API.

``CONFIG_VERSION`` is bumped whenever the document changes incompatibly (the
schema in ``docs/config-schema.json`` is checked by the tests). Older documents
are upgraded step by step with ``UPGRADES`` before they are validated; newer
ones are refused.
"""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import types
from collections.abc import Callable, Collection, Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, create_model, field_validator
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from phonix import __version__, config, i18n
from phonix.core import settings as st
from phonix.core.models import (
    AmiUser,
    ApiToken,
    Application,
    CallGroup,
    CallGroupMember,
    ConferenceRoom,
    MediaFile,
    Phone,
    PhoneBlockedProvider,
    PhoneProviderCallerId,
    Provider,
    ProviderDialPattern,
    ProviderIncomingRoute,
    User,
)
from phonix.i18n import _
from phonix.services import dialplan as dp
from phonix.services import manager as mgr
from phonix.services import phones as ph
from phonix.services import providers as pv
from phonix.services import users as users_svc
from phonix.services.common import AREAS, ServiceError, errors_from_validation, mark_dirty, parse

FORMAT = "phonix-config"
CONFIG_VERSION = 1
# version n -> n + 1, applied to the plain dict before validation
UPGRADES: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}

_FORBID = ConfigDict(extra="forbid")


# --- document model -------------------------------------------------------------------


class PhoneDoc(ph.PhoneIn):
    model_config = _FORBID
    id: int
    legacy_uniqid: str | None = None


class ProviderDoc(pv.ProviderIn):
    model_config = _FORBID
    id: int
    legacy_uniqid: str | None = None


class CallGroupDoc(dp.CallGroupIn):
    model_config = _FORBID
    id: int
    legacy_uniqid: str | None = None


class ConferenceRoomDoc(dp.ConferenceRoomIn):
    model_config = _FORBID
    id: int
    legacy_uniqid: str | None = None


class ApplicationDoc(dp.ApplicationIn):
    model_config = _FORBID
    id: int
    legacy_uniqid: str | None = None


class AmiUserDoc(mgr.AmiUserIn):
    model_config = _FORBID
    legacy_uniqid: str | None = None


class TokenDoc(BaseModel):
    model_config = _FORBID
    name: str = Field(min_length=1, max_length=64)
    # sha256 of the token; the token itself is never stored
    token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prefix: str = Field(max_length=16)
    read_only: bool = True
    enabled: bool = True
    created_at: dt.datetime | None = None
    expires_at: dt.datetime | None = None
    last_used_at: dt.datetime | None = None


class UserDoc(BaseModel):
    model_config = _FORBID
    username: str = Field(pattern=users_svc._USERNAME.pattern)
    # argon2id hash
    password_hash: str = Field(pattern=r"^\$argon2", max_length=255)
    role: str = Field(default="admin", max_length=16)
    must_change_pw: bool = False
    language: str | None = None
    created_at: dt.datetime | None = None
    last_login: dt.datetime | None = None
    tokens: list[TokenDoc] = Field(default_factory=list)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        if value and value not in i18n.LANGUAGE_NAMES:
            raise ValueError(_("Unknown language"))
        return value or None


class MediaDoc(BaseModel):
    model_config = _FORBID
    kind: Literal["moh", "vm_greeting"]
    name: str = Field(max_length=128)
    # below the media directory: <kind>/<file>
    path: str = Field(pattern=r"^[a-z_]+/[A-Za-z0-9_-]+\.wav$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _path(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("kind") and not value.startswith(f"{info.data['kind']}/"):
            raise ValueError(_("Invalid value"))
        return value


def _strict_settings(model: type[st.SettingsGroup]) -> type[st.SettingsGroup]:
    """``model`` refusing unknown keys, without the internal ``group`` field in the schema."""

    def body(ns: dict[str, Any]) -> None:
        ns["__module__"] = __name__
        ns["__annotations__"] = {"group": SkipJsonSchema[str]}
        ns["model_config"] = _FORBID
        ns["group"] = Field(default=st.group_name(model), exclude=True)

    return types.new_class(model.__name__.replace("Settings", "SettingsDoc"), (model,), {}, body)


SETTINGS_DOCS: dict[str, type[st.SettingsGroup]] = {st.group_name(m): _strict_settings(m) for m in st.ALL_GROUPS}

# groups that are missing in a document get their defaults
SettingsDoc = create_model(  # type: ignore[call-overload]
    "SettingsDoc",
    __config__=_FORBID,
    **{name: (model | None, None) for name, model in SETTINGS_DOCS.items()},
)


class ConfigDocument(BaseModel):
    model_config = _FORBID
    format: Literal["phonix-config"]
    version: int
    phonix_version: str = ""
    created: dt.datetime | None = None
    settings: SettingsDoc = Field(default_factory=SettingsDoc)  # type: ignore[valid-type]
    users: list[UserDoc] = Field(min_length=1)
    providers: list[ProviderDoc] = Field(default_factory=list)
    phones: list[PhoneDoc] = Field(default_factory=list)
    callgroups: list[CallGroupDoc] = Field(default_factory=list)
    conferences: list[ConferenceRoomDoc] = Field(default_factory=list)
    applications: list[ApplicationDoc] = Field(default_factory=list)
    ami_users: list[AmiUserDoc] = Field(default_factory=list)
    media: list[MediaDoc] = Field(default_factory=list)


def json_schema() -> dict[str, Any]:
    schema = ConfigDocument.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = f"PhonixPBX configuration, version {CONFIG_VERSION}"
    return schema


# --- export ---------------------------------------------------------------------------


def _ts(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(session: Session) -> dict[str, Any]:
    """The current configuration as a plain JSON-able dict (secrets included)."""
    session.expire_all()

    def entity(data: dict[str, Any], obj: Any) -> dict[str, Any]:
        data["legacy_uniqid"] = obj.legacy_uniqid
        return data

    users = []
    for user in session.scalars(select(User).order_by(User.username)):
        tokens = [
            {
                "name": t.name,
                "token_hash": t.token_hash,
                "prefix": t.prefix,
                "read_only": t.read_only,
                "enabled": t.enabled,
                "created_at": _ts(t.created_at),
                "expires_at": _ts(t.expires_at),
                "last_used_at": _ts(t.last_used_at),
            }
            for t in sorted(user.api_tokens, key=lambda t: t.id)
        ]
        users.append(
            {
                "username": user.username,
                "password_hash": user.password_hash,
                "role": user.role,
                "must_change_pw": user.must_change_pw,
                "language": user.language,
                "created_at": _ts(user.created_at),
                "last_login": _ts(user.last_login),
                "tokens": tokens,
            }
        )

    ami_users = []
    for u in session.scalars(select(AmiUser).order_by(AmiUser.username)):
        data = mgr.to_dict(u)
        del data["id"]
        data["secret"] = u.secret
        ami_users.append(entity(data, u))

    media_dir = config.get().media_dir
    media = []
    for m in session.scalars(select(MediaFile).order_by(MediaFile.path)):
        path = media_dir / m.path
        if not path.is_file():
            continue  # a row without its file cannot be restored
        media.append(
            {"kind": m.kind, "name": m.name, "path": m.path, "size": path.stat().st_size, "sha256": sha256_file(path)}
        )

    return {
        "format": FORMAT,
        "version": CONFIG_VERSION,
        "phonix_version": __version__,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "settings": {name: group.model_dump(mode="json") for name, group in sorted(st.load_all(session).items())},
        "users": users,
        "providers": [
            entity(pv.to_dict(p, with_secret=True), p)
            for p in session.scalars(select(Provider).order_by(Provider.tech, Provider.name, Provider.id))
        ],
        "phones": [
            entity(ph.to_dict(p, with_secret=True), p) for p in session.scalars(select(Phone).order_by(Phone.extension))
        ],
        "callgroups": [
            entity(dp.callgroup_to_dict(g), g)
            for g in session.scalars(select(CallGroup).order_by(CallGroup.name, CallGroup.id))
        ],
        "conferences": [entity(dp.room_to_dict(r), r) for r in dp.list_rooms(session)],
        "applications": [entity(dp.application_to_dict(a), a) for a in dp.list_applications(session)],
        "ami_users": ami_users,
        "media": media,
    }


# --- parse ----------------------------------------------------------------------------


def _format_errors(exc: ValidationError, limit: int = 5) -> str:
    errors = [f"{loc}: {msg}" for loc, msg in errors_from_validation(exc).items()]
    more = len(errors) - limit
    return "; ".join(errors[:limit]) + (f" (+{more})" if more > 0 else "")


def parse_document(data: Any) -> ConfigDocument:
    """Upgrade and validate a decoded ``config.json``."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ServiceError(_("This is not a PhonixPBX configuration file"))
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise ServiceError(_("Unknown configuration version %(version)s", version=version))
    if version > CONFIG_VERSION:
        raise ServiceError(
            _(
                "The configuration was created by PhonixPBX %(release)s and is newer than this system "
                "supports. Update this system first.",
                release=data.get("phonix_version") or "?",
            )
        )
    data = copy.deepcopy(data)
    while version < CONFIG_VERSION:
        data = UPGRADES[version](data)
        version += 1
        data["version"] = version
    try:
        return ConfigDocument.model_validate(data)
    except ValidationError as exc:
        raise ServiceError(_("The configuration is invalid: %(errors)s", errors=_format_errors(exc))) from exc


# --- import ---------------------------------------------------------------------------


def delete_pbx_objects(session: Session) -> None:
    """Remove phones, providers, call groups, rooms, applications and manager users."""
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
        session.execute(delete(model))
    session.execute(
        Provider.__table__.update().values(failover_provider_id=None)  # type: ignore[attr-defined]
    )
    session.execute(delete(Provider))
    session.expire_all()


def check_media(doc: ConfigDocument, media_root: Path) -> None:
    """Every media entry needs its file below ``media_root`` with the recorded checksum."""
    for m in doc.media:
        path = media_root / m.path
        if not path.is_file() or sha256_file(path) != m.sha256:
            raise ServiceError(_("The media file %(path)s is missing or damaged", path=m.path))


# parts of the current configuration a restore can keep instead of taking them from the document
KEEP_PARTS = ("network", "users", "certificate")
# settings groups each part keeps (the certificate files themselves are handled by the backup)
KEEP_GROUPS = {"network": ("network", "firewall"), "certificate": ("acme",)}
# SSH access belongs to the "network" part, but lives in the system group
KEEP_SYSTEM_FIELDS = ("ssh_enabled", "ssh_password_hash")


class _Importer:
    def __init__(self, session: Session, doc: ConfigDocument, user: str, keep: Collection[str] = ()) -> None:
        unknown = set(keep) - set(KEEP_PARTS)
        if unknown:
            raise ValueError(f"unknown parts to keep: {sorted(unknown)}")
        self.session = session
        self.doc = doc
        self.user = user
        self.keep = frozenset(keep)
        # document id -> database id, per object type
        kinds = ("provider", "phone", "callgroup", "conference", "application")
        self.ids: dict[str, dict[int, int]] = {kind: {} for kind in kinds}
        self.counts: dict[str, int] = {}

    def ref(self, kind: str, doc_id: int, where: str) -> int:
        try:
            return self.ids[kind][doc_id]
        except KeyError:
            raise ServiceError(
                _("%(object)s: reference to unknown %(type)s %(id)s", object=where, type=kind, id=doc_id)
            ) from None

    @contextlib.contextmanager
    def step(self, where: str) -> Iterator[None]:
        """Name the object in service errors raised inside the block."""
        try:
            yield
        except ServiceError as exc:
            detail = "; ".join(f"{k}: {v}" for k, v in exc.fields.items()) or exc.message or str(exc)
            raise ServiceError(_("%(object)s: %(error)s", object=where, error=detail)) from exc

    def remember(self, kind: str, doc_id: int, obj: Any, uniqid: str | None) -> None:
        if doc_id in self.ids[kind]:
            raise ServiceError(_("Duplicate %(type)s id %(id)s", type=kind, id=doc_id))
        self.ids[kind][doc_id] = obj.id
        obj.legacy_uniqid = uniqid or None

    def run(self) -> dict[str, int]:
        session, doc, user = self.session, self.doc, self.user
        delete_pbx_objects(session)
        session.execute(delete(MediaFile))
        if "users" not in self.keep:
            session.execute(delete(ApiToken))
            session.execute(delete(User))
        session.flush()
        self.settings()
        if "users" not in self.keep:
            self.users()
        # providers first without routes and failover: those may point to anything
        for p in doc.providers:
            data = p.model_dump(exclude={"id", "legacy_uniqid"})
            data.update(incoming_routes=[], failover_provider_id=None)
            with self.step(f"providers/{p.name}"):
                provider = pv.create_provider(session, pv.parse_provider(data), user)
            self.remember("provider", p.id, provider, p.legacy_uniqid)
        for phone in doc.phones:
            where = f"phones/{phone.extension}"
            data = phone.model_dump(exclude={"id", "legacy_uniqid"})
            if phone.dial_provider_id is not None:
                data["dial_provider_id"] = self.ref("provider", phone.dial_provider_id, where)
            data["blocked_provider_ids"] = [self.ref("provider", i, where) for i in phone.blocked_provider_ids]
            data["provider_callerids"] = {
                self.ref("provider", i, where): cid for i, cid in phone.provider_callerids.items()
            }
            with self.step(where):
                obj = ph.create_phone(session, ph.parse_phone(data), user)
            self.remember("phone", phone.id, obj, phone.legacy_uniqid)
        for room in doc.conferences:
            data = room.model_dump(exclude={"id", "legacy_uniqid"})
            with self.step(f"conferences/{room.number}"):
                conf = dp.create_room(session, parse(dp.ConferenceRoomIn, data), user)
            self.remember("conference", room.id, conf, room.legacy_uniqid)
        for app in doc.applications:
            data = app.model_dump(exclude={"id", "legacy_uniqid"})
            with self.step(f"applications/{app.extension}"):
                application = dp.create_application(session, parse(dp.ApplicationIn, data), user)
            self.remember("application", app.id, application, app.legacy_uniqid)
        for group in doc.callgroups:
            where = f"callgroups/{group.name}"
            data = group.model_dump(exclude={"id", "legacy_uniqid"})
            data["member_ids"] = [self.ref("phone", i, where) for i in group.member_ids]
            with self.step(where):
                callgroup = dp.create_callgroup(session, parse(dp.CallGroupIn, data), user)
            self.remember("callgroup", group.id, callgroup, group.legacy_uniqid)
        for p in doc.providers:
            if not p.incoming_routes and p.failover_provider_id is None:
                continue
            where = f"providers/{p.name}"
            data = p.model_dump(exclude={"id", "legacy_uniqid"})
            data["incoming_routes"] = [
                {**r.model_dump(), "dest_id": self.ref(r.dest_type, r.dest_id, where)} for r in p.incoming_routes
            ]
            if p.failover_provider_id is not None:
                data["failover_provider_id"] = self.ref("provider", p.failover_provider_id, where)
            with self.step(where):
                pv.update_provider(session, self.ids["provider"][p.id], pv.parse_provider(data), user)
        for u in doc.ami_users:
            with self.step(f"ami_users/{u.username}"):
                ami = mgr.create_ami_user(session, parse(mgr.AmiUserIn, u.model_dump(exclude={"legacy_uniqid"})), user)
            ami.legacy_uniqid = u.legacy_uniqid or None
        for m in doc.media:
            session.add(MediaFile(kind=m.kind, name=m.name, path=m.path, size=m.size))
        session.flush()
        mark_dirty(session, *AREAS)
        self.counts = {
            "settings": sum(getattr(doc.settings, name) is not None for name in SETTINGS_DOCS),
            "users": len(doc.users),
            "api_tokens": sum(len(u.tokens) for u in doc.users),
            "providers": len(doc.providers),
            "phones": len(doc.phones),
            "callgroups": len(doc.callgroups),
            "conferences": len(doc.conferences),
            "applications": len(doc.applications),
            "ami_users": len(doc.ami_users),
            "media": len(doc.media),
        }
        return self.counts

    def settings(self) -> None:
        # a group missing from the document (hand-written, or older than the group) keeps its
        # current values: a config.json without "network" must not reset the LAN address
        kept = {group for part in self.keep for group in KEEP_GROUPS.get(part, ())}
        for model in st.ALL_GROUPS:
            name = st.group_name(model)
            value = getattr(self.doc.settings, name)
            if value is None or name in kept:
                continue
            data = value.model_dump()
            if model is st.SystemSettings and "network" in self.keep:
                current = st.load(self.session, st.SystemSettings)
                data.update({f: getattr(current, f) for f in KEEP_SYSTEM_FIELDS})
            st.save(self.session, model.model_validate(data))

    def users(self) -> None:
        seen: set[str] = set()
        for u in self.doc.users:
            if u.username in seen:
                raise ServiceError(_("Duplicate user %(name)s", name=u.username))
            seen.add(u.username)
            user = User(
                username=u.username,
                password_hash=u.password_hash,
                role=u.role,
                must_change_pw=u.must_change_pw,
                language=u.language,
            )
            if u.created_at:
                user.created_at = _naive_utc(u.created_at)
            if u.last_login:
                user.last_login = _naive_utc(u.last_login)
            for t in u.tokens:
                token = ApiToken(
                    name=t.name,
                    token_hash=t.token_hash,
                    prefix=t.prefix,
                    read_only=t.read_only,
                    enabled=t.enabled,
                    expires_at=_naive_utc(t.expires_at) if t.expires_at else None,
                )
                if t.created_at:
                    token.created_at = _naive_utc(t.created_at)
                if t.last_used_at:
                    token.last_used_at = _naive_utc(t.last_used_at)
                user.api_tokens.append(token)
            self.session.add(user)
        self.session.flush()


def _naive_utc(value: dt.datetime) -> dt.datetime:
    """The database stores naive UTC timestamps."""
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def import_document(
    session: Session, doc: ConfigDocument, media_root: Path, user: str = "", keep: Collection[str] = ()
) -> dict[str, int]:
    """Replace the whole configuration with ``doc``; returns object counts.

    ``keep`` names parts of the current configuration (``KEEP_PARTS``) that stay
    as they are. Runs in the caller's transaction and does not commit. Media rows
    are created for the files below ``media_root`` (checked, not copied).
    """
    check_media(doc, media_root)
    return _Importer(session, doc, user or "restore", keep).run()
