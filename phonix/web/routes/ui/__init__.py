"""HTML user interface routes."""

from fastapi import APIRouter

from phonix.web.routes.ui import accounts, advanced, apply, auth, dialplan, services, status, system

router = APIRouter(include_in_schema=False)
for module in (auth, apply, status, accounts, dialplan, services, system, advanced):
    router.include_router(module.router)
