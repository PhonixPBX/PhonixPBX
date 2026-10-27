# PhonixPBX — Specification

PhonixPBX (code name `phonix`) is the successor of AskoziaPBX. It was renamed to avoid
trademark issues; the name AskoziaPBX below refers to the original 2007–2011 project.

## Context
This repo is an archived AskoziaPBX tree from 2007–2011. It has three layers:
- **Build:** a T2-SDE build system targeting uClibc, Linux 2.6.39 and GRUB 0.97.
- **Web GUI:** a PHP4 interface derived from m0n0wall, at `package/overlays/pbx/rootfs/usr/www`, with its libraries in `etc/inc/*.inc`.
- **Telephony:** Asterisk 1.8 using chan_sip and DAHDI.

All configuration lives in a single `config.xml` on a read-only FAT partition. That file is turned into roughly 60 Asterisk `.conf` files by `pbx_configure()` in `etc/inc/pbx.inc`.

We are reviving the product on current technology:
- Alpine Linux as the base system
- Python 3.10 or newer with FastAPI
- SQLite as the only configuration store; there is no XML
- Tabler 1.7.1 for the UI, keeping the original AskoziaPBX colors (new PhonixPBX logo)
- Asterisk 22 LTS with PJSIP
- Bootable images for Raspberry Pi (arm64), amd64 and, as best effort, x86

### Confirmed decisions
- **Python:** the code must run on Python 3.10 or newer. At runtime it uses the Alpine-packaged `python3`, which is 3.12 or newer.
- **Engine:** Asterisk 22 LTS. Telephony uses PJSIP plus IAX2. chan_sip, chan_skinny and MeetMe are not used; conferencing moves to ConfBridge.
- **Hardware:** v1 supports SIP and IAX only.
  - Analog and ISDN lines are reached through SIP ATAs or gateways.
  - These are dropped: DAHDI, mISDN, Redfone, GSM, the Pika and COMpact platform code, the LCD, and the reset button.
- **Memory:** the system must run in 256 MB of RAM (a container); 512 MB is recommended. The smallest supported board, the Raspberry Pi Zero 2 W, has 512 MB.
- **Repository:** the old tree moves to `legacy/` and is kept as reference. The new code goes at the repository root.

## 1. Architecture

```
┌─ Browser (Tabler 1.7.1 + htmx 4 + uPlot/Tom Select, server-rendered) ─────┐
                 │ HTTPS
           nginx (TLS, static files, rate limits)  ──unix socket──▶ uvicorn: phonix.web (FastAPI)
                                                                     │
                     ┌───────────────────────────────────────────────┤
                     │ service layer (pure Python, used by UI + /api/v1)
                     │   ├─ SQLite /data/phonix.db  (SQLAlchemy 2 + Alembic)
                     │   ├─ generators: Jinja2 → /etc/asterisk/*.conf (tmpfs)
                     │   ├─ AMI client (reload, status, events)
                     │   └─ privileged ops → doas → /usr/libexec/phonix/* (fixed scripts)
                     ▼
                 Asterisk 22 (PJSIP, IAX2, ConfBridge, Voicemail, MOH)
```

### Core principles

**The SQLite database is the single source of truth.**
- All generated files (Asterisk configs, the network config, `msmtp.conf`, the timezone, etc.) are derived data.
- At boot the `phonix-apply` service regenerates them before Asterisk starts. This replaces `rc.bootup` and `pbx_configure()`.

**Changes are staged, then applied.** This mirrors the old `*.dirty` workflow.
- A save writes to the database and marks the affected subsystems dirty.
- The UI then shows an "Apply changes" banner.
- Apply regenerates only the affected files, validates them, and reloads.
  - Asterisk is reloaded over AMI with targeted modules, for example `module reload res_pjsip.so` or `dialplan reload`.
  - Asterisk is fully restarted only when a change requires it.

**Generation is deterministic and pure.**
- Each generator has the form `generate(db_snapshot) -> dict[path, text]`.
- Generators perform no I/O, so they can be unit tested with golden files.
- Writing to disk is atomic: write a temporary file, then rename it.

**The web process runs unprivileged.**
- It runs as user `phonix`.
- Anything that needs root goes through `doas`. A rule allows `phonix` to run only the fixed scripts in `/usr/libexec/phonix/`.
  - Examples: `apply-network`, `set-time`, `reboot`, `install-update`, `factory-reset`.
- These scripts accept validated arguments only.
- The web server is not exposed directly; it sits behind nginx.

