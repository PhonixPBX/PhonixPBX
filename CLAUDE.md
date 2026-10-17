# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PhonixPBX is the successor of AskoziaPBX. It is an appliance PBX made of Alpine 3.24, Asterisk 22 (PJSIP), a Python 3.10+ FastAPI app and SQLite, with a Tabler + htmx web UI. It ships as disk images, LXC containers and an OCI image. The original PHP/T2 tree in `legacy/` is reference material only; don't change it. The specification lives in `docs/SPEC.md`.

## Commands

```sh
uv venv -p 3.10 .venv && uv pip install -e '.[dev]' -c dev/constraints-alpine-3.24.txt

.venv/bin/pytest -q                                   # unit + web tests (asterisk/integration markers excluded by default)
.venv/bin/pytest tests/test_web.py::test_token_ui     # single test
UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_generators.py tests/legacy   # accept changed golden files
.venv/bin/ruff check . && .venv/bin/ruff format --check phonix tests
.venv/bin/mypy phonix
dev/test-asterisk.sh                                  # Asterisk/SIPp integration tests in the Alpine dev container
dev/run.sh                                            # full dev container on :8000 (dev/console.sh = console menu)
```

To run the app locally without root (privileged actions are only recorded):

```sh
export PHONIX_DATA_DIR=$PWD/dev/root/data PHONIX_ROOT=$PWD/dev/root PHONIX_PRIVILEGED=dry-run PHONIX_DEV=1
.venv/bin/phonix migrate && .venv/bin/phonix user add admin --password 'change-me-now'
.venv/bin/phonix web --reload
.venv/bin/phonix generate /tmp/out                    # render all generated config files
```

CI (`.github/workflows/ci.yml`) runs ruff, mypy and pytest.

## Architecture

- **Data model.** The data lives in SQLite at `<data>/phonix.db`.
  - Entities are SQLAlchemy models in `phonix/core/models.py`. They are named after the legacy `config.xml` concepts and carry `legacy_uniqid` for import/export round trips.
  - Scalar settings are pydantic `SettingsGroup` models in `phonix/core/settings.py`, stored as JSON rows in the `settings` table. Use `st.load(session, Model)` and `st.save(...)`. A new group must be added to `ALL_GROUPS`, and that changes the legacy golden JSON files.
  - Schema changes need an Alembic revision in `phonix/core/migrations/versions/`. Keep it identical to the models; autogenerate's `compare_metadata` must report no diff.
- **Service layer** (`phonix/services/`). The HTML UI, the REST API (`/api/v1`), the CLI and the legacy importer all call it. User-facing errors are raised as `ServiceError(message, fields={field: msg})`. Mutations write `audit(...)` entries and `mark_dirty(session, *areas)`.
- **Generators** (`phonix/generators/`). These are pure functions from `build_snapshot(session)` to `GeneratedFile`s. Each file has a target path and a `component`, and is either written by the web user or `privileged`. Templates are in `generators/templates/`. Golden outputs in `tests/golden/` are compared byte for byte.
- **Apply** (`phonix/services/apply.py`). It generates everything, writes only the files that changed, and reloads only the affected components. Asterisk is reloaded over AMI (`phonix/ami.py`, `RELOAD_COMMANDS`). Files that are root-owned are staged in `/run/phonix/staged` and installed through the privileged helper. The UI shows pending "dirty" areas until the user applies.
- **Privilege separation.** The web app runs as user `phonix`. Root actions go only through `phonix/services/privileged.py` (`ACTIONS` whitelist, argument regex), which runs `doas /usr/libexec/phonix/priv <action>`.
  - The helper exists in three copies that must stay in sync: `system/libexec/priv` (appliance), `system/container/priv` (OCI) and `dev/libexec/priv`.
  - `PHONIX_PRIVILEGED=dry-run` (used in tests) records the calls in `privileged.recorder.calls`.
- **Paths.** `phonix/config.py`'s `RuntimeConfig` reads its paths from `PHONIX_*` environment variables. `cfg.path("/etc/...")` maps absolute targets below `PHONIX_ROOT`, so tests and dev write into temp dirs. The `tests/conftest.py` autouse fixture gives every test its own data dir and root.
- **Web** (`phonix/web/`).
  - Routes are in `routes/ui/*.py` (HTML) and `routes/api.py` (JSON).
  - The menu is in `templating.py`. Form macros (`input`, `secret`, `select`, `checkbox`, `radios`, `textarea`) are in `templates/macros/forms.html`, and `data-show-if="field=value"` toggles conditional fields.
  - Settings pages use `save_settings_form()` (`routes/ui/common.py`). Secrets are never echoed back to the browser; an empty secret field keeps the stored value.
  - UI auth is a session cookie plus a CSRF token on every unsafe request, enforced by `ui_user`/`verify_csrf`. API auth is bearer tokens (`phonix/services/tokens.py`) or the UI session.
  - MCP (`POST /api/mcp`): the JSON-RPC methods and tools are in `phonix/mcp.py`, the HTTP transport in `routes/mcp.py`. Bearer tokens only (`mcp_token`); read-only is checked per tool. Entity tools and the REST CRUD endpoints are both generated from `RESOURCES` in `phonix/services/resources.py`, and settings go through `phonix/services/settings_api.py`.
  - The CSP forbids inline scripts, so behaviour goes in `static/phonix.js` through `data-*` attributes.
  - Front-end assets are vendored; refresh them with `scripts/vendor-update.sh`.
- **System integration.**
  - OpenRC services are in `system/openrc/` and nginx (TLS termination in front of the uvicorn unix socket) is in `system/nginx/phonix.conf`.
  - The OCI image doesn't use OpenRC: `system/container/entrypoint` duplicates the directory setup and service start.
  - The app is packaged as an apk (`packaging/apk/phonix/APKBUILD`; runtime deps are Alpine `py3-*` packages, so a new Python dependency must exist in Alpine 3.24). `Containerfile` and `dev/Containerfile` keep their own copies of the package lists.
  - `/data` is the persistent partition (DB, `tls/`, `acme/`, media, backups). The rootfs is a read-only squashfs.

## Translations

- The web UI is translated with gettext (`phonix/i18n.py`).
  - Mark strings with `_("...")`, or `N_("...")` for module-level constants that are translated where they are displayed.
  - Use named placeholders only: `_("Deleted %(name)s.", name=x)`. Never wrap an f-string, and never build sentences from translated fragments.
  - In templates, `{{ _("...") }}` always %-formats its result, so a literal `%` must be written `%%`.
- After changing UI strings, run `scripts/i18n.sh update` and translate the new entries in all 11 catalogs under `phonix/locale/`. `tests/test_i18n.py` enforces complete catalogs.
- Don't translate: logs, audit summaries, JSON API errors, CLI/console output, generated config files.
- The request language is a contextvar. `LanguageMiddleware` sets it from the session; the session copy comes from `User.language`.

## Conventions

- Commit messages: `area: lowercase summary` (e.g. `certificate: ...`, `ui: ...`, `nginx: ...`).
- Every user-visible change gets an entry in `CHANGELOG.md` under `## [Unreleased]` (Keep a Changelog sections: Added, Changed, Fixed, Removed, Security), committed together with the change itself. Write it for administrators: what they can now do or what behaves differently, with menu paths (e.g. *Dialplan → IVR Menus*), and call out anything that needs action (incompatible `config.json` versions, upgrades, replaced containers). Internal refactors and tests get no entry.
- Keep `docs/SPEC.md` in step with features and design decisions (data model, feature scope, API/MCP, backup format, implementation notes).
- Ruff line length is 120.
