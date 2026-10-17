<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="phonix/web/static/img/logo-sidebar.svg">
    <img src="phonix/web/static/img/logo.svg" alt="PhonixPBX" width="340">
  </picture>
</p>

<p align="center">
  The appliance PBX on Alpine Linux and Asterisk 22, successor of AskoziaPBX.
</p>

<p align="center">
  <a href="https://github.com/PhonixPBX/PhonixPBX/actions/workflows/ci.yml"><img src="https://github.com/PhonixPBX/PhonixPBX/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
  <a href="https://github.com/PhonixPBX/PhonixPBX/actions/workflows/image.yml"><img src="https://github.com/PhonixPBX/PhonixPBX/actions/workflows/image.yml/badge.svg" alt="image"></a>
  <a href="https://github.com/PhonixPBX/PhonixPBX/actions/workflows/container.yml"><img src="https://github.com/PhonixPBX/PhonixPBX/actions/workflows/container.yml/badge.svg" alt="container"></a>
  <a href="https://github.com/PhonixPBX/PhonixPBX/releases"><img src="https://img.shields.io/github/v/release/PhonixPBX/PhonixPBX?sort=semver" alt="release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/PhonixPBX/PhonixPBX" alt="license"></a>
</p>

PhonixPBX is the successor of AskoziaPBX (2007–2011): an appliance PBX built on Alpine
Linux, Asterisk 22 (PJSIP), Python (FastAPI) and SQLite, with a Tabler + htmx 4 web
interface in the classic AskoziaPBX colours. Configurations of AskoziaPBX 2.x systems
can be imported.

It ships as

- bootable disk images for Raspberry Pi (arm64), PCs and VMs (amd64, x86),
- LXC system containers for Incus and Proxmox VE,
- an OCI image for Docker and Podman.

## Documentation and downloads

- User manual (English, German): on every PBX under `https://<pbx>/help/` and behind the help button on
  each page; sources in [docs/manual/](docs/manual/)
- Specification: [docs/SPEC.md](docs/SPEC.md)
- Installation: [docs/INSTALL.md](docs/INSTALL.md)
  - [Raspberry Pi, PC and VM disk images](docs/INSTALL.md#1-write-the-image)
  - [Proxmox VE, Incus and LXC system containers](docs/INSTALL.md#lxc-incus-and-proxmox-ve-system-containers)
  - [Container image](docs/INSTALL.md#container-image-docker-podman):
    `docker run -d --network host -v phonix-data:/data ghcr.io/phonixpbx/phonix:latest`
- Downloads: [releases](https://github.com/PhonixPBX/PhonixPBX/releases) (nightly builds:
  the `nightly` pre-release and `ghcr.io/phonixpbx/phonix:edge`)
- Changes: [CHANGELOG.md](CHANGELOG.md), release process: [docs/RELEASING.md](docs/RELEASING.md)
- The original AskoziaPBX tree (T2 SDE, PHP web GUI) is preserved in [legacy/](legacy/).

## Why "Phonix"?

"Askozia" is a registered trademark of the former owners of AskoziaPBX, so the revived
project needed a name of its own.

**Phonix = phone + phoenix.** The project is a telephone system, and like the phoenix it
rises again: the AskoziaPBX code base lay dormant for more than a decade, and PhonixPBX
brings its ideas, menu structure, dialplan logic and colours back on a modern foundation.
Old AskoziaPBX configurations can still be imported. The spelling *Phonix* instead of
*Phoenix* is deliberate, to put the "phone" into the phoenix.

- **`phonix`** is the technical name: Python package, CLI (`phonix apply`), system user,
  paths (`/etc/phonix`) and service names.
- **PhonixPBX** is the product name for the UI, logo, documentation and domain. The "PBX"
  suffix says what it is and continues the AskoziaPBX naming.

## Layout

| Path | Contents |
|---|---|
| `phonix/core` | settings, SQLAlchemy models, validation, Alembic migrations |
| `phonix/services` | service layer used by the UI, the REST API, the CLI and the legacy importer |
| `phonix/generators` | pure functions: DB snapshot → Asterisk/OS configuration files |
| `phonix/legacy` | legacy `config.xml` import/export |
| `phonix/web` | FastAPI app, Jinja templates, static assets (vendored Tabler/htmx) |
| `phonix/cli.py` | `phonix` command (apply, firstboot, user, legacy, backup, config, web, …) |
| `system/`, `packaging/`, `image/` | files installed into the image, the APKBUILD and the image builder |
| `Containerfile`, `system/container/` | OCI image (`ghcr.io/phonixpbx/phonix`): entry point, root helper, health check |
| `tests/` | unit, web and golden-file tests; `tests/integration` runs against real Asterisk |
| `docs/manual` | user manual (Hugo, en/de), built into `phonix/web/static/help` by `scripts/help-build.sh` |

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
The console menu (the same as on the appliance's screen) opens with `dev/console.sh`.
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
After changing UI texts, run `scripts/i18n.sh update` and fill in the new entries of the
catalogs in `phonix/locale/` (`tests/test_i18n.py` checks them).

## License

New code is licensed under the [Apache License 2.0](LICENSE). Third-party and legacy parts
keep their own licenses, see [NOTICE](NOTICE).
