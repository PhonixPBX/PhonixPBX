# Changelog

All notable changes to PhonixPBX are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- *Dialplan → Business Hours*: an out-of-office key with a lamp. A phone key on the feature code of business hours
  is lit while they are closed and dark while they are open, whatever the reason (opening hours, holiday, special
  period, key or manual mode), and pressing it switches to the opposite state. On Snom phones, set up a function key
  of type **BLF** with the feature code as its number.
- *Dialplan → Business Hours*: **Special periods**, an ordered list per business hours that takes precedence over
  holidays and the weekly hours. Each period can be switched on and off, optionally applies only between two dates
  (also every year, e.g. 24.12.–02.01.), has its own destination, which may also be other business hours (e.g.
  shorter opening hours over Christmas), and can have its own feature code that switches it on and off, with a lamp
  that is lit while the period is on (BLF key on Snom phones). The first period in the list that is on and whose
  dates include today applies. Periods are switched on the list page, on the edit page, through the REST API and
  through MCP immediately, without applying the configuration. The list page shows why business hours are open or
  closed right now.
- *Dialplan → Business Hours*: **Year at a glance** on the edit page shows the next twelve months (or 24, 36, up to 60)
  as calendars, with each day coloured by what applies: the weekly hours, closed all day, a holiday or a special
  period. It shows the entries in the form, also before they are saved, and is available for new business hours too.
- *Accounts → Providers*: the list has a **Status** column with the registration state of each provider
  (e.g. *Registered*, *Rejected*), or for providers without registration and IAX providers whether they can be
  reached. It updates every 15 seconds.

### Changed

- *Dialplan → Business Hours*: the edit page is organised in tabs (General, Weekly hours, Holidays, Special periods,
  Year at a glance). A tab with a wrong entry opens and is marked after saving, and `#tab-…` links open a tab directly.
  **Save and stay** saves without leaving the page and returns to the open tab.
- The card **Numbers with +** (**Replace a leading + with**) moved from *Accounts → Providers* to
  *Dialplan → Transfers & Parking*. The setting itself is unchanged.
- *Dialplan → Business Hours*: the feature code no longer switches between “Closed” and “Automatic”. It now switches
  to the opposite of the current state until the next change, at midnight at the latest, so a forgotten press never
  keeps the office open or closed over a weekend. Pressed again, it returns to “Automatic”; it also ends a permanent
  mode set on the web interface, REST API or MCP.
- Restoring a backup (*System → Backup/Restore*, `phonix backup restore`), `phonix config import` and a legacy
  import that replaces the configuration set all business hours back to **Automatic**: permanent modes and the
  state of the out-of-office key are cleared, and special periods are switched on or off as saved in the backup.
  Before, the mode of the replaced configuration could stick to restored business hours with the same number.
- The help button at the top right of each page is bigger.
- The pages of the web interface use the full width of the browser window.
- The sidebar marks the open page more clearly: a solid background, bold text and a bar on the left.
- The **Apply changes** button in the pending changes banner is dark amber instead of black.
- The top bar and the banners for pending changes and a pending reboot stay at the top while the page scrolls.
- The web interface is built on Tabler 1.7.1: buttons, switches, small selects and some dark mode surfaces look
  slightly different, and dark mode has better contrast.
- Configuration backups (`config.json`) are now version 5 and contain the special periods. Older backups still
  restore; backups of this version cannot be restored on older PhonixPBX versions.

### Fixed

- *Services → Voicemail*: the text of the mail previews was light grey on grey and could hardly be read.

## [1.9.0rc2] - 2026-10-23

### Added

- *Accounts → Providers*: phones can dial numbers in the international form with a leading `+` (for example
  `+41 44 123 45 67` from an address book or call list), also through click-to-call. The `+` is replaced with `00`
  before the dial patterns are matched; set **Replace a leading + with** in the new card **Numbers with +** to `000`
  with an outside line prefix `0`, to `011` in North America, or leave it empty to switch it off.

## [1.9.0rc1] - 2026-10-23

### Added

- *Dialplan → Call Groups*: a call group can now contain other call groups as members, next to phones. With
  *Ring all at once* all their phones ring together; with *One after another* a contained group is one step in which
  all its phones ring at once. A phone that is in several of the groups rings only once, and a group cannot contain
  itself, directly or through another group.
- *Dialplan → Call Groups*: drag the **Members** into a new order instead of removing and adding them again. With
  *One after another* this is the order in which they ring.

