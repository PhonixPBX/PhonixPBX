# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import re
import subprocess
import sys
from pathlib import Path

import pytest
from babel.messages.pofile import read_po
from test_web import client, csrf, login  # noqa: F401 - fixture

from phonix import i18n
from phonix.core.db import session_scope
from phonix.services import users
from phonix.web.templating import MENU

ROOT = Path(__file__).resolve().parent.parent
PYBABEL = Path(sys.executable).with_name("pybabel")
CATALOG_LANGUAGES = [lang for lang in i18n.LANGUAGE_NAMES if lang != i18n.DEFAULT and lang not in i18n.FALLBACK]


def _catalog(lang):
    with (i18n.LOCALE_DIR / lang / "LC_MESSAGES" / "messages.po").open("rb") as fh:
        return read_po(fh, locale=lang)


def _pot():
    with (i18n.LOCALE_DIR / "messages.pot").open("rb") as fh:
        return read_po(fh)


@pytest.mark.parametrize("lang", CATALOG_LANGUAGES)
def test_catalog_complete(lang):
    catalog = _catalog(lang)
    template_ids = {m.id for m in _pot() if m.id}
    ids = {m.id for m in catalog if m.id}
    assert template_ids - ids == set(), "run scripts/i18n.sh update"
    missing = [m.id for m in catalog if m.id and (not m.string or (isinstance(m.string, tuple) and not all(m.string)))]
    fuzzy = [m.id for m in catalog if m.id and m.fuzzy]
    assert not missing, f"{len(missing)} untranslated, e.g. {missing[:5]}"
    assert not fuzzy, f"{len(fuzzy)} fuzzy, e.g. {fuzzy[:5]}"
    errors = [(m.id, [str(e) for e in errs]) for m, errs in catalog.check()]
    assert not errors, errors[:5]


@pytest.mark.parametrize("lang", CATALOG_LANGUAGES)
def test_catalog_placeholders(lang):
    """Named placeholders and inline HTML tags of a translation match the source."""
    names = re.compile(r"%\(\w+\)[sdr]")
    tags = re.compile(r"</?(a|b|br|code|em|i|kbd|span|strong)[\s>/]")
    for m in _catalog(lang):
        if not m.id:
            continue
        pairs = zip(m.id, m.string, strict=False) if isinstance(m.id, tuple) else [(m.id, m.string)]
        for source, text in pairs:
            assert sorted(set(names.findall(source))) == sorted(set(names.findall(text))), (lang, source, text)
            assert sorted(tags.findall(source)) == sorted(tags.findall(text)), (lang, source, text)


def test_pot_up_to_date(tmp_path):
    out = tmp_path / "messages.pot"
    subprocess.run(
        [PYBABEL, "-q", "extract", "-F", "babel.cfg", "-k", "N_", "-o", out, "phonix"],
        cwd=ROOT,
        check=True,
    )
    with out.open("rb") as fh:
        fresh = {m.id for m in read_po(fh) if m.id}
    current = {m.id for m in _pot() if m.id}
    new, gone = sorted(fresh - current)[:5], sorted(current - fresh)[:5]
    assert fresh == current, f"run scripts/i18n.sh update: new {new}, gone {gone}"


def test_gettext_follows_context():
    assert i18n.gettext("Phones") == "Phones"
    with i18n.language("de"):
        assert i18n.gettext("Phones") != "Phones"
        assert i18n.get_language() == "de"
    with i18n.language("en_GB"):
        assert i18n.gettext("Phones") == "Phones"
    with i18n.language("xx"):
        assert i18n.get_language() == "en"


def _set_language(lang):
    with session_scope() as s:
        user = users.get_by_name(s, "admin")
        users.set_language(s, user, lang)


def test_preferences_page(client):  # noqa: F811
    login(client)
    page = client.get("/account").text
    assert '<html lang="en">' in page and "Deutsch" in page
    r = client.post("/account", data={"csrf_token": csrf(client, "/account"), "language": "de"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/account").text
    assert '<html lang="de">' in page and "Telefone" in page  # menu in German
    r = client.post("/account", data={"csrf_token": csrf(client, "/account"), "language": "xx"})
    assert r.status_code == 422
    # back to the default
    client.post("/account", data={"csrf_token": csrf(client, "/account"), "language": ""})
    assert '<html lang="en">' in client.get("/account").text


@pytest.mark.parametrize("lang", list(i18n.LANGUAGE_NAMES))
def test_pages_render_in_every_language(client, lang):  # noqa: F811
    _set_language(lang)
    login(client)
    urls = [item.url for section in MENU for item in section.items] + [
        "/account",
        "/password",
        "/accounts/phones/new",
        "/accounts/providers/new",
        "/dialplan/applications/new",
        "/dialplan/callgroups/new",
        "/services/conferencing/new",
        "/advanced/manager/new",
        "/accounts/phones/1",
        "/accounts/providers/1",
    ]
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, (lang, url)
        assert "%(" not in r.text, (lang, url)
        assert f'<html lang="{lang.replace("_", "-")}">' in r.text, (lang, url)
