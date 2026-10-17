---
title: "Audit Log"
weight: 50
description: "Who changed what and when: every configuration change and administrative action."
---
*Status → Audit Log* records every change to the configuration and every administrative action, with the time and the administrator who did it. Use it to find out when a setting was changed, by whom, and what the value was before.

## Columns {#columns}

| Column | Meaning |
|---|---|
| Time (UTC) | Time of the action, in UTC regardless of the time zone of the PBX. |
| User | Who did it: the name of an administrator. API requests appear under the owner of the token, MCP requests as `<name> (mcp)`. Actions from the command line appear as `cli`, from the console menu as `console`, and the initial setup as `setup` or `firstboot`. |
| Action | What was done, for example `create`, `update`, `delete`, `enable`, `disable`, `apply`, `backup`, `restore`, `password`, `certificate`, `firmware`, `originate` (a call placed through the API) or `legacy-import`. |
| Object | Kind and name of the object concerned, for example a phone with its extension, a provider or a settings group. |
| Details | For changes: the fields that changed, as `field: old → new`. Passwords, PINs and other secrets are never shown; for them the log only says *(changed)*. |

## Browsing {#paging}

The newest entries are at the top, 50 per page. Use *Older* and *Newer* at the bottom of the list to page through the history.

## What is recorded {#recorded}

- Creating, changing, enabling, disabling and deleting phones, providers, call groups, applications, IVR menus, business hours, conference rooms, media files and manager users.
- Changes to settings pages, via the web interface, the API or MCP.
- Switching the mode of business hours.
- Applying the configuration, backups and restores, imports, firmware updates, certificates, factory reset.
- Administrators and API tokens: created, deleted, passwords and language changed.
- Calls placed through the API or MCP (click-to-call).

Logins are not recorded in the audit log. The audit log stays on the PBX; it is not part of backups.