### Changed

- REST API and MCP: call groups have a new `members` field, the ordered list of `phone:<id>` and `callgroup:<id>`.
  `member_ids` still works for phones.
- Configuration backups (`config.json`) are now version 4. Older backups are upgraded on restore; backups of this
  version cannot be restored on PhonixPBX 1.8 or older.
- The export to the legacy `config.xml` writes a contained call group as its phones.

### Fixed

- *Accounts → Phones* and *Accounts → Providers*: the **Codecs** can now be dragged into order of preference, as
  the manual describes.

## [1.8.0] - 2026-10-21

### Changed

- OCI container (Docker, Podman): all logs (Asterisk, web interface, security monitor, nginx errors) now go only
  to the container output, read them with `docker logs -f <container>`. No log files are written in the container
  any more, and *Status → Logs* shows a notice instead. Limit the size with the log driver of the container engine
  (e.g. `--log-opt max-size=10m`).
- The log of an LXC/Incus container update is now kept in `/var/lib/phonix/update.log`, so it survives the restart into
  the new version.
- Logs are checked every 15 minutes instead of once a day and rotated at 1–2 MB, so a SIP scan can no longer fill
  the RAM with a huge security log.

### Fixed

- LXC/Incus system containers wrote every log line (Asterisk, web interface, nginx, syslog) to the host's disk. Now
  `/var/log` and `/tmp` are kept in RAM, as on the appliance; the logs are lost when the container restarts. Takes
  effect with the update and a restart of the container.

## [1.7.0] - 2026-10-18

### Changed

- *System → Firmware* refuses an update bundle whose version is not newer than the running one, right after the
  upload and before anything is written; the uploaded file is deleted. To install the same or an older version
  (recovery, test builds), use `phonix update install <file> --force` on the console.

### Fixed

- Uploading a file in *System → Firmware* and *System → Backup/Restore* now shows a progress bar; before, nothing
  visible happened until the upload had finished.

## [1.6.0] - 2026-10-18

### Added

- After a firmware update has been installed, every page shows a *Reboot required* banner with a **Reboot now**
  button until the system (or the LXC container) has been restarted into the new version.

### Changed

- *System → Firmware → Check now*: a newer release comes with a **Download** button for the update bundle of
  this board (`phonix-<version>-<board>.update`) and a **Release notes** link, instead of the address of the
  release page as plain text. The page keeps showing the last result until the version is installed.

### Fixed

- LXC containers: between installing an update and restarting the container, pages of the web interface no
  longer fail with an error (*Internal Server Error*). This takes effect for updates installed from this version
  on: when you update an LXC container from 1.5.0 or older, restart the container right after the installation.

## [1.5.0] - 2026-10-18

### Added

- On the console, `phonix update install <file>` installs an update bundle. It runs one installation at a time, also
  against an upload in *System → Firmware*.

### Changed

- *System → Firmware*: after the upload, the page shows the progress of the installation in steps (check, backup
  on LXC, install) with the elapsed time, instead of an upload field that stays at 100 %. You can leave and come
  back; the update continues in the background, and another upload is refused until it has finished. After
  *Reboot into the new firmware* the page waits for the system and then confirms that the new version runs, or
  reports that the previous version was started again.
- *System → Firmware*: rebooting and resetting to factory defaults are refused while a firmware update is being
  installed. An installation that was cut off by a crash or power loss is shown as interrupted.

### Fixed

- Installing a firmware update on a slow SD card no longer ends with an error page while the update itself
  succeeded: the installation no longer runs inside the upload request.

## [1.4.0] - 2026-10-17

### Added

- User manual in English and German, available on the PBX under `/help/` without logging in. It explains
  every page of the web interface and has a chapter for phone users with all dial codes (transfer, pickup,
  parking, voicemail, call forwarding, conference rooms).
- A help button (?) in the header of every page opens the matching chapter of the manual in a new tab, in
  German when German is your interface language and in English otherwise. Create and edit forms jump straight
  to the description of their fields. The footer and the login page link to the manual too.
- *System → Firmware → Check automatically* now works: once a day the PBX asks the update information URL
  for the newest release. When a check (daily or *Check now*) finds a newer version, *Status → Summary*
  shows a notice with a link to *System → Firmware*. Nothing is downloaded or installed automatically.
  `phonix update check` runs the check from the command line.
