---
title: "REST API and MCP"
weight: 20
description: "Automating the PBX: bearer tokens, the REST API under /api/v1, click-to-call, AskoziaPBX import, Prometheus metrics and the MCP server."
---
PhonixPBX can be controlled by scripts and other programs. The **REST API** under `/api/v1` offers the same functions as the web interface and uses the same rules for validation, secrets and pending changes. The **MCP server** under `/api/mcp` makes the same functions available to AI assistants. Both are reached over HTTPS on the address of the web interface.

## Interactive documentation {#docs}

- `https://<pbx>/api/docs` – Swagger UI with every endpoint, its parameters and response format. You can try out requests there: click *Authorize* and enter a token. The footer of the web interface links here (*API*).
- `https://<pbx>/api/v1/openapi.json` – the OpenAPI schema, for example to generate a client.

## API tokens {#tokens}

Scripts authenticate with a **bearer token**. Create tokens under [Advanced → API tokens]({{< relref "/advanced/tokens.md" >}}) or with [`phonix token create`]({{< relref "/reference/cli.md#token" >}}). A token starts with `phx_` and is shown only once, when it is created; the PBX stores only a hash of it.

| Property | Meaning |
|---|---|
| Access *Read-only* | GET requests only, and only the read-only MCP tools. Voicemail and conference PINs are left out of the responses. |
| Access *Read-write* | All requests: create, change, delete, apply. |
| *May place calls* | Allows click-to-call (`POST /api/v1/calls`, MCP tool `originate_call`), independently of the access: a read-only token with this flag can place calls but not change the configuration. Off by default – calls to external numbers can cost money. |
| Expires in (days) | Validity; empty means the token never expires. |

A token acts with the rights of the administrator who owns it, and its changes appear under that name in the [audit log]({{< relref "/status/audit.md" >}}). Disabled and expired tokens are rejected. Repeated requests with wrong tokens are blocked for a few minutes, like failed logins.

Send the token in the `Authorization` header:

```sh
curl -H "Authorization: Bearer phx_..." https://pbx.example.com/api/v1/status
```

While the PBX uses its self-signed certificate, add `-k` to `curl` or, better, install a proper certificate.

## Objects {#resources}

Every kind of object has the same five endpoints:

| Path | Objects |
|---|---|
| `/api/v1/phones` | Phones |
| `/api/v1/providers` | Providers |
| `/api/v1/callgroups` | Call groups |
| `/api/v1/conferences` | Conference rooms |
| `/api/v1/applications` | Dialplan applications |
| `/api/v1/ivr-menus` | IVR menus |
| `/api/v1/business-hours` | Business hours |
| `/api/v1/ami-users` | Asterisk manager users |

- `GET <path>` lists all objects, `GET <path>/{id}` returns one.
- `POST <path>` creates an object (answer `201`).
- `PUT <path>/{id}` replaces an object: send all fields, as for a create.
- `DELETE <path>/{id}` deletes it (answer `204`).

Passwords and other secrets are never returned. When you send an empty secret, the stored value stays unchanged.

Call groups list their members in `members`, in ringing order: `"phone:<id>"` for a phone, `"callgroup:<id>"` for a contained call group, for example `{"name": "Support", "members": ["callgroup:2", "phone:5"]}`. A group that would contain itself is refused with `422`. The older field `member_ids` (phone ids only) is still returned and accepted.

## Settings {#settings}

`GET /api/v1/settings/{group}` returns a settings group, `PATCH /api/v1/settings/{group}` changes only the fields you send. The groups are `system`, `network`, `rtp`, `sip`, `iax`, `voicemail`, `email`, `features`, `media`, `firewall`, `acme`, `gui` and `update`.

## Applying changes {#apply}

Changes over the API become pending changes, just like in the web interface:

- `GET /api/v1/pending` lists the areas with changes that are not applied yet.
- `POST /api/v1/apply` applies them and returns the changed files, the reloaded components and any errors.

## Business hours {#business-hours}

- `GET /api/v1/business-hours/{id}/status` – whether the business hours are open right now, why (`reason`: `forced`, `override`, `special`, `holiday` or `schedule`), the live mode and the special periods with their switch (`active`) and whether they apply today.
- `PUT /api/v1/business-hours/{id}/mode` with `{"mode": "auto"}`, `"open"` or `"closed"` – switches the mode immediately, without apply.
- `PUT /api/v1/business-hours/{id}/special/{special_id}` with `{"active": true}` or `false` – switches a special period on or off immediately, without apply.
- The special periods themselves are the `specials` list of the business hours (create and update, then apply).

