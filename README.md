AskoziaPBX NG
=============

A revival of AskoziaPBX: an appliance PBX built on Alpine Linux, Asterisk 22 (PJSIP),
Python (FastAPI) and SQLite, with a Tabler + htmx 4 web interface in the original Askozia
look. Bootable images are built for Raspberry Pi (arm64), amd64 and x86.

- Specification: [docs/SPEC.md](docs/SPEC.md)
- Installation: [docs/INSTALL.md](docs/INSTALL.md)
- The original 2007–2011 tree (T2 SDE, PHP web GUI) is preserved in [legacy/](legacy/).

## Layout

| Path | Contents |
|---|---|
| `askozia/core` | settings, SQLAlchemy models, validation, Alembic migrations |
| `askozia/services` | service layer used by the UI, the REST API, the CLI and the legacy importer |
| `askozia/generators` | pure functions: DB snapshot → Asterisk/OS configuration files |
| `askozia/legacy` | legacy `config.xml` import/export |
| `askozia/web` | FastAPI app, Jinja templates, static assets (vendored Tabler/htmx) |
| `askozia/cli.py` | `askozia` command (apply, firstboot, user, legacy, backup, web, …) |
| `system/`, `packaging/`, `image/` | files installed into the image, the APKBUILD and the image builder |
| `tests/` | unit, web and golden-file tests; `tests/integration` runs against real Asterisk |

## Development

```sh
uv venv -p 3.10 .venv
uv pip install -e '.[dev]' -c dev/constraints-alpine-3.24.txt

.venv/bin/pytest                 # unit + web tests
.venv/bin/ruff check . && .venv/bin/ruff format --check askozia tests
.venv/bin/mypy askozia
dev/test-asterisk.sh             # Asterisk 22 + SIPp tests in the Alpine dev container (podman)
```

Run the web interface locally (no root needed; privileged actions are only logged):

```sh
export ASKOZIA_DATA_DIR=$PWD/dev/root/data ASKOZIA_ROOT=$PWD/dev/root \
       ASKOZIA_PRIVILEGED=dry-run ASKOZIA_DEV=1
.venv/bin/askozia migrate
.venv/bin/askozia user add admin --password 'change-me-now'
.venv/bin/askozia web --reload          # http://127.0.0.1:8000
.venv/bin/askozia generate /tmp/out     # render all generated config files
```

Front-end assets are vendored; refresh them with `scripts/vendor-update.sh`.

## License

New code is licensed under the [Apache License 2.0](LICENSE). Third-party and legacy parts
keep their own licenses, see [NOTICE](NOTICE).
