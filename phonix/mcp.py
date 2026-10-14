# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Model Context Protocol server: JSON-RPC methods and tools on top of the service layer.

Transport independent: ``handle()`` takes one decoded JSON-RPC message and returns
the response (``None`` for notifications). ``phonix.web.routes.mcp`` serves it over
streamable HTTP in stateless, JSON-only mode.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

import phonix
from phonix import config
from phonix.core.models import User
from phonix.services import apply as apply_svc
from phonix.services import settings_api
from phonix.services import status as status_svc
from phonix.services.common import ServiceError, dirty_areas
from phonix.services.resources import RESOURCES, Resource

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
LOG_LINES_MAX = 1000
LOGS = ("asterisk", "system", "web", "monitor")  # keys of RuntimeConfig.log_files

INSTRUCTIONS = (
    "PhonixPBX is an Asterisk based PBX appliance. Changes made with the create_*, update_*, "
    "delete_*, set_*_enabled and update_settings tools are stored but not active until "
    "apply_changes runs; get_pending_changes and preview_apply show what is outstanding. "
    "Secrets are never returned: an empty secret keeps the stored one."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

log = logging.getLogger(__name__)


@dataclass
class Context:
    db: Session
    user: User
    read_only: bool

    @property
    def actor(self) -> str:
        return f"{self.user.username} (mcp)"[:64]


class ToolInputError(Exception):
    """Bad tool arguments: reported to the model as a tool error so it can retry."""


Handler = Callable[[Context, dict[str, Any]], Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Handler
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    write: bool = False
    destructive: bool = False
    idempotent: bool = True
    defs: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": self.properties}
        if self.required:
            schema["required"] = list(self.required)
        if self.defs:
            schema["$defs"] = self.defs
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": schema,
            "annotations": {
                "readOnlyHint": not self.write,
                "destructiveHint": self.destructive,
                "idempotentHint": self.idempotent,
                "openWorldHint": False,
            },
        }


# --- argument helpers -------------------------------------------------------------------------

ID = {"id": {"type": "integer", "description": "Object id as returned by the list tool"}}


def _int(args: dict[str, Any], name: str) -> int:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError(f"'{name}' must be an integer")
    return value


def _str(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str):
        raise ToolInputError(f"'{name}' must be a string")
    return value


def _bool(args: dict[str, Any], name: str) -> bool:
    value = args.get(name)
    if not isinstance(value, bool):
        raise ToolInputError(f"'{name}' must be a boolean")
    return value


def _schema(res: Resource) -> tuple[dict[str, Any], tuple[str, ...], dict[str, Any]]:
    schema = res.schema.model_json_schema()
    return schema.get("properties", {}), tuple(schema.get("required", ())), schema.get("$defs", {})


# --- entity tools -----------------------------------------------------------------------------


def _resource_tools(res: Resource) -> list[Tool]:
    props, required, defs = _schema(res)
    name, tag = res.name, res.tag

    def list_items(ctx: Context, args: dict[str, Any]) -> Any:
        return [res.public(o, ctx.read_only) for o in res.list_fn(ctx.db)]

    def get_item(ctx: Context, args: dict[str, Any]) -> Any:
        return res.public(res.get_fn(ctx.db, _int(args, "id")), ctx.read_only)

    def create_item(ctx: Context, args: dict[str, Any]) -> Any:
        return res.to_dict(res.create_fn(ctx.db, res.parse(args), ctx.actor))

    def update_item(ctx: Context, args: dict[str, Any]) -> Any:
        item_id = _int(args, "id")
        data = res.to_dict(res.get_fn(ctx.db, item_id))
        data.update({k: v for k, v in args.items() if k != "id"})
        return res.to_dict(res.update_fn(ctx.db, item_id, res.parse(data), ctx.actor))

    def delete_item(ctx: Context, args: dict[str, Any]) -> Any:
        res.delete_fn(ctx.db, _int(args, "id"), ctx.actor)
        return {"deleted": True}

    tools = [
        Tool(f"list_{name}s", f"List all {tag}.", list_items),
        Tool(f"get_{name}", f"Get one of the {tag} by id.", get_item, ID, ("id",)),
        Tool(
            f"create_{name}",
            f"Create one of the {tag}. Returns the stored object with its id.",
            create_item,
            props,
            required,
            write=True,
            idempotent=False,
            defs=defs,
        ),
        Tool(
            f"update_{name}",
            f"Change one of the {tag}. Only the given fields change; the others keep their value.",
            update_item,
            {**ID, **props},
            ("id",),
            write=True,
            defs=defs,
        ),
        Tool(f"delete_{name}", f"Delete one of the {tag}.", delete_item, ID, ("id",), write=True, destructive=True),
    ]
    if res.enable_fn is not None:
        enable_fn = res.enable_fn

        def set_enabled(ctx: Context, args: dict[str, Any]) -> Any:
            return res.to_dict(enable_fn(ctx.db, _int(args, "id"), _bool(args, "enabled"), ctx.actor))

        tools.append(
            Tool(
                f"set_{name}_enabled",
                f"Enable or disable one of the {tag}.",
                set_enabled,
                {**ID, "enabled": {"type": "boolean"}},
                ("id", "enabled"),
                write=True,
            )
        )
    return tools


# --- settings, status, apply, logs ------------------------------------------------------------

GROUP = {"group": {"type": "string", "enum": sorted(settings_api.SETTINGS)}}


def _group(args: dict[str, Any]) -> str:
    group = _str(args, "group")
    if group not in settings_api.SETTINGS:
        raise ToolInputError(f"unknown settings group '{group}'")
    return group


def list_settings_groups(ctx: Context, args: dict[str, Any]) -> Any:
    return {"groups": sorted(settings_api.SETTINGS)}


def get_settings(ctx: Context, args: dict[str, Any]) -> Any:
    return settings_api.read_group(ctx.db, _group(args))


def update_settings(ctx: Context, args: dict[str, Any]) -> Any:
    values = args.get("values")
    if not isinstance(values, dict):
        raise ToolInputError("'values' must be an object")
    return settings_api.patch_group(ctx.db, _group(args), values, ctx.actor, via="MCP")


def get_status(ctx: Context, args: dict[str, Any]) -> Any:
    return {"system": status_svc.system_info(), "asterisk": status_svc.asterisk_status()}


def get_pending_changes(ctx: Context, args: dict[str, Any]) -> Any:
    return {"pending": dirty_areas(ctx.db)}


def preview_apply(ctx: Context, args: dict[str, Any]) -> Any:
    # paths only: generated files contain secrets
    files = apply_svc.preview(ctx.db)
    components = {f.component for f in files}
    return {
        "changed_files": [f.path for f in files],
        "components": [c for c in apply_svc.ORDER if c in components],
    }


def apply_changes(ctx: Context, args: dict[str, Any]) -> Any:
    result = apply_svc.apply(ctx.db, user=ctx.actor)
    return {
        "ok": result.ok,
        "changed_files": result.changed_files,
        "components": result.components,
        "actions": result.actions,
        "errors": result.errors,
    }


def tail_log(ctx: Context, args: dict[str, Any]) -> Any:
    files = config.get().log_files
    log = _str(args, "log")
    if log not in LOGS or log not in files:
        raise ToolInputError(f"unknown log '{log}'")
    lines = args.get("lines", 200)
    if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= LOG_LINES_MAX:
        raise ToolInputError(f"'lines' must be an integer from 1 to {LOG_LINES_MAX}")
    path = files[log]
    return {"log": log, "path": str(path), "lines": status_svc.tail(path, lines)}


def _tools() -> dict[str, Tool]:
    tools = [t for res in RESOURCES for t in _resource_tools(res)]
    tools += [
        Tool("list_settings_groups", "List the names of the settings groups.", list_settings_groups),
        Tool("get_settings", "Get one settings group. Secrets are returned empty.", get_settings, GROUP, ("group",)),
        Tool(
            "update_settings",
            "Change fields of one settings group (call get_settings first). Empty secrets keep the stored value.",
            update_settings,
            {**GROUP, "values": {"type": "object", "description": "Fields to change"}},
            ("group", "values"),
            write=True,
        ),
        Tool(
            "get_status",
            "System information and Asterisk status: endpoints, registrations, IAX peers and current calls.",
            get_status,
        ),
        Tool("get_pending_changes", "Areas with stored changes that are not applied yet.", get_pending_changes),
        Tool(
            "preview_apply",
            "Configuration files and components an apply would change, without changing anything.",
            preview_apply,
        ),
        Tool(
            "apply_changes",
            "Generate the configuration and activate it (reloads or restarts Asterisk and system services).",
            apply_changes,
            write=True,
        ),
        Tool(
            "tail_log",
            "The last lines of a log file.",
            tail_log,
            {
                "log": {"type": "string", "enum": list(LOGS)},
                "lines": {"type": "integer", "minimum": 1, "maximum": LOG_LINES_MAX, "default": 200},
            },
            ("log",),
        ),
    ]
    return {t.name: t for t in tools}


_TOOLS: dict[str, Tool] | None = None


def tools() -> dict[str, Tool]:
    global _TOOLS
    if _TOOLS is None:
        _TOOLS = _tools()
    return _TOOLS


# --- JSON-RPC ---------------------------------------------------------------------------------


def error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _content(data: Any, is_error: bool = False) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {"items": data}
    out: dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(data, default=str, ensure_ascii=False)}],
        "structuredContent": json.loads(json.dumps(data, default=str)),
    }
    if is_error:
        out["isError"] = True
    return out


