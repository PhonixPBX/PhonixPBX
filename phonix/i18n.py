"""Translations of the web interface.

Catalogs are ``phonix/locale/<lang>/LC_MESSAGES/messages.po``, read (and
compiled in memory) on first use, so no ``.mo`` build step is needed. The
language of the current request lives in a context variable that the web
middleware sets from the session; everything else (CLI, console, API, tests)
runs in English.

Mark strings with ``_("...")`` (translated now) or ``N_("...")`` (module
level constants, translated where they are displayed). Placeholders use the
named form: ``_("Deleted %(name)s.", name=x)``.
"""

from __future__ import annotations

import gettext as _gettext
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

LOCALE_DIR = Path(__file__).parent / "locale"
DEFAULT = "en"

# web interface languages, in their own language
LANGUAGE_NAMES = {
    "en": "English",
    "en_GB": "English (UK)",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "nl": "Nederlands",
    "da": "Dansk",
    "sv": "Svenska",
    "pl": "Polski",
    "pt_BR": "Português (Brasil)",
    "ru": "Русский",
    "ja": "日本語",
}
# languages without a catalog of their own
FALLBACK = {"en_GB": "en"}

_current: ContextVar[str] = ContextVar("phonix_language", default=DEFAULT)


def normalize(lang: str | None) -> str:
    return lang if lang in LANGUAGE_NAMES else DEFAULT


@cache
def translations(lang: str) -> _gettext.NullTranslations:
    lang = FALLBACK.get(lang, lang)
    path = LOCALE_DIR / lang / "LC_MESSAGES" / "messages.po"
    if lang == DEFAULT or not path.exists():
        return _gettext.NullTranslations()
    with path.open("rb") as fh:
        catalog = read_po(fh, locale=lang)
    buf = BytesIO()
    write_mo(buf, catalog)
    buf.seek(0)
    return _gettext.GNUTranslations(buf)


def get_language() -> str:
    return _current.get()


def set_language(lang: str | None) -> None:
    _current.set(normalize(lang))


@contextmanager
def language(lang: str | None) -> Iterator[None]:
    token = _current.set(normalize(lang))
    try:
        yield
    finally:
        _current.reset(token)


def gettext(message: str, **variables: Any) -> str:
    text = translations(_current.get()).gettext(message)
    return text % variables if variables else text


def ngettext(singular: str, plural: str, n: int, **variables: Any) -> str:
    text = translations(_current.get()).ngettext(singular, plural, n)
    return text % {"num": n, **variables}


def N_(message: str) -> str:
    """Mark a string for extraction; it is translated where it is displayed."""
    return message


_ = gettext
