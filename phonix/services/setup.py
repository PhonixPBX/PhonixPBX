"""Database initialisation and default content for fresh installations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from phonix.core import migrate
from phonix.core.db import session_scope
from phonix.core.models import Application, ConferenceRoom, Phone, Provider
from phonix.services import dialplan


def is_empty(session: Session) -> bool:
    counts = [
        session.scalar(select(func.count()).select_from(model))
        for model in (Phone, Provider, Application, ConferenceRoom)
    ]
    return not any(counts)


def seed_defaults(session: Session) -> bool:
    """Insert the factory default dialplan objects into an empty database."""
    if not is_empty(session):
        return False
    for data in dialplan.DEFAULT_APPLICATIONS:
        dialplan.create_application(session, dialplan.ApplicationIn(**data), user="setup")
    dialplan.create_room(session, dialplan.ConferenceRoomIn(**dialplan.DEFAULT_CONFERENCE), user="setup")
    return True


def initialize() -> None:
    """Migrate the schema and seed defaults (idempotent)."""
    migrate.upgrade()
    with session_scope() as session:
        seed_defaults(session)
