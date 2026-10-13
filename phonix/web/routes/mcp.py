# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""MCP streamable HTTP transport (``/api/mcp``): stateless, JSON responses, no SSE stream."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from phonix import mcp
from phonix.core.models import ApiToken
from phonix.web.deps import get_db, mcp_token

router = APIRouter(prefix="/api", tags=["mcp"])

ALLOW = {"Allow": "POST"}


def _check_headers(request: Request) -> None:
    # DNS rebinding protection: a browser page of another site must not reach us
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "origin not allowed")
    version = request.headers.get("mcp-protocol-version")
    if version and version not in mcp.SUPPORTED_VERSIONS:
        raise HTTPException(400, f"unsupported MCP protocol version {version}")


@router.post("/mcp", summary="Model Context Protocol endpoint (JSON-RPC)")
async def mcp_post(request: Request, token: ApiToken = Depends(mcp_token), db: Session = Depends(get_db)) -> Response:
    _check_headers(request)
    try:
        message = json.loads(await request.body())
    except ValueError:
        return JSONResponse(mcp.error(None, mcp.PARSE_ERROR, "parse error"), status_code=400)
    if isinstance(message, list):
        return JSONResponse(mcp.error(None, mcp.INVALID_REQUEST, "batches are not supported"), status_code=400)
    ctx = mcp.Context(db=db, user=token.user, read_only=token.read_only)
    response = await run_in_threadpool(mcp.handle, message, ctx)
    if response is None:
        return Response(status_code=202)
    return JSONResponse(response)


@router.get("/mcp", include_in_schema=False)
@router.delete("/mcp", include_in_schema=False)
def mcp_other() -> Response:
    # no server initiated SSE stream and no sessions to end
    return Response(status_code=405, headers=ALLOW)