## Click-to-call {#calls}

`POST /api/v1/calls` with `{"extension": "21", "number": "0441234567"}` rings the SIP or IAX phone with that extension. When it is answered, the PBX dials the number from that phone, with the phone's own outgoing rules and caller ID. The answer is `202` with `"status": "ringing"`. The number may contain digits, `*`, `#` and `+`. The token needs *May place calls*.

```sh
curl -H "Authorization: Bearer phx_..." -H "Content-Type: application/json" \
     -d '{"extension": "21", "number": "0441234567"}' https://pbx.example.com/api/v1/calls
```

## AskoziaPBX config.xml {#legacy}

- `POST /api/v1/legacy/import` imports an AskoziaPBX `config.xml` sent as the request body (at most 10 MB). By default (`dry_run=true`) it only returns the preview; `dry_run=false` imports. `mode=replace` (the default, a backup is created first) or `mode=merge` selects the [mode]({{< relref "/reference/askozia.md#modes" >}}). The answer is the import report as JSON (`ok`, `dry_run`, `mode`, `source_version`, `counts`, `dropped_sections`, `items`, `summary`); `422` when the file has errors, in which case nothing is imported. Apply the changes afterwards.
- `GET /api/v1/legacy/export` returns the configuration as `config.xml` (`application/xml`). The file contains all passwords in plain text, so read-only tokens get `403`, although it is a GET request. Every export is recorded in the audit log.

```sh
curl -k -H "Authorization: Bearer phx_..." --data-binary @config.xml \
     "https://pbx.example.com/api/v1/legacy/import?dry_run=false&mode=merge"
```

## Status and Prometheus metrics {#metrics}

- `GET /api/v1/status` returns system information and the Asterisk state (registrations, channels) as JSON.
- `GET /api/v1/metrics` returns metrics in the Prometheus text format; any valid token works, a read-only one is recommended.

The metrics cover the system (uptime, load, memory, data partition, network traffic), Asterisk (up, start time, active calls and channels), registrations of each phone (`phonix_phone_registered`) and provider (`phonix_provider_up`), voicemail messages per mailbox, the TLS certificate expiry and the last ACME request, pending changes and backups. A scrape job:

```yaml
scrape_configs:
  - job_name: phonix
    scheme: https
    metrics_path: /api/v1/metrics
    authorization:
      credentials: phx_...            # read-only API token
    tls_config:
      insecure_skip_verify: true      # only while the PBX uses its self-signed certificate
    static_configs:
      - targets: ["pbx.example.com"]
```

Useful alerts: `phonix_provider_up == 0`, `phonix_asterisk_up == 0`, `phonix_tls_certificate_expiry_seconds - time() < 14 * 86400`.

## Errors {#errors}

| Status | Meaning |
|---|---|
| `401` | No token, or the token is invalid, disabled or expired. |
| `403` | The token is read-only (also for the `config.xml` export), or it may not place calls. |
| `404` | The object does not exist. |
| `422` | Invalid input. The body contains `detail.message` and, per field, `detail.fields`. |
| `429` | Too many failed authentication attempts; wait a few minutes. |

Error messages of the API are always in English.

## MCP for AI assistants {#mcp}

`POST /api/mcp` is a server for the Model Context Protocol (MCP, streamable HTTP transport). With it, an AI assistant such as Claude can read and change the configuration of the PBX on your behalf. It accepts only bearer tokens. Example for Claude Code:

```sh
claude mcp add --transport http phonix https://pbx.example.com/api/mcp \
  --header "Authorization: Bearer phx_..."
```

The tools:

- `list_*`, `get_*`, `create_*`, `update_*` and `delete_*` for phones, providers, call groups, conferences, applications, IVR menus, business hours and AMI users. `update_*` changes only the fields that are given.
- `set_phone_enabled`, `set_provider_enabled`, `set_ivr_menu_enabled`.
- `get_business_hours_status`, `set_business_hours_mode` and `set_business_hours_special` (take effect immediately).
- `list_settings_groups`, `get_settings`, `update_settings`.
- `get_status`, `get_pending_changes`, `preview_apply` (which files and components would change), `apply_changes`.
- `tail_log` – the last lines of the `asterisk`, `system`, `web` or `monitor` log (up to 1000). In an OCI container there are no log files, and the tool returns an error.
- `originate_call` – click-to-call; only offered to tokens with *May place calls*.

A read-only token sees only the reading tools. Secrets are never returned. Changes appear in the audit log as `<name> (mcp)`. Give an assistant only the access it needs – a read-only token is enough to answer questions about the configuration or to analyse logs.
