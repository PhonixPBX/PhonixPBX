"""Web UI administrators (argon2id hashed passwords)."""

from __future__ import annotations

import contextlib
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from phonix.core.models import User, utcnow
from phonix.services.common import NotFound, ServiceError, audit, generate_secret

_hasher = PasswordHasher()
_USERNAME = re.compile(r"^[a-z][a-z0-9._-]{0,31}$")
MIN_PASSWORD = 8

# a valid hash used to equalise timing when the user does not exist
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ServiceError(fields={"password": f"Password must have at least {MIN_PASSWORD} characters"})
    if len(password) > 256:
        raise ServiceError(fields={"password": "Password is too long"})


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        with contextlib.suppress(VerificationError):
            _hasher.verify(_DUMMY_HASH, password)
        return None
    try:
        _hasher.verify(user.password_hash, password)
    except (VerificationError, InvalidHashError):
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login = utcnow()
    return user


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User)) or 0


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username)))


def get_by_name(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def create_user(session: Session, username: str, password: str, must_change: bool = False, actor: str = "") -> User:
    username = username.strip().lower()
    if not _USERNAME.match(username):
        raise ServiceError(fields={"username": "Use lowercase letters, digits, '.', '_' or '-'"})
    if get_by_name(session, username):
        raise ServiceError(fields={"username": "User already exists"})
    check_password_policy(password)
    user = User(username=username, password_hash=hash_password(password), must_change_pw=must_change)
    session.add(user)
    session.flush()
    audit(session, actor, "create", "user", user.id, username)
    return user


def set_password(session: Session, username: str, password: str, must_change: bool = False, actor: str = "") -> User:
    user = get_by_name(session, username)
    if user is None:
        raise NotFound("User not found")
    check_password_policy(password)
    user.password_hash = hash_password(password)
    user.must_change_pw = must_change
    audit(session, actor or username, "password", "user", user.id, username)
    return user


def change_own_password(session: Session, user: User, current: str, new: str, confirm: str) -> None:
    try:
        _hasher.verify(user.password_hash, current)
    except (VerificationError, InvalidHashError):
        raise ServiceError(fields={"current": "Current password is wrong"}) from None
    if new != confirm:
        raise ServiceError(fields={"confirm": "Passwords do not match"})
    if new == current:
        raise ServiceError(fields={"password": "Choose a different password"})
    set_password(session, user.username, new, must_change=False, actor=user.username)


def delete_user(session: Session, username: str, actor: str = "") -> None:
    user = get_by_name(session, username)
    if user is None:
        raise NotFound("User not found")
    if count(session) <= 1:
        raise ServiceError("The last administrator cannot be deleted")
    audit(session, actor, "delete", "user", user.id, username)
    session.delete(user)


def ensure_admin(session: Session) -> str | None:
    """Create the initial ``admin`` with a random password; returns it (or None)."""
    if count(session):
        return None
    password = generate_secret(12)
    create_user(session, "admin", password, must_change=True, actor="firstboot")
    return password
