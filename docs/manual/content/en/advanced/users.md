---
title: "Administrators"
weight: 70
description: "User accounts for the web interface."
---
*Advanced → Administrators* manages the accounts that can log in to the web interface. Every administrator has full access; there are no roles with fewer rights. For scripts and integrations, create an [API token]({{< relref "/advanced/tokens.md" >}}) instead of a shared administrator account.

Changes on this page take effect immediately, without applying. They are recorded in the [audit log]({{< relref "/status/audit.md" >}}) with the name of the administrator who made them, which is a good reason to give every person their own account.

## Administrator list {#list}

The table shows every administrator with the time of the **Last login**. The badge *must change password* marks accounts that have to set a new password at their next login.

The search field above the list finds administrators by user name; how searching and paging work is described in [Lists]({{< relref "/getting-started/_index.md#lists" >}}).

Use the trash icon to delete an administrator. You cannot delete your own account, and the last administrator cannot be deleted. API tokens belong to the administrator who created them and are deleted together with the account.

## Add an administrator {#add}

| Field | Meaning | Default |
|---|---|---|
| Username | Login name: starts with a lowercase letter, then up to 31 lowercase letters, digits, `.`, `_` or `-`. Upper case is converted to lower case. | — |
| Initial password | The first password, at least 8 characters. | — |
| Must change the password at first login | The new administrator has to choose a new password after the first login, so that only they know it. | on |

Click **Add**. Pass the initial password to the new administrator on a secure channel.

## Passwords {#passwords}

Every administrator changes their own password and interface language in their account menu, see [Changing your password]({{< relref "/getting-started/_index.md#password" >}}).

The web interface cannot set the password of another administrator. If someone has forgotten their password, delete the account and add it again, or set a new password on the command line with `phonix user passwd <name>` (see [CLI]({{< relref "/reference/cli.md" >}})).

The web server limits the number of login attempts per address to slow down password guessing.
