# Changelog

All notable changes to PhonixPBX are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Status → Logs shows the logs of the web application and the security monitor
  (`/var/log/phonix/web.log`, `monitor.log`), live like the Asterisk and system logs. The MCP
  `tail_log` tool reads them too.
- The console menu can view the Asterisk, system, web application and monitor logs and
  follows them live until Ctrl-C.
- The OCI image writes the web and monitor output to `/var/log/phonix` as well as to the
  container output.
- The appliance and the LXC images announce themselves on the LAN with mDNS:
  `https://<hostname>.local/` opens the web interface, and discovery tools find it as an
  HTTPS service. It is on by default and can be turned off under System → General. The
  firewall lets mDNS through, and new self-signed certificates include the `.local` name.
- Voicemail and missed call e-mails are sent in the language of the phone, with the date
  formatted for that language and the reason of a missed call spelled out ("Busy", "No
  answer"). Phones get an *E-mail language* setting (default: the phone's language). Under
  Services → Voicemail the subject and text of both e-mails can be changed per language,
  with a preview and a reset to the built-in text.

### Changed

- The custom voicemail e-mail subject and text are kept as the texts of the default prompt
  language. Configuration files (`config.json`) are now version 2; version 1 files are
  upgraded on import.
- `/usr/libexec/phonix/notify` replaces `notify-missed-call`.

### Fixed

- Saving a call group that keeps some of its members failed with a database error
  (`UNIQUE constraint failed: callgroup_members.group_id, callgroup_members.phone_id`).

## [1.1.0] - 2026-10-14

### Added

- MCP (Model Context Protocol) server at `/api/mcp` for AI assistants such as Claude. It uses
  the API bearer tokens; read-only tokens can only use the read tools. The tools cover phones,
  providers, call groups, conferences, applications, AMI users, settings, system and Asterisk
  status, logs, and previewing and applying pending changes. The API tokens page shows an
  example client command.
- `phonix config export|import|schema` to export and import the configuration as a
  versioned `config.json`. Its JSON Schema is in `docs/config-schema.json`. Settings groups
  missing from an imported file keep their current values.
- Restoring a backup first shows a preview of its contents. Stored backups can be restored
  directly from the list.
- A restore can keep parts of the current system: the network, firewall and SSH settings
  (kept by default, so a backup from another system cannot lock you out), the web users and
  API tokens, and the TLS certificate with the ACME settings. On the command line:
  `phonix backup restore --restore-network|--keep-users|--keep-certificate`.

### Changed

- Backups contain the configuration as a versioned, schema-validated `config.json` instead
  of a copy of the database. A restore validates everything and does a dry run first, then
  replaces the configuration in one transaction and applies it right away. Backups from
  older releases restore on newer ones; backups made with 1.0.0 can no longer be restored.
- The Asterisk database is no longer part of backups. Backup files are only readable by
  the `phonix` user.
- Web sessions end if their user was replaced or their password changed, e.g. by a restore
  or a password reset on the console. Changing your own password keeps the current session.
  All users are logged out once after updating.
- The console menu shows a spinner instead of the prompt while the system reboots or shuts
  down, and ignores further input. If the system is still up after five minutes, the menu
  comes back.
- Read-only API tokens no longer get the voicemail and conference PINs.

### Fixed

- Uploading a firmware update larger than 128 MiB (e.g. on the Raspberry Pi) failed with
  "Server responded with 0 code." and nothing was installed: the upload was buffered in the
  small `/tmp` RAM disk. Uploads are now buffered on the data partition, and the web
  interface stays responsive while an update is installed. A failed upload no longer leaves
  the partial bundle on the data partition.
- Restoring a backup could leave the system broken: the database was replaced under
  running processes, a backup from a newer release failed halfway through, and media,
  TLS and ACME directories lost their permissions.
- With two backups created within the same second, removing old backups could delete the
  newer one.
- The online update check offered any release that differed from the running version, even
  an older one (e.g. 1.0.1 on a 1.1.0 development build). Versions are now compared by
  PEP 440 (release candidates, post and development releases) and only newer releases are
  offered. An update check response without a version is reported as an error.

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

[Unreleased]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/PhonixPBX/PhonixPBX/releases/tag/v1.0.0
