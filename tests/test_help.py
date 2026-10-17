# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""User manual (docs/manual -> phonix/web/static/help) and the help buttons linking into it."""

import re
from pathlib import Path

import pytest
from test_web import client, csrf, login  # noqa: F401  (fixture)

from phonix import i18n
from phonix.web.templating import HELP_LANGUAGES, MENU, STATIC_DIR, TEMPLATES_DIR, help_url

HELP_DIR = STATIC_DIR / "help"
MANUAL_LANGUAGES = ("en", *HELP_LANGUAGES)


def _built(url: str) -> Path:
    """The built HTML file for a /help/ URL (without anchor)."""
    path = url.split("#")[0].removeprefix("/help/")
    return HELP_DIR / path / "index.html"


def _ids(html: str) -> set[str]:
    # minified output drops the quotes where it can
    return set(re.findall(r'\sid="?([^"\s>]+)', html))


def _template_links() -> list[tuple[str, str | None, str]]:
    """(template, help page, anchor) for every template that overrides the help target."""
    out = []
    for tpl in sorted(TEMPLATES_DIR.rglob("*.html")):
        text = tpl.read_text()
        anchor = re.search(r"{% block help_anchor %}(.*?){% endblock %}", text)
        page = re.search(r"{% block help_page %}(.*?){% endblock %}", text)
        if anchor and anchor.group(1):
            out.append((str(tpl.relative_to(TEMPLATES_DIR)), page.group(1) if page else None, anchor.group(1)))
        for page_arg, anchor_arg in re.findall(r"help_url\('([^']*)', '([^']*)'\)", text):
            out.append((str(tpl.relative_to(TEMPLATES_DIR)), page_arg, anchor_arg))
    return out


@pytest.mark.parametrize("lang", MANUAL_LANGUAGES)
def test_every_menu_item_has_a_chapter(lang):
    with i18n.language(lang):
        missing = [item.url for section in MENU for item in section.items if not _built(help_url(item.url)).is_file()]
        assert _built(help_url()).is_file()
    assert missing == [], f"no manual page for {missing} ({lang}): add it to docs/manual and run scripts/help-build.sh"


@pytest.mark.parametrize("lang", MANUAL_LANGUAGES)
def test_help_anchors_exist(lang):
    links = _template_links()
    assert any(anchor == "edit" for _, _, anchor in links)
    with i18n.language(lang):
        for tpl, page, anchor in links:
            if page is None:
                # list/form pages: the chapter of the menu item their routes belong to
                continue
            html = _built(help_url(page)).read_text()
            assert anchor in _ids(html), f"{tpl}: #{anchor} missing in manual page {page} ({lang})"


@pytest.mark.parametrize(
    ("form", "page"),
    [
        ("phone_form", "accounts/phones"),
        ("provider_form", "accounts/providers"),
        ("application_form", "dialplan/applications"),
        ("callgroup_form", "dialplan/callgroups"),
        ("ivr_form", "dialplan/ivr"),
        ("hours_form", "dialplan/hours"),
        ("conference_form", "services/conferencing"),
        ("ami_user_form", "advanced/manager"),
    ],
)
def test_form_chapters_have_edit_section(form, page):
    assert "{% block help_anchor %}edit{% endblock %}" in (TEMPLATES_DIR / "pages" / f"{form}.html").read_text()
    for lang in MANUAL_LANGUAGES:
        with i18n.language(lang):
            assert {"list", "edit"} <= _ids(_built(help_url(page)).read_text()), (page, lang)


def test_help_url():
    with i18n.language("en"):
        assert help_url() == "/help/"
        assert help_url("/") == "/help/status/summary/"
        assert help_url("/accounts/phones", "edit") == "/help/accounts/phones/#edit"
    with i18n.language("de"):
        assert help_url("/system/backup") == "/help/de/system/backup/"
    with i18n.language("fr"):
        assert help_url("/system/backup") == "/help/system/backup/"


def test_manual_is_public(client):  # noqa: F811
    r = client.get("/help/", follow_redirects=False)
    assert r.status_code == 200 and "PhonixPBX" in r.text
    assert r.headers["cache-control"].startswith("public")
    assert client.get("/help/de/accounts/phones/").status_code == 200
    assert client.get("/help/nope/").status_code == 404


def test_help_buttons(client):  # noqa: F811
    assert 'href="/help/getting-started/#login"' in client.get("/login").text
    login(client)
    assert 'href="/help/status/summary/"' in client.get("/").text
    page = client.get("/accounts/phones").text
    assert 'href="/help/accounts/phones/"' in page and 'href="/help/"' in page
    assert 'href="/help/accounts/phones/#edit"' in client.get("/accounts/phones/new?tech=pjsip").text
    assert 'href="/help/getting-started/#password"' in client.get("/password").text
    token = csrf(client, "/account")
    client.post("/account", data={"csrf_token": token, "language": "de"})
    assert 'href="/help/de/getting-started/#account"' in client.get("/account").text
    assert 'href="/help/de/system/backup/"' in client.get("/system/backup").text