def _call(ctx: Context, params: dict[str, Any], msg_id: Any) -> dict[str, Any]:
    name = params.get("name")
    tool = tools().get(name) if isinstance(name, str) else None
    if tool is None:
        return error(msg_id, INVALID_PARAMS, f"unknown tool: {name}")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        return error(msg_id, INVALID_PARAMS, "arguments must be an object")
    if tool.write and ctx.read_only:
        return _result(msg_id, _content({"error": "token is read-only"}, is_error=True))
    try:
        data = tool.handler(ctx, args)
    except ToolInputError as exc:
        ctx.db.rollback()
        return _result(msg_id, _content({"error": str(exc)}, is_error=True))
    except ServiceError as exc:
        ctx.db.rollback()
        return _result(msg_id, _content({"error": str(exc), "fields": exc.fields}, is_error=True))
    except Exception:
        ctx.db.rollback()
        log.exception("MCP tool %s failed", tool.name)
        return error(msg_id, INTERNAL_ERROR, f"internal error in tool {tool.name}")
    return _result(msg_id, _content(data))


def handle(message: Any, ctx: Context) -> dict[str, Any] | None:
    """Process one JSON-RPC message; ``None`` means no response (notification)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "invalid request")
    method = message["method"]
    if "id" not in message:
        return None  # notifications (initialized, cancelled, ...) need no answer
    msg_id = message["id"]
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error(msg_id, INVALID_PARAMS, "params must be an object")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return _result(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "phonix", "title": "PhonixPBX", "version": phonix.__version__},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        listed = [t.describe() for t in tools().values() if not (t.write and ctx.read_only)]
        return _result(msg_id, {"tools": listed})
    if method == "tools/call":
        return _call(ctx, params, msg_id)
    return error(msg_id, METHOD_NOT_FOUND, f"method not found: {method}")
