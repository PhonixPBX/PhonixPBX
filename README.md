PhonixPBX
=========

PhonixPBX is the successor of AskoziaPBX (2007–2011): an appliance PBX built on Alpine
Linux, Asterisk 22 (PJSIP), Python (FastAPI) and SQLite, with a Tabler + htmx 4 web
interface in the classic AskoziaPBX colours. Bootable images are built for Raspberry Pi
(arm64), amd64 and x86. Configurations of AskoziaPBX 2.x systems can be imported.

- Specification: [docs/SPEC.md](docs/SPEC.md)
- Installation: [docs/INSTALL.md](docs/INSTALL.md)
- The original AskoziaPBX tree (T2 SDE, PHP web GUI) is preserved in [legacy/](legacy/).

## Layout

| Path | Contents |
|---|---|
| `phonix/core` | settings, SQLAlchemy models, validation, Alembic migrations |
| `phonix/services` | service layer used by the UI, the REST API, the CLI and the legacy importer |
| `phonix/generators` | pure functions: DB snapshot → Asterisk/OS configuration files |
| `phonix/legacy` | legacy `config.xml` import/export |
| `phonix/web` | FastAPI app, Jinja templates, static assets (vendored Tabler/htmx) |
| `phonix/cli.py` | `phonix` command (apply, firstboot, user, legacy, backup, web, …) |
| `system/`, `packaging/`, `image/` | files installed into the image, the APKBUILD and the image builder |
| `tests/` | unit, web and golden-file tests; `tests/integration` runs against real Asterisk |

## Quick start: run it locally in a container

```sh
dev/run.sh            # podman (CONTAINER_ENGINE=docker works too)
dev/run.sh --reset    # start over with an empty data volume
```

This builds the Alpine 3.24 dev image (Asterisk 22 + the Python runtime from apk),
runs first boot, generates the configuration, starts Asterisk and serves the web UI
on http://localhost:8000 with auto-reload of the mounted source. The initial `admin`
password is printed at startup. The container uses host networking, so softphones
on your LAN can register against your machine's IP (SIP 5060/udp, RTP 10000-20000/udp).
Data persists in the `phonix-dev-data` volume; `podman exec -it phonix-dev asterisk -r`
opens the Asterisk console. Network, firewall and boot-slot actions are only logged
inside the container.

## Development

```sh
uv venv -p 3.10 .venv
uv pip install -e '.[dev]' -c dev/constraints-alpine-3.24.txt

.venv/bin/pytest                 # unit + web tests
.venv/bin/ruff check . && .venv/bin/ruff format --check phonix tests
.venv/bin/mypy phonix
dev/test-asterisk.sh             # Asterisk 22 + SIPp tests in the Alpine dev container (podman)
```

Run the web interface locally (no root needed; privileged actions are only logged):

```sh
export PHONIX_DATA_DIR=$PWD/dev/root/data PHONIX_ROOT=$PWD/dev/root \
       PHONIX_PRIVILEGED=dry-run PHONIX_DEV=1
.venv/bin/phonix migrate
.venv/bin/phonix user add admin --password 'change-me-now'
.venv/bin/phonix web --reload          # http://127.0.0.1:8000
.venv/bin/phonix generate /tmp/out     # render all generated config files
```

Front-end assets are vendored; refresh them with `scripts/vendor-update.sh`.

## License

New code is licensed under the [Apache License 2.0](LICENSE). Third-party and legacy parts
keep their own licenses, see [NOTICE](NOTICE).
