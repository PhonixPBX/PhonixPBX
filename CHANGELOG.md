# Changelog

All notable changes to PhonixPBX are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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

[1.0.0]: https://github.com/PhonixPBX/PhonixPBX/releases/tag/v1.0.0
