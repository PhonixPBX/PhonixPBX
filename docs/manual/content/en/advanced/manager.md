---
title: "Manager (AMI)"
weight: 40
description: "Users for the Asterisk Manager Interface, with permitted networks and permissions."
---
*Advanced → Manager (AMI)* manages users of the Asterisk Manager Interface. AMI is a TCP interface on port 5038 that lets external software monitor and control the PBX, for example CTI tools, operator panels, wallboards or call recording solutions. PhonixPBX uses AMI internally as well; you only need to add users here for external software.

For your own scripts the [REST API]({{< relref "/reference/api.md" >}}) with an [API token]({{< relref "/advanced/tokens.md" >}}) is usually the better choice: it has finer access control and does not expose Asterisk internals.

Changes become active after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

> An AMI user with write permissions can control the whole PBX, including placing calls and running Asterisk commands. Create users only for software you trust, grant only the permissions it needs and restrict the permitted networks as far as possible.

## User list {#list}

The list shows each manager user with its **Permitted networks** and its **Read** and **Write** permissions. Without users, AMI is only used internally.

Click **Manager user** above the list to add a user, the user name to edit one, and the trash icon to delete it.

## User settings {#edit}

| Field | Meaning | Default |
|---|---|---|
| Username | Login name, up to 64 letters, digits, `_` and `-`. The names `phonix` and `general` are reserved. | — |
| Secret | Password of the user, 4–128 characters without spaces, quotes, `;` or backslashes. When editing, leave it empty to keep the stored secret. | — |
| Permitted networks | The networks the user may connect from, one CIDR per line, e.g. `192.168.1.0/24`. At least one is required. | `127.0.0.1/32` |
| Read permissions | Event classes the user receives. | `all` |
| Write permissions | Action classes the user may execute. | none |

The permissions are the Asterisk AMI classes: `all`, `system`, `call`, `log`, `verbose`, `command`, `agent`, `user`, `config`, `dtmf`, `reporting`, `cdr`, `dialplan`, `originate`, `agi`, `cc`, `aoc`, `test`, `security` and `message`. The documentation of the external software usually lists which classes it needs. Typical examples:

- A wallboard or monitoring tool: read `call`, `agent`, `reporting`; no write permissions.
- A click-to-dial tool: additionally write `originate`.
- `system`, `command` and `config` allow restarting Asterisk, running CLI commands and reading configuration files. Grant them only when really needed.

## Network access {#network}

As long as all users only have loopback networks (`127.0.0.0/8`), AMI listens on the PBX itself only. As soon as a user has another permitted network, AMI listens on all interfaces, and each user can only log in from its own permitted networks.

With the firewall enabled under [Advanced → Firewall]({{< relref "/advanced/firewall.md" >}}), port 5038 is opened only for the IPv4 networks in the *Permitted networks* of the manager users (loopback networks need no rule). IPv6 networks are not opened, because AMI listens on IPv4 only. The firewall rules change when you apply. AMI traffic, including the secret, is not encrypted; only use it in a trusted network.
