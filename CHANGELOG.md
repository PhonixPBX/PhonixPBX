# Changelog

All notable changes to PhonixPBX are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- MCP (Model Context Protocol) server at `/api/mcp` for AI assistants such as Claude. It uses
  the API bearer tokens; read-only tokens can only use the read tools. The tools cover phones,
  providers, call groups, conferences, applications, AMI users, settings, system and Asterisk
  status, logs, and previewing and applying pending changes. The API tokens page shows an
  example client command.
- `phonix config export|import|schema` to export and import the configuration as a
  versioned `config.json`. Its JSON Schema is in `docs/config-schema.json`.
- Restoring a backup first shows a preview of its contents. Stored backups can be restored
  directly from the list.

### Changed

- Backups contain the configuration as a versioned, schema-validated `config.json` instead
  of a copy of the database. A restore validates everything and does a dry run first, then
  replaces the configuration in one transaction and applies it right away. Backups from
  older releases restore on newer ones; backups made with 1.0.0 can no longer be restored.
- The Asterisk database is no longer part of backups. Backup files are only readable by
  the `phonix` user.
- Web sessions end if their user was replaced, e.g. by a restore. All users are logged out
  once after updating.

### Fixed

- Restoring a backup could leave the system broken: the database was replaced under
  running processes, a backup from a newer release failed halfway through, and media,
  TLS and ACME directories lost their permissions.

## [1.0.0] - 2026-10-13

First release of PhonixPBX, the successor of AskoziaPBX, rebuilt on Alpine Linux 3.24,
Asterisk 22 (PJSIP), Python (FastAPI) and SQLite.

### Platforms

- Bootable disk images for Raspberry Pi (`rpi-arm64`: 3B+, 4, 5, Zero 2 W), PCs and VMs
  (`pc-amd64`, UEFI and BIOS) and `pc-x86` (BIOS, best effort), with a read-only squashfs
  root, A/B slots and automatic rollback.
- LXC/Incus/Proxmox VE system containers (`lxc-amd64`, `lxc-arm64`).
- Multi-arch OCI image `ghcr.io/phonixpbx/phonix` for Docker and Podman.
- Signed (ed25519) update bundles, uploaded in the web interface or checked online.

### Telephony

- Phones (PJSIP, IAX, external) and providers (PJSIP trunks with registration, IAX).
- Call groups, dialplan applications with server-side validation, feature codes,
  transfers and call parking.
- Voicemail with voicemail-to-email, conferencing (ConfBridge), music on hold, custom
  greetings and prompt languages.
- PJSIP transports, NAT/external IP, TLS and SRTP, RTP port range, AMI users.

### Administration

- Web interface (Tabler + htmx) with the AskoziaPBX menu structure and colours, available
  in 12 languages.
- REST API (`/api/v1`) with bearer tokens, and the `phonix` command line tool.
- Status dashboard with registrations, active calls, live logs and CPU/network graphs.
- Backup and restore of the database and media.
- TLS certificates, including ACME.
- Import of AskoziaPBX 2.x `config.xml` (dry run, replace or merge) and best-effort export
  back to the old format; a `config.xml` on the boot partition is imported at first boot.
- Console menu on tty1: show IP, set LAN IP, reset password, factory reset, reboot.
- Privilege separation: the web app runs unprivileged and root actions go through a
  whitelisted helper.

### Upgrading from nightly builds

The pre-release database migrations were squashed into a single initial revision.
Nightly installs at the latest pre-release schema are upgraded automatically; older
nightly databases must be recreated (factory reset).

[Unreleased]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/PhonixPBX/PhonixPBX/releases/tag/v1.0.0