**The REST API comes first.**
- `/api/v1/...` is a JSON API with an OpenAPI schema.
- Scripts authenticate with bearer tokens (`Authorization: Bearer phx_...`). Tokens are managed under *Advanced → API tokens* or with `phonix token`. Each token is read-only (GET only, without the voicemail and conference PINs) or read-write, can be disabled, and expires after 1–3653 days or never (no expiry set). Only a SHA-256 hash is stored, and the last use is recorded. HTTP basic auth is not accepted. The web interface's own requests use the session cookie plus the CSRF header.
- Click-to-call: `POST /api/v1/calls` (`{"extension", "number"}`, answers 202) rings the SIP or IAX phone and, when it is answered, dials the number in the phone's `phone-<ext>` context, so its outgoing rules and caller ID apply (AMI `Originate`, audited as `originate`). It needs a token with *may place calls* (`allow_calls`, off by default, `phonix token create --allow-calls`); that flag works independently of read-only, so a read-only token with it can place calls but not change the configuration. The UI session also works.
- Audio files: `POST /api/v1/media?kind=moh|vm_greeting|ivr_prompt&filename=...` takes the audio as the raw request body (at most 64 MB, `413` above) and stores it through the same `add_media()` as the UI upload (conversion to 8 kHz mono WAV, sox when installed). `GET /api/v1/media` (`kind`, `q`, `limit`, `offset`), `GET /api/v1/media/{id}`, `GET /api/v1/media/{id}/audio` (the converted WAV) and `DELETE /api/v1/media/{id}`. IVR menus refer to an announcement by `prompt_media_id`. This is the push path for announcements produced elsewhere (e.g. text-to-speech); pulling from an external service and recording by phone are planned as further sources that end in the same `add_media()`.
- `/api/v1/metrics` serves Prometheus metrics (text format 0.0.4, any valid token). Every scrape computes them fresh from the database, `/proc`, the data partition and one AMI connection; no `prometheus_client` dependency.
- List endpoints accept `q` (case-insensitive substring search over the entity's search fields), `limit` (>= 1; without it all matches are returned) and `offset` (>= 0). The body stays a JSON array; the `X-Total-Count` header carries the number of matches before `limit` and `offset`. Without parameters the result is unchanged.
- The HTML UI and the API call the same service layer.

**MCP for AI assistants.**
- `POST /api/mcp` is a Model Context Protocol server (streamable HTTP, protocol versions 2025-03-26 to 2025-11-25). It is stateless and answers with JSON only: no SSE stream and no `Mcp-Session-Id`, so `GET` and `DELETE` return 405. The protocol is implemented in `phonix/mcp.py`, not with the `mcp` SDK, so it adds no runtime dependency.
- Clients authenticate with the same bearer tokens; the session cookie is not accepted. Every MCP request is a POST, so a read-only token is enforced per tool: it gets only the read tools in `tools/list`, and write tools return a tool error. Requests with an `Origin` header for another host name are rejected (DNS rebinding); the port is not compared, because nginx passes `Host` without it.
- Tools: `list_*`, `get_*`, `create_*`, `update_*` (partial: only the given fields change), `delete_*` for phones, providers, call groups, conferences, applications, IVR menus, business hours and AMI users, plus `set_phone_enabled` / `set_provider_enabled` / `set_ivr_menu_enabled`; `get_business_hours_status`, `set_business_hours_mode` and `set_business_hours_special` (immediate); `list_media` and `delete_media` (uploads only over REST: audio as base64 in JSON-RPC is impractical), `create_media_from_text` and `list_tts_voices` (text-to-speech server); `list_settings_groups`, `get_settings`, `update_settings`; `get_status`, `get_pending_changes`, `preview_apply` (paths and components only, never file content), `apply_changes`; `tail_log` (`asterisk`, `system`, `web` or `monitor`, at most 1000 lines; an error in the OCI image, which has no log files). `originate_call` (the click-to-call above) is listed and callable only for tokens with `allow_calls`.
- The `list_*` tools accept the optional `q`, `limit` and `offset` (as in the REST API) and return `{"items": [...], "total": N}`, where `total` is the number of matches before `limit` and `offset`.
- Secrets are never returned, and an empty secret keeps the stored one, as in the REST API. Changes are audited as `<user> (mcp)`.

### Tech choices
- **Python libraries:** installed from Alpine `apk` packages wherever available, rather than pip wheels. This avoids Rust and musl build problems on arm64 and x86.
  - Packages: `py3-fastapi`, `uvicorn`, `py3-pydantic`, `py3-sqlalchemy`, `py3-alembic`, `py3-jinja2`, `py3-argon2-cffi`, `py3-itsdangerous`, `py3-multipart`, `py3-babel`.
  - Any library that is missing from Alpine is vendored as pure Python.
- **Development:** `pyproject.toml` with tooling `uv`, `ruff`, `mypy` and `pytest`. A local virtualenv is fine for development.
- **AMI client:** a small asyncio client in-tree, `phonix/ami.py`, about 200 lines, so there is no heavy dependency.
- **Init system:** OpenRC. Services: `phonix-firstboot`, `phonix-apply`, `asterisk`, `phonix-web`, `nginx`, `chronyd`, `dropbear` (optional), `crond`.

## 2. Data model (SQLite, Alembic-migrated)

Alembic migrations replace `convert_config()`. WAL mode is enabled and foreign keys are on.

The table list below is derived from the old `config.xml` schema:
- `settings`: a key/value table for singletons, with typed Pydantic models per group.
  - Groups: `system.*` (hostname, domain, timezone, tonezone, language, ntp servers), `network.*`, `webgui.*`, `rtp.*`, `pjsip.*` (transports, NAT external address, local nets), `iax.*`, `voicemail.*`, `email.*` (SMTP for msmtp), `features.*` (transfer/pickup codes, parking), `media.*`, `tts.*` (text-to-speech server).
- `users`: web admins.
  - Columns: id, username, argon2 hash, role (`admin` only in v1), `must_change_pw`.
- `phones`: id, tech (`pjsip|iax|external`), extension (unique), name, secret, callerid, codecs, language, `voicemail_enabled`, `vm_pin`, `vm_email`, `nat`, `qualify`, `dtmf_mode`, `max_contacts`, `external_number` (for tech=`external`), `ui_order`.
- `providers`: id, tech (`pjsip|iax`), name, host, port, username, secret, `auth_user`, `from_domain`, `from_user`, `register`, codecs, `outbound_callerid`, enabled.
  - `provider_dialpatterns`: provider_id, pattern, position. The pattern keeps the legacy syntax `[add+][strip|]pattern` (e.g. `49+0|X.`), so legacy configs import 1:1.
  - `provider_incoming_map`: provider_id, did_pattern, target_type, target_id.
- `callgroups` (ring groups): id, extension (optional), name, description, strategy (`ringall|linear`), ringlength, public access/name.
  - `callgroup_members`: group_id, position, and either phone_id or member_group_id (a nested call group, exactly one of the two is set).
  - A nested call group stands for its phones, resolved recursively; a phone that turns up again rings only once. In a `linear` group a nested group is one step that rings all its phones at once, for the parent's ring length, else the nested group's, else 20 s. Loops (a group containing itself directly or through other groups) are refused by the service layer; the generator also skips them. Unanswered calls go to the mailbox of the first resolved phone.
  - API/MCP: `members` is the ordered list of `phone:<id>` / `callgroup:<id>`. `member_ids` (phones only) is still returned and accepted for pre-1.9 clients: if it disagrees with the phones in `members`, its phones win and the nested groups of `members` follow them.
- `conference_rooms`: id, extension, name, pin, admin_pin.
- `applications`: custom dialplan snippets.
  - Columns: id, extension, name, logic (plain text dialplan), enabled.
  - Seed rows port the 7 defaults from the old `config.xml`: Read extension, Read IP, Echo, Milliwatt, Voicemail, Call forwarding, Weasels. Their `applicationlogic` is base64-decoded and rewritten for Asterisk 22 syntax.
- `ivr_menus`: id, name, extension (optional, unique), public access/name, enabled, the announcement (`prompt_mode` `upload` with `prompt_media_id`, or `sound` with an Asterisk sound name; `prompt_text` is only a recording script), `timeout` (seconds to wait for a key), `repeats`, `direct_dial`, and the destinations for "no key" (`timeout_dest_type/_id`) and "unknown key" (`invalid_dest_type/_id`).
  - `ivr_options`: menu_id, key (`0-9`, `*`, `#`, unique per menu), label, dest_type, dest_id, position (the order of the announcement).
- `business_hours`: id, name, optional `feature_code` (unique), and the destinations while open and while closed.
  - `business_hours_ranges`: hours_id, weekday (0 = Monday), start, end (`HH:MM`, the end is exclusive, `24:00` = midnight).
  - `business_hours_holidays`: hours_id, date, name, yearly.
  - `business_hours_specials`: hours_id, position (list order), name, enabled (the configured on/off switch), optional `start` / `end` dates (both or neither, inclusive; none = always), yearly (may cross the new year), optional `feature_code` (unique like the other feature codes), dest_type, dest_id. The destination may be other business hours, one level deep: the target has no special periods itself and is not the object itself.
- `ami_users`: id, username, secret, permit network, read/write permission sets.
- `media_files`: id, kind (`moh|vm_greeting|ivr_prompt`), filename, stored path.
- `audit_log`: ts, user, action, object, diff. This is new, so changes can be traced.
- `dirty`: subsystem, `since`. This drives the "Apply changes" banner.

Every importable entity (phones, providers, call groups, rooms, applications, AMI users) carries a nullable `legacy_uniqid` column. It stores the old `uniqid`, for example `SIP-PHONE-…`, so that cross-references and import/export round-trips stay stable.

Uniqueness of extensions across phones, call groups, rooms, applications, IVR menus and the feature codes of business hours is enforced in the service layer.

Destinations (provider incoming routes, IVR keys, business hours) are `(type, id)` pairs, handled in `phonix/services/destinations.py`: `phone`, `callgroup`, `application`, `conference`, `ivr`, `hours`, `voicemail` (the mailbox of a phone), and the actions `repeat` (IVR only) and `hangup` without id. Deleting an object removes the routes and IVR keys that led to it; the fixed destinations of menus and business hours fall back to hanging up. The validation rules port `verify.inc`: extension and dialpattern checks, hostname, IP and so on.

## 3. Feature scope

### v1: parity minus hardware
The menu keeps the original structure from `usr/www/fbegin.inc`.

**System**
- General: hostname, domain, DNS, timezone, NTP, language, admin password, mDNS announcement (avahi-daemon without D-Bus via the `phonix-mdns` service: `<hostname>.local` and `_https._tcp`; not in the OCI image)
- Network: DHCP or static; the IPv4 fields come from the old app, and IPv6 is optional
- Storage: status of the data partition and usage
- Firmware update: upload a signed bundle, or check online
- Backup/Restore: a `.tar.zst` with a versioned `config.json`, media, TLS and ACME files (see section 3b)
- Legacy `config.xml` import and export (see section 3a)
- Factory defaults
- Reboot

**Accounts**
- Phones: PJSIP, IAX, External
- Providers: PJSIP trunk with registration, IAX trunk

**Dialplan**
- Applications, edited in a monospace auto-growing textarea (Tabler's Autosize; CodeMirror is not part of the Tabler-supported libraries) with server-side validation of every line
- Call groups
- IVR menus (auto attendant): an announcement (uploaded audio, converted to 8 kHz, or an Asterisk sound), then one destination per key. The key options are reordered by drag and drop (or with up/down buttons); the order is the order of the announcement, and "Write from options" turns it into a recording script in the prompt language. Settings: wait time, repeats, destinations for no key and for an unknown key, direct dialling of extensions. A menu reached from outside (`ivr-<id>-pub`) only allows public direct dial and gives callers no transfer feature. A read-only call flow tree and a test call (Originate into the menu) are on the edit page. Text-to-speech is postponed (piper changed its licence and maintainers; no espeak-ng stopgap); `prompt_mode` leaves room for it.
- Business hours: weekly time ranges, holidays (one-off or yearly), special periods and a destination while open and while closed; usable as the destination of incoming routes and IVR keys. The dialplan uses `GotoIfTime()` (whose end minute is inclusive, so `17:30` becomes `17:29`) and compares the date for holidays and special periods.
  - Precedence for calls and the lamp: 1. the permanent mode (open/closed from the UI, `PUT /api/v1/business-hours/{id}/mode`, MCP `set_business_hours_mode`); 2. the temporary override of the out-of-office key; 3. the first special period in list order that is on and whose dates include today; 4. holidays (closed); 5. the weekly ranges. Levels 3–5 are the *automatic* state. Forced open or closed (1, 2) uses the normal open/closed destination even while a special period applies.
  - Special periods send calls to their own destination. A period pointing to business hours takes that object's effective state; any other destination counts as closed. They are switched on and off immediately, without an apply: on the list and edit pages, `PUT /api/v1/business-hours/{id}/special/{sid}` (`{"active": bool}`), MCP `set_business_hours_special`, and their optional feature code (announces "activated" / "de-activated"). `GET /api/v1/business-hours/{id}/status` and `get_business_hours_status` return the state, the `reason` (`forced`, `override`, `special` with the period's name and the end of its occurrence, `holiday`, `schedule`) and the periods with their switch and whether they apply today.
  - The out-of-office key (the feature code of the business hours) always inverts the effective state: without a manual mode it sets a temporary override to the opposite of the automatic state; an existing override or permanent mode is removed (back to automatic); a permanent mode equal to the automatic state is removed and replaced by an override to the opposite. An override ends at midnight or as soon as the automatic state reaches its value. Announcements: "enabled" (now open), "disabled" (now closed), "cancelled" (back to automatic). A permanent mode set from the UI/API/MCP clears the override.
  - Lamps: BLF hints in `internal` on the feature codes (`Custom:phonix-hours-<id>`, `INUSE` = closed; `Custom:phonix-special-<sid>`, `INUSE` = switched on). No ringing/blinking states, since pressing a blinking BLF key on a Snom picks up instead of dialling.
- Transfers/Features: feature codes and parking
- Numbers with a leading `+`: the settings group `outgoing` (`plus_replacement`, default `00`, empty = off, digits/`*`/`#`, max 16) is edited on *Dialplan → Transfers & Parking*. Every `phone-<ext>` context gets `_+X.` → `Goto(phone-<ext>,<replacement>${EXTEN:1},1)`, so the number runs through the internal numbers and the dial patterns again. A dial pattern cannot match `+` because `+` separates its prefix to add. This also covers click-to-call and call forwarding.
- The printable dialplan view stays

**Services**
- Email notifications (msmtp)
- Voicemail, with voicemail-to-email
- Voicemail and missed call e-mails in the e-mail language of each phone (*E-mail language*, default: the phone's language). The built-in texts are translated through the catalogs, and dates are formatted for the language. *Services → Voicemail* overrides the subject and text per language and resets a language to the built-in text; a text equal to the built-in one is not stored, so it keeps following the translations.
- Conferencing (ConfBridge)
- Media: music-on-hold upload, custom voicemail greetings, IVR announcements, prompt language
  - Recording by phone (`services/recording.py`): the UI rings a SIP/IAX phone by AMI Originate into the static context `phonix-record` with the channel variable `PHX_REC=<32 hex token>`; no other context includes or jumps to it. Asterisk records to `<data>/media/incoming/<token>.wav` (`Record()`, `#` ends, at most 300 s), plays it back and asks with `vm-review` (1 save, 2 listen, 3 record again). The progress is in AstDB `phonix-rec/<token>` (`recording`, `review`, `saved`, `cancel`, `hangup` from the `h` extension). The page polls every 2 s (`POST /services/media/record/<token>`); on `saved` the web app reads the file (no symlinks, regular file, at most 64 MB) and stores it through `add_media()`, then removes file and state. Not answered after the ring timeout + 15 s, or pending for more than 30 min: discarded.
  - Kinds: `ivr_prompt` (named) and `vm_greeting`. What a pending recording is for (kind, name, user) is in `<data>/state/recordings/<token>.json`, out of Asterisk's reach.
  - Text to speech (`services/tts.py`): an external server with the RestfulTTS API, settings group `tts` (`url` http/https, `token` secret sent as bearer, default `voice`, `speed` 0.5–2, `timeout` 5–300 s). `GET {url}/api/v1/voices`, `POST {url}/api/v1/synthesize` with `{"text", "voice" | "language", "speed", "format": "wav8"}`; without a voice the system prompt language is sent. Text at most 2000 characters, answers at most 16 MB within the timeout in total (not per read); redirects are refused (they would carry the token elsewhere); the database transaction is committed before the request, so a slow server never holds the SQLite write lock. Changing `url` without a new `token` drops the stored token (`settings_api.SECRET_BOUND`, also in the UI). The audio goes through `add_media()` (kinds `ivr_prompt`, `vm_greeting`). Synthesis happens when the announcement is created, never during a call. UI: *Services → Media* (create, **Listen** stores a preview under `<data>/state/tts-preview/` for 10 min, at most 20 files) and the IVR editor (speaks the recording script `prompt_text`, named after the menu). REST `POST /api/v1/media/tts`, `GET /api/v1/tts/voices`; MCP `create_media_from_text`, `list_tts_voices`. No text is kept with the media file, so an announcement cannot be regenerated from its text yet.
  - `media/incoming` is the only place Asterisk writes to below `media`: mode 2770, owner `phonix`, group `asterisk`, created by the web app on demand (it is not part of backups; a restore replaces `media` and the next recording recreates it).

**Status**
- Dashboard: system info, uptime, registrations, active calls
- Registrations and channels, from AMI
- Logs: a tail of the Asterisk, system, web application and monitor logs, live via SSE. Logs are kept in RAM (appliance overlay, tmpfs in LXC) and rotated by size every 15 minutes (`/etc/periodic/15min/phonix-logrotate`). The OCI image writes no log files: everything goes to the container output, and the page (and MCP `tail_log`) say so instead.
- CPU and network graphs, drawn with uPlot

**Advanced**
- RTP port range
- PJSIP: transports, NAT and external IP, TLS/SRTP toggle
- IAX
- AMI users
- GUI options (inactivity logout; `expand_advanced` is a legacy field kept for `config.json` compatibility and not shown)

**Console**
- A small Python TUI on tty1 replaces `rc.initial`. It offers: show IP, set LAN IP, reset password, factory reset, reboot.

### 3a. Legacy `config.xml` import and export (v1)
**Goals**
- Existing AskoziaPBX boxes can migrate onto PhonixPBX.
- Configs can be exported back to a box running the old firmware, for rollback or interop.
- Import is the primary use case. Export is best-effort, for the features both systems share.

**Code**
- All of this lives in `phonix/legacy/`:
  - `parse.py`: XML to a typed intermediate model
  - `upgrade.py`: older config versions to 2.1
  - `mapping.py`: intermediate model to and from the DB
  - `exporter.py`: DB to config.xml 2.1
- Parsing uses `defusedxml`, to protect against XXE and entity bombs.
- List tags follow `$listtags` in `legacy/.../etc/inc/xmlparse.inc`.
- Defaults come from `$defaults` in `globals.inc`.

**Version handling**
- Files with `<version>` below 2.1 are upgraded first. The `convert_config()` steps relevant to the supported subset are ported from `legacy/.../etc/inc/config.inc`.
- Files with a version newer than 2.1 are rejected with a clear error.

**Mapping (import → PhonixPBX)**

| Legacy | PhonixPBX |
|---|---|
| `system` (hostname, domain, dnsserver[], timezone, tonezone, timeservers, webgui/language) | `settings.system.*`, `settings.network.dns` |
| `system/username`, `password` (plaintext) | `users` row with an argon2 hash. The old password is kept, because the owner knows it, and is flagged in the report. |
| `interfaces/lan` (dhcp, ipaddr, subnet, gateway) | `settings.network.*`, with the interface name mapped to the detected NIC |
| `sip/phone[]` | `phones` tech=pjsip. Mapped fields: secret, callerid, codecs[] (order kept), natmode → rtp_symmetric/force_rport/rewrite_contact, dtmfmode, qualify, voicemail, language, `manualattributes` → kept as a note |
| `iax/phone[]` | `phones` tech=iax |
| `external/phone[]` | `phones` tech=external |
| `sip/provider[]` | `providers` tech=pjsip, generating registration, auth and aor. Also imports `dialpattern[]`, `incomingextensionmap[]` and `outgoingcalleridmap` |
| `iax/provider[]` | `providers` tech=iax |
| `dialplan/callgroup[]` | `callgroups` + members, resolved by legacy uniqid; the export writes nested call groups as their phones |
| `dialplan/application[]` | `applications` with base64-decoded logic. Known Asterisk 1.8 constructs, such as `MeetMe` → `ConfBridge`, are rewritten automatically. Anything else is flagged "review needed". |
| `dialplan` callparking/featuremap/transfer and pickup keys | `settings.features.*` |
| `conferencing/room[]` | `conference_rooms` |
| `voicemail`, `notifications/email` | `settings.voicemail.*`, `settings.email.*` |
| `services/rtp`, `services/sip`, `services/iax` | `settings.rtp/pjsip/iax.*` |
| `services/manager/manager-user[]` | `ami_users` |

**Not imported, but reported**
- `analog`, `isdn`, `skinny`, `virtual/fax`, `analog/fax`, `interfaces/dahdi-*`, `redfone-gateway`, `storage/disk`, `thirdparty/humbug`, `dyndns`, `dnsupdate`, `manual-file`, `shellcmd`, `earlyshellcmd`, `captiveportal`
- Any ISDN or analog provider that phones or dialpatterns depend on. For these, the importer suggests replacing the provider with a SIP gateway.

**Import flow**
1. **Dry run.** Parse, upgrade and map the file, run the full validation, and produce an `ImportReport`:
   - counts of items to create, update and skip
   - per-item warnings and errors
   - the sections that were dropped
   - extension conflicts with existing data
2. **Choose a mode.**
   - **Replace** (default): wipe the importable tables, then import. An automatic backup is taken first.
   - **Merge**: matches on `legacy_uniqid`, then on extension. On a conflict the item is skipped and reported.
3. **Commit.** Everything is written in a single DB transaction, which marks all subsystems dirty. The user then reviews the changes and clicks Apply.

**Export (PhonixPBX → config.xml 2.1)**
- `exporter.py` performs the inverse mapping:
  - `legacy_uniqid` is reused when present; otherwise a uniqid is generated in the old format.
  - Application logic is base64-encoded again.
- PhonixPBX-only settings are left out and listed in the export report: TLS/SRTP, nftables, multiple users, and PJSIP-only options. IVR menus, business hours and the incoming routes that lead to them have no legacy equivalent and are reported as omitted.
- PJSIP options that chan_sip understands, such as codecs, nat, qualify and dtmf, are mapped back.
- The file contains plaintext secrets, as the old format requires. For that reason:
  - only admins can export
  - the UI shows a warning
  - the export is recorded in `audit_log`

**Interfaces**
- **UI:** the System → Backup/Restore page gets a "Legacy AskoziaPBX" card.
  - Import uses a Dropzone upload, then shows the dry-run report in a Tabler table with warnings and errors badges, then asks for the mode and confirmation.
  - Export is a download button with its report.
- **API:** `POST /api/v1/legacy/import?dry_run=true|false&mode=replace|merge` with the file as request body (at most 10 MB; `dry_run` defaults to true; returns the report, 422 when it has errors), `GET /api/v1/legacy/export` (refused for read-only tokens even though it is a GET, because of the plaintext secrets).
- **CLI:** `phonix legacy import <file> [--dry-run] [--merge]` and `phonix legacy export <file>`.
- **First-boot convenience:** if `PHXBOOT/config.xml` is present on the boot partition at first boot, it is imported automatically (Replace), the report is saved to `state/legacy-import-report.json` and shown on the dashboard until an administrator dismisses it, and the file is renamed to `config.xml.imported`. This matches where users put the file on old boxes, under `conf/config.xml` on partition 1, which is also checked.

**Tests**
- **Fixtures:** every `legacy/target/*/config.xml`, plus realistic synthetic configs covering each section, older versions such as 2.0, and malformed or hostile XML.
- **Golden import:** fixture → DB → JSON snapshot.
- **Round trip, export side:** `import(export(db)) == db` for the supported subset.
- **Round trip, import side:** `export(import(xml))` keeps every supported field. The XML is compared semantically, ignoring ordering and `lastchange`.
- **Generator check:** the generators run on imported fixtures, and the resulting Asterisk config loads cleanly in the CI Asterisk container.

### 3b. Backup and restore (v1)

A backup holds the configuration as a document, not as a database file. This keeps backups restorable on newer releases, and a restore never replaces the database under running processes.

**Archive** (`<data>/backups/phonix-backup-YYYYmmdd-HHMMSS.tar.zst`, mode 0600, the newest 10 are kept)
- `manifest.json`: `{"format": 2, "version", "created", "config_version"}`. Format 1 archives (a raw `phonix.db` snapshot) are refused.
- `config.json`: the configuration document (below).
- `media/`: the files that `config.json` lists, with their sha256.
- `tls/`, `acme/`: certificate, key and ACME account, without the `acme/lock` file.
- Not included: the Asterisk database (`asterisk/`, runtime state), voicemail messages (`spool/`), `secrets.json` (machine-local keys), SSH host keys and logs.

**config.json** (`phonix/services/configdoc.py`, schema in `docs/config-schema.json`)
- `{"format": "phonix-config", "version": 5, "phonix_version", "created", "settings", "users", "providers", "phones", "callgroups", "conferences", "applications", "ivr_menus", "business_hours", "ami_users", "media"}`. Version 3 added the IVR menus and business hours (optional sections) and the `allow_calls` flag of API tokens. An IVR menu names its announcement by media path (`prompt_media`), since media files have no document id; menus and business hours that point to each other are created first without destinations, which are set in a second pass. Version 4 replaced `callgroups[].member_ids` by `members` (`phone:<id>` / `callgroup:<id>`); call groups are created in dependency order, contained groups first. Version 5 added `business_hours[].specials` (with the configured `enabled` switch; periods pointing to business hours are resolved in the second pass); version 4 documents are read unchanged.
- Contains every secret: SIP/IAX passwords, voicemail PINs, manager secrets, the e-mail password, the argon2 hashes of the web users and the sha256 hashes of their API tokens.
- Objects have document-local `id`s that references use (`dial_provider_id`, `member_ids`, `incoming_routes[].dest_id`, …); the field names are those of the REST API. Settings groups that are missing keep their current values.
- Unknown keys are errors. `version` is bumped whenever the document changes incompatibly; older documents are upgraded step by step (`UPGRADES`), newer ones are refused with the release that made them. A test keeps the checked-in schema current.

**Restore** (`phonix/services/backup.py`)
1. Extract into a temporary directory below `/data` and validate the manifest, `config.json` and the media checksums.
2. Dry run the import and show a preview (counts, files). Nothing has changed so far.
3. Take a safety backup of the current state.
4. In one transaction, wipe all configuration tables (not the audit log) and create every object through the service layer, so the same validation as in the UI applies. The first error aborts the restore.
   The admin can keep parts of the current system (`configdoc.KEEP_PARTS`):
   - `network` (default on): the `network` and `firewall` groups plus `ssh_enabled`/`ssh_password_hash` of the `system` group, so a backup from another system or network cannot lock the admin out.
   - `users`: web users and their API tokens.
   - `certificate`: the `tls`/`acme` directories and the `acme` group.
5. Swap in the `media`, `tls` and `acme` directories (with the modes and group from first boot), then commit. If the commit fails, the directories are swapped back.
6. Reset the business hours runtime state in AstDB (`hours.reset_runtime()`): the database ids start again at 1, so entries of the replaced configuration would attach to the restored objects. The families `phonix-hours`, `phonix-hours-tmp` and `phonix-special` are deleted (permanent modes and temporary overrides are cleared, every business hours object is automatic again), every special period switch is written from its restored `enabled`, and the lamps are refreshed. Best effort: when Asterisk is not running, the restore still succeeds and the minute sync removes entries of unknown ids later. `phonix config import` and a legacy import in replace mode do the same after their commit.
7. Apply the configuration and reload nginx when a certificate was restored.

Sessions store the user name next to the user id, so a session whose id now belongs to another user ends.

**Interfaces**
- **UI:** System → Backup/Restore. An upload or a stored backup first shows the preview with the parts to keep; Restore needs a confirmation.
- **CLI:** `phonix backup create [file]`, `phonix backup restore <file> [--dry-run] [--restore-network] [--keep-users] [--keep-certificate]`, and `phonix config export|import|schema` for the bare `config.json` (an import checks the media files in place and leaves the apply to the user).

### Later phases (not v1)
- Fax to email via `res_fax_spandsp`, if Alpine's Asterisk build includes it
- Phone auto-provisioning; the old version was snom-only
- DynDNS
- Multiple admin roles
- A hardware plugin hook for DAHDI

### Dropped
Everything hardware-specific listed in the confirmed decisions, plus Humbug analytics, Skinny, the m0n0wall captive portal leftovers, the `exec.php` web shell, and the `ajax.cgi` CGI.

## 4. Security (best practice; replaces the plaintext admin/phonix)
**First login and passwords**
- On first boot, a random admin password is generated and shown on the console banner and TUI. If the user prefers, a factory default plus a forced change on first login can be used instead. Either way, there is no fixed known password in the image.
- Passwords are hashed with argon2id.

**Sessions**
- Session cookies are `HttpOnly`, `Secure` and `SameSite=Strict`.
- CSRF tokens protect forms.
- Login attempts are rate-limited, by nginx and in the app.

**HTTPS**
- HTTPS is the default. A self-signed certificate is generated on first boot. Port 80 redirects to HTTPS (except `/.well-known/acme-challenge/`). Users can upload their own certificate or have one issued and renewed automatically by an ACME CA (Let's Encrypt, ZeroSSL or a custom directory) through the `lego` client, validated over HTTP-01 or DNS-01 with a DNS provider API. `phonix cert renew` runs daily from cron and renews 30 days before expiry; PhonixPBX decides when to renew and calls `lego run --renew-force --no-random-sleep --force-cert-domains`. lego 5 (≥ 5.2, current DNS provider APIs) is only in Alpine edge: the images and containers install a pinned edge build (`LEGO_VERSION` in `image/lib/common.sh`, `Containerfile`, `dev/Containerfile`). ACME state written by lego 4 (e.g. from a restored backup) is converted with `lego migrate` before the next run.

**Secrets**
- SIP and IAX secrets are stored in the DB.
- They are never rendered back in clear text in the UI. The UI offers write-only fields with a "regenerate" action.
- Generated `.conf` files are mode 0640, owned by `asterisk:phonix`.

**Firewall and SIP**
- An nftables ruleset is generated from settings.
- The SIP port is open only to the configured networks and providers. An optional fail2ban equivalent bans IPs on Asterisk security events from AMI; the monitor re-reads its settings at most a minute after a change, keeping its counters.
- The AMI port 5038 is opened only for the IPv4 networks of the manager users (loopback excluded); Asterisk binds to all addresses only when such a user exists.
- `alwaysauthreject` is enabled, and anonymous inbound is off by default.

**Updates**
- Update bundles are signed with ed25519. The public key is baked into the image.
- The upload request only stores the bundle in `/data` and starts `phonix update install --remove` detached (like the ACME request), so a long install never hangs on an HTTP request or a proxy timeout. The job writes its state (`running` with the step verify/backup/write and a percentage while hashing, `installed`, `error`) to `<state>/update-job.json`; *System → Firmware* polls it and allows one job at a time. A job whose process is gone is shown as interrupted.
- Only a newer version than the running one is installed (`is_newer`, PEP 440), checked in `verify_bundle` right after signature and board, before the checksums; `phonix update install --force` (console only, never the web upload) allows the same or an older version. The root helper does not compare versions.
- While an `installed` job waits for the reboot (job version ≠ running version, same `boot_id`; containers keep the host's `boot_id`), every page except *System → Firmware* shows a *Reboot required* banner with a reboot button.
- LXC upgrades the packages in place, so the files on disk change while the old version keeps running until the container restarts. The web app therefore reads all Jinja templates into memory at start (`DictLoader`; `PHONIX_DEV=1` keeps reading from disk), and the old routes never render templates of the new version.
- After *Reboot into the new firmware* the waiting page polls `/system/ping` until the system went down and answered twice, then opens *System → Firmware*, which compares the running version with the installed one once: success, or (after a reboot, `boot_id` changed) a rolled-back trial boot.

## 5. UI: Tabler 1.7.1 with PhonixPBX branding
**Rendering and assets**
- Pages are server-rendered with Jinja2 and use **htmx 4.x** for partial updates: list tables, the apply banner, status polling, and the SSE log tail.
- Code is written against htmx 4 semantics only: fetch-based requests, explicit attribute inheritance, and the htmx 4 event names and extension API. No htmx 1/2-era extensions or patterns.
- **Use the libraries Tabler 1.7.1 itself ships and supports**, at the versions Tabler pins in its `libs.json`/`package.json`, rather than adding third-party alternatives:
  - **Tom Select**: every non-trivial select. Examples: codec multi-select with ordering, call group member picker, provider/phone pickers, timezone search, incoming-DID target picker.
  - **Dropzone**: uploads for firmware/update bundles, MOH, greetings, IVR announcements and the backup restore. A `<div data-dropzone data-url>` works inside another form (the IVR editor), where a nested `<form>` is not allowed.
  - **IMask**: masked inputs where useful, such as IP/netmask, port ranges and PINs.
  - **Litepicker**: date ranges for log and CDR filters, if needed.
  - **Tabler Icons** (webfont/SVG sprite): all icons.
- **Exception: charts use uPlot** (MIT, vendored from npm by `scripts/vendor-update.sh`), not the ApexCharts that Tabler bundles: ApexCharts is no longer open source since 5.1.0 (free only below USD 2M revenue, no redistribution in platforms). `data-chart="cpu|network"` with `data-chart-url` (JSON samples), `data-height` and `data-interval`; `phonix.js` builds the uPlot options (colours resolved from the Tabler/phonix CSS variables, so light and dark theme work), polls the URL with `setData`, and follows the card width with a `ResizeObserver`. The live legend below the plot replaces a tooltip.
- Library glue lives in a single `phonix/web/static/phonix.js`. It initializes the Tabler libs on `htmx:after:swap` (the htmx 4 event), so swapped-in fragments get Tom Select, uPlot charts and similar applied. It also tears them down before swap to avoid leaks. Drag and drop uses SortableJS, vendored from Tabler's libs. Rows (IVR key options) sit in a container with Tabler's `data-sortable` plugin (JSON options in the attribute, auto-initialised by `tabler.min.js`, so `Sortable.min.js` loads before it), dragged only by their `[data-sortable-handle]` so the inputs stay usable, plus `data-move` up/down buttons on `[data-sortable-item]` rows for keyboards; the rows are submitted in page order. A multi Tom Select with `data-tom-sortable` (call group members via `ordered_select`, codecs) gets a Sortable on its chips in `phonix.js` (`forceFallback`, because Tom Select cancels mousedown on items); on drop it reorders `ts.items` and calls `updateOriginalInput()`, which re-appends the selected options in that order, so the form posts the new order.
- The sidebar links use `hx-boost`, limited to the menu (`<ul class="navbar-nav">`): they fetch the page and swap `#page` only (`target`/`select` `#page`, `outerHTML`), never `<body>`, because htmx 4 runs the `<script>` tags of swapped content again. `#page` is also the `hx-history-elt`, so the back button restores it the same way. A response without `#page` (an error page, the print view, a redirect to the login) is loaded as a normal page by `phonix.js`. Everything else (forms, downloads, the top bar, `/api/docs`) stays a normal navigation. What a full load sets up once (`#tab-…` links, the reboot watcher, `data-sortable`) also runs for a swapped `#page`.
- **Lists: search and paging.** Entity lists share one pattern (all entity lists except the audit log, which follows):
  - The view is in the address: `q` (case-insensitive substring over the list's search fields, the same `search_fields` the REST API and MCP use), `page` (1-based; out of range is clamped to the last page) and `per_page` (25/50/100/`all`, default 50; anything else falls back to 50; the audit log offers no `all`). `list_page()` in `routes/ui/common.py` reads them and returns a `ListPage` (`phonix/services/listing.py`); entity lists filter and slice in Python after the existing `list_*` query, so their order is kept.
  - Markup comes from `macros/lists.html` (`list_header`, `list_footer`, `no_matches`). The card header holds a GET form with the search field, the count (`ngettext` "N phones", or "M of N" while searching) and *Per page*; the card footer shows "51–100 of 500" and Tabler `.pagination` (first, last, current ±2, gaps as `…`) and is left out when everything fits on one page. Matches are wrapped in `<mark>` by the `highlight` filter, which escapes first.
  - Region convention: `<div id="list-<name>">` wraps the table (or the empty or no-match state) and the footer; `<span id="list-<name>-count">` sits in the header outside it. The search field (`hx-trigger="input changed delay:300ms, search"`, `hx-replace-url`), the page size select (`change`, `hx-push-url`) and the page links (`hx-push-url`) all GET the list URL with `hx-select`/`hx-target` on the region and `hx-select-oob` on the count, so the field keeps focus and caret. Enter submits the form as a normal GET (also the fallback without JavaScript). `phonix.js` drops the defaults (empty `q`, `page=1`, the default `per_page` in `data-list-search`) from the pushed address. History restore re-GETs the URL through `#page`, so back, reload and shared links show the same view.
  - Status polling sits inside the region and passes the current `q`/`page`/`per_page`, so it only reports the rows shown. Toggling or deleting a row replaces or removes just that row; counts and footer catch up on the next search or page change.
  - "No phones yet" (an empty list) stays the empty state; a search without matches shows "No phones found" with *Clear search*.
- There is no Node build at runtime. Tabler 1.7.1, its libraries above, and the htmx 4 dist files are vendored into `phonix/web/static/vendor/`. The pinned version and SHA256 checksum of each are recorded in `vendor/VERSIONS`, and a `scripts/vendor-update.sh` script refreshes them.

**Layout**
- Tabler's vertical sidebar layout is used, with the menu tree from section 3.

**Branding**
- Tabler's CSS variables are overridden in `phonix/web/static/phonix.css`. Color values come from `legacy/.../usr/www/gui.css`:

| Use | Value |
|---|---|
| Primary, navbar and header background (`--tblr-primary`, `.navbar` background) | `#435370` |
| Sidebar background | `#435370` with a `#9D9D9D` border; the active item uses `#687BA4` (white text on the legacy grey `#9D9D9D` fails WCAG contrast) |
| Accent / info | `#687BA4` |
| Light info backgrounds | `#D9DEE8` |
| Danger | `#A12A2A`, with background `#FFD9D1` |
| Links | `#0000CC` |
| Muted / inactive | `#777777` |

- New PhonixPBX logo and favicon as SVG (`phonix/web/static/img/`), drawn in the legacy colours; the original
  Askozia artwork is not shipped (trademark).
- The footer reads "PhonixPBX" and the version.

**Usability**
- Dark mode uses Tabler's built-in theme with the same primary color.
- Forms use Tabler form controls, with validation errors shown inline next to each field.

**User manual**
- An end-user and administrator manual in English and German is written in Markdown under `docs/manual/` (Hugo, own minimal layout on top of the vendored Tabler CSS, no external theme). Its chapter paths mirror the menu URLs (`/accounts/phones` → `docs/manual/content/<lang>/accounts/phones.md`; the dashboard `/` → `status/summary`), plus *Getting started*, *Using your phone* (dial codes for phone users) and *Reference* (CLI, API/MCP, AskoziaPBX migration, troubleshooting).
- `scripts/help-build.sh` renders it with a pinned Hugo version into `phonix/web/static/help/`, which is committed like the vendored assets, so packages and images need no Hugo. CI (`scripts/help-build.sh check`) fails when the committed output is stale.
- It is served without login under `/help/` (English) and `/help/de/` (German): by nginx from the static directory on the appliance, by a `StaticFiles` mount in development.
- Every page below the sidebar layout has a help button (`?`) in the page header that opens the chapter of the active menu item in a new tab, in the manual language matching the interface language (English for languages without a manual). Create/edit forms link to the chapter's `#edit` section; templates set `help_page`/`help_anchor` blocks to point elsewhere. Section anchors are explicit (`{#edit}`) and identical in all languages. `tests/test_help.py` checks that every menu item has a chapter in every manual language and that all linked anchors exist.

**Translation**
- The web interface uses gettext catalogs in `phonix/locale/<lang>/LC_MESSAGES/messages.po`. They are read and compiled in memory at runtime by `phonix/i18n.py`, so there is no `.mo` build step.
- Languages: English (source), English (UK) (uses the English text), German, French, Spanish, Italian, Dutch, Danish, Swedish, Polish, Portuguese (Brazil), Russian, Japanese. These are the languages of the legacy GUI that also exist as prompt languages.
- Each administrator chooses a language under *Preferences* (user menu). If none is chosen, English is used.
- The JSON API, CLI, console, logs and audit log stay English.
- `scripts/i18n.sh update` extracts the strings marked with `_()`/`N_()` in Python and Jinja and merges them into the catalogs. `tests/test_i18n.py` fails when the template is out of date, a catalog is incomplete, or placeholders/HTML tags differ.
- The old `.po` files under `usr/www/locale/` (18 languages) are kept in `legacy/` as translation memory.

## 6. Repository layout
```
legacy/                  # entire old tree, untouched (git mv)
phonix/                 # Python package
  core/                  # settings, db, models, migrations (alembic/), validation
  services/              # phones, providers, dialplan, system, network, backup, update
  generators/            # one module per output; templates/ with Jinja2 .conf.j2
  ami.py
  web/                   # FastAPI app: routes/ (ui + api/v1), templates/, static/ (phonix.css, img/, vendor/)
  legacy/                # config.xml import/export: parse, upgrade, mapping, emit
  cli.py                 # `phonix` CLI: apply, migrate, user, legacy import/export, tui
  tui.py
tests/                   # unit, golden generator outputs, API tests, integration
system/                  # files installed into image: openrc init.d/, nginx conf, doas.d, libexec scripts, nftables
packaging/apk/APKBUILD   # builds phonix as an Alpine package (abuild, signed)
image/                   # image build: build.sh, per-board profiles (rpi-arm64, pc-amd64, pc-x86), partition layout
dev/                     # docker compose dev env (Asterisk 22 + app, hot reload)
docs/SPEC.md             # this spec (committed)
docs/manual/             # user manual (Hugo, en/de); built into phonix/web/static/help/ by scripts/help-build.sh
.github/workflows/       # lint, test, build apk + images, QEMU boot smoke test
```

## 7. OS image and boot (best practice: A/B, read-only root)

### Partition layout
The layout is the same on every board. The data partition is grown to fill the disk on first boot.

| # | Label | Filesystem | Size | Contents |
|---|---|---|---|---|
| 1 | `PHXBOOT` | FAT32 | 256 MB | Bootloader files and the kernel and initramfs for slot A and slot B. On the Pi, also the firmware, `config.txt` and `autoboot.txt`. |
| 2 | `rootA` | squashfs | 512 MB | Root filesystem for slot A |
| 3 | `rootB` | squashfs | 512 MB | Root filesystem for slot B |
| 4 | `PHXDATA` | ext4 | rest of disk | Persistent data, see below |

`PHXDATA` holds:
- `/data/phonix.db`
- voicemail, recordings and media
- logs (optional)
- SSH host keys and the TLS certificate
- `machine-id`

### Root filesystem
- The squashfs root is mounted read-only with an overlay (tmpfs) on top for `/etc` and `/var` runtime state. The initramfs handles this.
- Persistent paths are bind-mounted from `/data`: `/var/spool/asterisk`, `/var/lib/asterisk/sounds/custom` and `/etc/phonix`.

This replaces the old `/cf` and `/offload` scheme and meets the goals of the `storage_system.txt` design: data survives upgrades and factory reset is detectable.

### Rootfs build
**Building in a container**
- The image is built reproducibly in an Alpine container using `apk --root /rootfs --arch <arch> --initdb add ...`.
- The Alpine release is pinned, for example 3.22, and the build is driven from a package list in `image/profiles/*.packages`.
- Post-install scripts for foreign architectures run through qemu-user binfmt.

**Our own packages**
- The `phonix` package is built with abuild and signed with the project key.
- It installs into the rootfs from a local repository.

**Asterisk**
- Use `asterisk` and its submodules from Alpine (`asterisk`, `asterisk-sounds-*`, `asterisk-sample-config` excluded).
- If the pinned Alpine release is not on version 22 LTS, carry our own APKBUILD in `packaging/apk/asterisk/`.

**Kernels**
- Raspberry Pi uses `linux-rpi`.
- PCs use `linux-lts`.

**Images and firmware**
- Images are assembled with `sfdisk`, `mkfs.vfat` + `mtools` and `mksquashfs`. No root or loop devices are needed, so the build runs in CI.
- Output is `phonix-<ver>-<board>.img.zst`, plus an update bundle `phonix-<ver>-<board>.update` (a signed tar of rootfs.squashfs, kernel and initramfs) and SHA256SUMS.
- The Pi also uses `raspberrypi-bootloader` firmware.

### Boards

**`rpi-arm64`**
- Supported models: Pi 3B+, 4, 5 and Zero 2 W (aarch64).
- A/B switching uses the Pi firmware's `tryboot` mechanism: `autoboot.txt` with `[all] tryboot_a_b=1` (Pi 4/5) selects the boot partition set.
- On a Pi 3, slots are switched by rewriting `cmdline.txt` `root=` with a boot counter in the initramfs.

**`pc-amd64`**
- Boots via UEFI and legacy BIOS using GRUB 2 (`grub-efi` + `grub-bios`) in hybrid mode.
- A/B switching uses `grubenv` (`boot_slot`, `boot_tries`) with fallback.
- The image works on bare metal, in VMs and on USB/SATA/NVMe drives.

**`pc-x86` (best effort)**
- Same as amd64, but BIOS only with i686 `linux-lts`.
- Requires SSE2: Alpine's x86 packages (Python, Asterisk, nginx, OpenSSL) use SSE2 instructions. Geode-based boards (PC Engines ALIX/WRAP) are not supported.
- Built in CI and boot-tested in QEMU. It ships only if Alpine x86 still packages `asterisk`; otherwise it is dropped with a note.

**`lxc-amd64`, `lxc-arm64` (system containers)**
- The same root filesystem, built by the same pipeline (`CONTAINER=1`, `LOADER=none` in the profile). There is no kernel, initramfs, boot loader or A/B slot. OpenRC is init, and the runlevels have no device, module, sysctl, clock, ACPI or health check services.
- Output: a rootfs tarball (Proxmox VE CT template, `lxc-create -t local` with a small metadata tarball) and an Incus/LXD unified image.
- `/data` is a directory or volume in the container. `/var/spool/asterisk` is a symlink to `/data/spool`.
- `phonix-ramlog` (first in the boot runlevel, containers only) mounts tmpfs on `/var/log` (64 MB) and `/tmp` (128 MB), as `localmount` does not run in containers. The log of an in-place update goes to `/var/lib/phonix/update.log`, because the update is activated by a restart.
- Network, host name and DNS belong to the container host, and `phonix apply` skips `system:network` and `system:hostname` (`phonix.services.platform`). `priv mark-good` refuses, and factory reset empties `/data` at the next start.
- Updates are in place, with a package bundle (see Updates). The root filesystem is writable and keeps its apk database, and `apk-tools` is installed (`lxc-<arch>.packages`). There is no rollback: the UI asks for a snapshot on the container host, and a configuration backup is saved first.

**OCI image (`ghcr.io/phonixpbx/phonix`)**
- Multi-arch application container from `Containerfile`: Alpine packages, the `phonix` wheel and the same file layout, with board `oci-<arch>`.
- No init system. `system/container/entrypoint` runs under tini and supervises busybox syslogd, Asterisk, the web interface (user `phonix`, unix socket), the monitor and nginx.
- No log files: web and monitor write to stdout, Asterisk logs to syslog (`logger.conf` for `platform == "oci"`, a generator fact), which `syslogd -n -O -` writes to the container output, and nginx logs errors to stderr with the access log off.
- Root actions go through doas to `system/container/priv`, which only does what belongs inside a container.

### Updates
- The UI uploads a bundle. *Check now*, and with *Check automatically* a daily job (`/etc/periodic/daily/phonix-update` → `phonix update check --auto`), ask the update information URL (GitHub "latest release" API or `{"version", "url"}`) for the newest release; the answer is kept in `state/update-check.json` and the dashboard shows a notice while it is newer than the running version. From a GitHub release the asset `phonix-<version>-<board>.update` of the running board becomes a direct download link (*System → Firmware*, `phonix update check`), next to the release page; only `https://` URLs are kept. Nothing is downloaded automatically. The ed25519 signature is verified in Python with `cryptography`, using `py3-cryptography`.
- `priv install-update` writes the squashfs and kernel to the inactive slot and sets the next boot to try that slot.
- LXC boards get a package bundle instead: `packages.tar` (an apk repository with every package of the release; the index is unsigned because the manifest covers the whole tar), `world` and `image-info`.
  - `priv install-update` replaces `/etc/apk/world` and runs `apk upgrade --available` against that repository only.
  - It then runs `rootfs-fixup`, the same script the image build uses, to set up the overlay, console, nginx, runlevels, `/etc/asterisk` and the symlinks to `/data` again.
  - The new version starts when the container restarts. OCI containers are still updated by replacing the image.
- After boot, `phonix-healthcheck` confirms the web app and Asterisk are up and then marks the slot good. If that fails, the bootloader rolls back.
- RAUC was considered and rejected for v1 to keep the image small. The scheme above is roughly 150 lines and fully under our control.

### First boot
- Generate SSH host keys, the TLS certificate, the admin password and the machine-id on `/data`.
- Run DB migrations and seed defaults: one LAN interface on DHCP, the default conference room 2663, and the default applications.

## 8. Implementation phases
Each phase ends shippable and tested.

1. **Repo reset:** `git mv` everything into `legacy/` and add the new skeleton: pyproject, ruff/mypy/pytest, CI lint+test, and `docs/SPEC.md` with this content.
2. **Core:**
   - DB models, Alembic, settings models, and validation ported from `legacy/.../etc/inc/verify.inc`
   - Service layer and `phonix` CLI (migrate, user, apply)
3. **Generators:**
   - Jinja2 templates producing `pjsip.conf`, `iax.conf`, `extensions.conf` (ported logic from `legacy/.../etc/inc/extensions.inc`), `voicemail.conf`, `confbridge.conf`, `musiconhold.conf`, `features.conf`, `rtp.conf`, `manager.conf`, `logger.conf`, `modules.conf` (explicit noload/minimal) and `indications.conf`
   - Non-Asterisk outputs: `msmtp.conf`, `/etc/network/interfaces`, nftables, `chrony.conf`, `TZ`
   - Golden-file tests
   - **Legacy import/export (section 3a):** `phonix/legacy/` with the parser, the version upgrade, the mapping and the emitter, plus the CLI commands. Covered by fixture, round-trip and "imported config loads in Asterisk" tests.
4. **Web:**
   - FastAPI app, auth, the Tabler base layout with branding, and CRUD pages per menu section
   - The apply workflow, the AMI client, status pages and the `/api/v1` OpenAPI
   - The Legacy import/export card and its API endpoints
5. **Dev environment:** docker compose with Alpine, Asterisk 22 and the app; SIPp register/call integration tests that reuse the scenarios in `legacy/testsuite/PERF_TEST_FILES/`.
6. **Packaging and image:**
   - APKBUILD, OpenRC/nginx/doas/libexec system files, and `image/build.sh` for the 3 boards
   - A/B update, healthcheck and first boot, including the automatic import of `config.xml` from the boot partition
7. **Hardening and release:**
   - nftables and ban-on-auth-failure
   - Backup/restore
   - The console TUI
   - Docs: installation, flashing with Raspberry Pi Imager or `dd`
   - Tagged release with artifacts

## 9. Verification
- **Unit tests:** `pytest` covers validation, services and generators. Generator tests compare output against golden `.conf` files in `tests/golden/`.
- **Config validity:**
  - CI starts Asterisk 22 in a container with the generated configs.
  - It checks `asterisk -rx "pjsip show endpoints"` and `dialplan show` for expected contexts and extensions.
  - It fails on any `ERROR` in the startup log.
- **API and UI tests:**
  - FastAPI `TestClient` covers auth, CSRF, CRUD and apply.
  - Playwright smoke tests cover login and the add-phone → apply flow.
- **Call flow tests:** in docker compose, SIPp registers two PJSIP phones, places a call between them, dials the echo test and joins a conference. It also calls an IVR menu (answered, announcement, waiting for a key), runs a key and the timeout path through `Local` channels, routes a call through business hours into the menu, and presses the out-of-office key and a special period key (`Local` channels into `internal`), checking the AstDB entries, the hint states and the routing over AMI.
- **Image boot tests:**
  - QEMU boot smoke tests in CI: `qemu-system-x86_64` (UEFI with OVMF, and BIOS), `qemu-system-i386`, and `qemu-system-aarch64 -M virt` for the arm64 rootfs (the generic kernel variant).
  - Each test waits for HTTPS 200 on the login page and for Asterisk to be up.
  - It then runs an update to slot B, reboots, and runs a forced-failure rollback test.
- **Hardware:** a manual checklist on a Pi 4 and a Pi 5. Flash the image, boot it, open the web UI, register a softphone, call the echo test, update and roll back.

## 10. Implementation notes (as built)

- Python runtime on Alpine 3.24 is 3.14; development and CI also run the suite on 3.10 (`dev/constraints-alpine-3.24.txt` pins the Alpine package versions).
- Asterisk 22 has no `Macro()`; the generated dialplan uses `Gosub` subroutines (`sub-dial`, `sub-try`, `sub-checkcf`, `sub-missed-call`). Missed call mails run as a hangup handler.
- E-mails: `voicemail.conf` has one global subject and body, so Asterisk only puts the message details into them (`key=value` lines) and hands the mail to `mailcmd=/usr/libexec/phonix/notify voicemail`. `phonix.notify` replaces subject and text with the mailbox language's texts, keeps the recording attached and sends it with msmtp; a mail it cannot rewrite is sent unchanged. The hangup handler calls `notify missed <email> <target> <cause> <callerid>`. Languages, names and texts come from the generated `/etc/asterisk/phonix-notify.json`, so the sender needs neither the database nor gettext.
- PJSIP providers register with `line=yes`; several accounts on the same host share one inbound context that dispatches on the account user name (legacy behaviour).
- The legacy "direct dial SIP URI" context (`outgoing-uri`) is not ported (toll-fraud risk, no PJSIP equivalent without a fixed domain).
- Swagger UI at `/api/docs` loads its assets from jsDelivr and therefore needs internet access; `/api/v1/openapi.json` is always available.
- The system setting `ui_language` (imported from legacy `config.xml`) is no longer shown; the interface language is a per-administrator preference.
- IVR menus and business hours are generated twice: `ivr-<id>` / `hours-<id>` for internal callers and `-pub` variants for calls from providers, which only include `public-direct-dial` and ring targets without the transfer feature (`t` instead of `tT`).
- The business hours mode is runtime state, not configuration: `DB(phonix-hours/<id>)` holds `open` or `closed` (no entry = automatic). The services read and write it with the `database get/put/del` CLI commands over AMI, so it changes without an apply, survives restarts (`astdbdir` is on `/data`) and is not part of backups (a restore clears it, see 3b).
- More runtime state in AstDB: `phonix-hours-tmp/<id>` = `<open|closed>:<YYYY-MM-DD>`, the temporary override of the out-of-office key and the day of the press (valid only on that day and while the automatic state differs from it; routing ignores and deletes an expired entry); `phonix-special/<sid>` = `1` / `0`, the runtime switch of a special period. Without an entry the dialplan uses the configured `enabled` as default. The AstDB switch is authoritative at runtime; changes from the UI/API/MCP write both AstDB and SQLite, a key press writes AstDB only. Deleting business hours, or removing a special period in a save, deletes their AstDB entries (best effort), so a reused id starts clean.
- Business hours dialplan (`phonix/generators/dialplan.py`): Gosub contexts `hours-<id>-auto` (special periods in order, holidays, ranges; returns `<open|closed>-<sid or 0>`), `hours-<id>-state` (permanent mode, override, automatic; returns `<open|closed>-<forced|override|auto>-<sid or 0>` and purges an expired override) and `hours-<id>-lamp` (sets `Custom:phonix-hours-<id>`); the routing contexts `hours-<id>` / `-pub` call `hours-<id>-state`. A key press refreshes the lamps of the object and of every object whose special period points to it, before the announcement (core sounds `enabled`, `disabled`, `cancelled`, `activated`, `de-activated`; `HOURS_SOUNDS`).
- `phonix monitor` runs a thread `hours-sync` (`phonix/services/hours_sync.py`) every minute and once at start: it removes expired overrides and AstDB entries of unknown ids, copies special switches changed by phones from AstDB to SQLite, writes missing switches from SQLite to AstDB (new periods, restored backups), and sets the `Custom:` device states, which also covers an Asterisk restart and schedule boundaries. Python (`hours.status()`) and the dialplan implement the same rules and must agree; where they ever differ, routing wins and the lamp follows within a minute.
- `GotoIfTime()` includes the end minute and rejects `24:00`, while PhonixPBX stores exclusive ends: the generator writes `17:30` as `17:29` and `24:00` as `23:59`.
- Business hours run in the configured time zone (`settings.system.timezone`), passed explicitly: `GotoIfTime(...,<zone>?open)` and `STRFTIME(${EPOCH},<zone>,%Y-%m-%d)` in the dialplan, `hours.local_now()` in Python. Asterisk and the web/monitor processes read `/etc/localtime` once at startup (musl and Asterisk do not notice the replaced symlink), so a changed zone reaches business hours with the next apply (a dialplan reload) instead of the next restart. Other local times in Asterisk (voicemail, CDR) still follow `/etc/localtime` and change after a restart.
- Dial options: `tThH` for internal callers and `th` for calls from providers (the callee may transfer, only internal parties get the disconnect code `*0`); outgoing provider calls use `TH`. The `h`/`H` options are what activates `features.conf`'s `disconnect` code.
- PJSIP registration timers: phone AORs get `default_expiration`/`minimum_expiration`/`maximum_expiration` from the SIP settings, provider registrations use the default expiry. With *DNS SRV lookups* off, providers without a port get the transport's standard port (5060, TLS 5061) written into `server_uri`/`contact`, because PJSIP has no SRV switch and an explicit port skips the SRV lookup (RFC 3263).
- Click-to-call and the IVR test call use AMI `Originate` (async, 30 s ring time) into `phone-<ext>` or `ivr-<id>`, so the dialplan decides what the phone may reach.