- REST API for AskoziaPBX configurations: `POST /api/v1/legacy/import` (preview by default,
  `?dry_run=false&mode=replace|merge` to import) and `GET /api/v1/legacy/export`. The export contains
  plaintext secrets and is refused for read-only tokens.
- When a `config.xml` on the boot partition was imported at first boot, *Status → Summary* now shows the
  import report until you dismiss it.

### Changed

- The SIP registration timers under *Advanced → SIP* now take effect: phones that ask for a registration
  interval outside *Minimum expiry*–*Maximum expiry* get the nearest limit, and phones that ask for none
  get *Default expiry*. Check the values after upgrading if your phones use unusual intervals.
- Turning off *Use DNS SRV lookups* under *Advanced → SIP* now works: providers without a port are
  contacted directly on port 5060 (TLS: 5061) instead of looking up DNS SRV records.
- Changes to the automatic blocking under *Advanced → Firewall* apply within about a minute; before, they
  needed a restart of the security monitor.

### Removed

- *Advanced → GUI Options → Always expand advanced sections*: it had no effect, since the forms show all
  fields in tabs. The value is still accepted in `config.json`.

### Fixed

- The disconnect code (*Dialplan → Transfers & Parking*, default `*0`) now ends the call; it had no effect
  before. On calls from providers only the internal phone can use it.
- Manager (AMI) users with permitted networks other than localhost can connect with the firewall enabled:
  port 5038 is now opened for those IPv4 networks (after *Apply changes*).

## [1.3.0] - 2026-10-17

### Added

- LXC/Incus/Proxmox VE system containers can be updated in place. Each release has an update
  bundle per container board (`phonix-<version>-lxc-<arch>.update`); uploading it under
  *System → Firmware* saves a configuration backup and upgrades the packages, and the new
  version starts when the container restarts. There is no automatic rollback: the page asks
  you to take a snapshot on the container host first. OCI containers are still updated by
  replacing the image. Containers created from 1.2.0 or older must be replaced once to get
  this feature.
- Click-to-call: `POST /api/v1/calls` and the MCP tool `originate_call` ring a phone and, when
  it is answered, dial a number from it with the phone's outgoing rules and caller ID. Only
  API tokens with the new *May place calls* option can use them (off by default, also on
  read-only tokens; `phonix token create --allow-calls`).
- IVR menus (Dialplan → IVR Menus): an announcement, uploaded or one of Asterisk's sounds, then
  one destination per key (0-9, `*`, `#`), such as a phone, call group, voicemail box,
  conference, another menu or business hours. Drag the options (or use the arrows) to change
  the order in which they are announced; *Write from options* turns that order into a
  recording script. Each menu sets the wait time, the repeats, where calls go when no key or
  an unknown key is pressed, and whether callers may dial extensions directly. The editor
  shows the call flow and can ring your phone to test the menu.
- Business hours (Dialplan → Business Hours): weekly opening hours with several ranges per day,
  holidays (once or every year), and a destination while open and while closed. They can be
  used as the destination of a provider's incoming route or of an IVR key. The page, the REST
  API, the MCP tool `set_business_hours_mode` and an optional feature code dialled on a phone
  switch between automatic, open and closed at once, without applying the configuration.
- Provider incoming routes can lead to IVR menus and business hours.

### Changed

- Lower memory use. Web passwords are hashed with argon2id at 19 MiB instead of 64 MiB per
  hash (existing hashes are upgraded at the next login), so the web application peaks at
  about 90 MB instead of 150 MB. nginx runs one worker process instead of one per CPU core.
  Containers now need at least 256 MB RAM (512 MB recommended) instead of 512 MB (1 GB).
- The `pc-x86` image needs a CPU with SSE2. PC Engines ALIX boards (AMD Geode) are not
  supported; move their AskoziaPBX `config.xml` to supported hardware.
- Configuration files (`config.json`, also in backups) are now version 3: they include IVR
  menus, business hours and the *May place calls* option of API tokens. Older systems refuse
  them; version 1 and 2 files are still imported.
- The AskoziaPBX `config.xml` export leaves out IVR menus, business hours and the incoming
  routes that lead to them, and lists them in the export report.

## [1.2.0] - 2026-10-14

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

[1.9.0rc2]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.9.0rc1...v1.9.0rc2
[1.9.0rc1]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.8.0...v1.9.0rc1
[1.8.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/PhonixPBX/PhonixPBX/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/PhonixPBX/PhonixPBX/releases/tag/v1.0.0
