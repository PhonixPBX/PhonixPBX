---
title: "API tokens"
weight: 80
description: "Bearer tokens for the REST API and MCP: read-only or read-write, expiry, permission to place calls."
---
*Advanced → API tokens* creates the tokens that scripts, monitoring systems and AI assistants use to access PhonixPBX over the [REST API]({{< relref "/reference/api.md" >}}) (`/api/v1`) and the Model Context Protocol (MCP, `/api/mcp`). A token replaces a user name and password: whoever has it gets the access it grants, without logging in.

Tokens take effect immediately, without applying.

## Create a token {#create}

| Field | Meaning | Default |
|---|---|---|
| Name | A name that says where the token is used, e.g. `monitoring`. Up to 64 characters. | — |
| Access | **Read-only**: only GET requests and the read-only MCP tools; voicemail and conference PINs are not included in the answers. **Read-write**: may also create, change and delete objects, change settings and apply the configuration. | Read-only |
| May place calls | Allows click-to-call: ringing a phone and dialing a number from it (`POST /api/v1/calls`, MCP tool `originate_call`). This works with read-only tokens too, since it is the only write action they get. | off |
| Expires in (days) | Validity in days, 1–3653. Empty: the token does not expire. | empty |

Click **Create**. The token is shown **once** in a green box, together with example commands. Copy it now with **Copy** and store it in a safe place, for example the secret store of the tool that uses it. PhonixPBX only keeps a hash and cannot show the token again; if it is lost, create a new one.

> Calls placed through a token with *May place calls* may cost money when they go to external numbers. Grant it only to tools that need it.

## Manage tokens {#manage}

The table lists every token:

| Column | Content |
|---|---|
| Name | The name, and below it the first characters of the token, which identify it without revealing it. |
| Access | *read-only* or *read-write*, and *calls* when the token may place calls. |
| Status | *active*, *disabled* or *expired*. |
| Owner | The administrator who created the token. When the administrator is deleted, the token is deleted too. |
| Created, Last used, Valid until | When the token was created, last used, and until when it is valid (*unlimited* without expiry). |

The search field above the list finds tokens by name, prefix or owner; how searching and paging work is described in [Lists]({{< relref "/getting-started/_index.md#lists" >}}).

Use the toggle to disable a token temporarily and to enable it again. Use the trash icon to delete it for good. Delete tokens that are no longer used, and check *Last used* to find them.

Good practice:

- One token per tool or script, so that you can revoke one without affecting the others.
- Read-only whenever the tool only needs to read, e.g. for monitoring.
- An expiry for tokens given to third parties or used for a limited time.

## Using a token {#using}

Send the token in the `Authorization` header of every request:

```sh
curl -H "Authorization: Bearer phx_..." https://pbx.example.com/api/v1/status
```

AI assistants and other MCP clients connect to `https://<your PBX>/api/mcp` with the same header, for example:

```sh
claude mcp add --transport http phonix https://pbx.example.com/api/mcp --header "Authorization: Bearer phx_..."
```

The interactive API documentation is available at `/api/docs` on your PBX. Endpoints, MCP tools and examples are described in the [API reference]({{< relref "/reference/api.md" >}}). Tokens can also be managed on the command line with `phonix token` (see [CLI]({{< relref "/reference/cli.md" >}})).
