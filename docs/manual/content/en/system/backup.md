---
title: "Backup/Restore"
weight: 50
description: "Create, download and restore backups, and import or export AskoziaPBX config.xml files."
---
*System → Backup/Restore* creates backups of the complete configuration, restores them on the same or on another system, and migrates the configuration of an old AskoziaPBX.

Make a backup before larger changes and before every update, and keep a copy outside the system: backups are stored on the data partition and are erased by a [factory reset]({{< relref "/system/defaults.md" >}}).

## What a backup contains {#contents}

A backup is a single file `phonix-backup-YYYYmmdd-HHMMSS.tar.zst`. It contains:

- the complete configuration: all settings, phones, providers, call groups, conference rooms, applications, IVR menus, business hours, manager users, and the web users with their API tokens,
- all secrets of that configuration: SIP and IAX passwords, voicemail PINs, manager secrets, the e-mail password, and the password hashes of the web users,
- the media files (music on hold, announcements),
- the TLS certificate with its private key and the ACME account.

> A backup contains passwords and private keys. Store downloaded backups as carefully as the system itself.

Not included are:

- voicemail messages,
- the Asterisk database (runtime state such as call forwarding set from the phones),
- the call detail records (CDR), the audit log and the system logs,
- the SSH host keys, your SSH keys in `/data/ssh/authorized_keys` and the machine-specific keys of the system.

The configuration is stored as a versioned document, not as a copy of the database. A backup can therefore be restored on a newer PhonixPBX release. A backup made by a newer release than the running one is refused.

## Backups {#backups}

The *Backups* card lists the backups stored on the system, newest first, with their size.

The search field above the list finds backups by file name; how searching and paging work is described in [Lists]({{< relref "/getting-started/_index.md#lists" >}}).

- **Create backup** saves a backup of the current state right away.
- The restore icon opens the [restore preview](#restore) for that backup.
- The download icon downloads the file to your computer.
- The delete icon removes the backup from the system.

PhonixPBX keeps the **10 newest** backups and deletes older ones automatically. This includes the backups that are created automatically: before every restore, before an AskoziaPBX import in *Replace* mode, and before a container update. Download the backups you want to keep for longer.

Backups can also be created on the command line with `phonix backup create` (see [Command line]({{< relref "/reference/cli.md" >}})).

## Restoring a backup {#restore}

1. Under *Restore*, drop a backup file (`.tar.zst`, at most 2 GiB) onto the upload field or click it to choose a file. For a backup stored on the system, click its restore icon in the list instead.
2. The backup is checked completely and a preview is shown: when and by which PhonixPBX version it was made, how many objects of each kind it contains, and whether it contains a TLS certificate and an ACME account. Nothing has changed so far.
3. Choose which parts of the current system to keep (see below).
4. Click **Restore** and confirm.

PhonixPBX then saves a backup of the current state (the safety backup), replaces the configuration and the media files, and applies everything right away; there is no separate apply step. The browser reloads the dashboard. If the web users were restored from the backup, log in again with a user and password from the backup.

If anything in the backup is invalid, the restore stops before changing anything. If applying the restored configuration fails, the configuration is restored nonetheless and the error is shown; fix the cause and apply again.

An uploaded file that you do not restore is deleted after 24 hours.

### Parts to keep {#keep}

| Option | Meaning | Default |
|---|---|---|
| Keep the current network, firewall and SSH settings | Keeps *System → Network*, *Advanced → Firewall* and the SSH settings of *System → General Setup* as they are now. Recommended when the backup comes from another system or network: its IP address, firewall rules or SSH settings could lock you out. | on |
| Keep the current web users and API tokens | Keeps the administrators and API tokens of this system. Otherwise the users, passwords and API tokens of the backup replace them. | off |
| Keep the current TLS certificate and ACME settings | Keeps the certificate, its key and the ACME settings of [Advanced → Certificate]({{< relref "/advanced/certificate.md" >}}), for example when the backup comes from a system with another host name. | off |

Everything else, including the media files, is always replaced by the content of the backup.

## Legacy AskoziaPBX {#askozia}

The *Legacy AskoziaPBX* card migrates the configuration of an AskoziaPBX 2.x system. More details on what is converted are in [AskoziaPBX migration]({{< relref "/reference/askozia.md" >}}).

### Import config.xml {#askozia-import}

1. Download `config.xml` from the AskoziaPBX (its backup function), then drop it onto the upload field (at most 10 MB).
2. A preview shows, per section, how many objects are created, updated or skipped, the sections that are not supported and are dropped (analog and ISDN hardware, for example), and a list of warnings and errors per object. Nothing has changed so far.
3. If there are no errors, choose the **Mode**:
   - **Replace current configuration (backup first)**: removes the current phones, providers and so on and imports the file. A backup of the current state is created first.
   - **Merge into current configuration**: adds the objects of the file to the current configuration. Objects that already exist are matched and updated; on a conflict (an extension that is already used, for example) the object is skipped and reported.
4. Click **Import** and confirm.

The import is not applied automatically. Review the imported configuration, then apply the pending changes (see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}})).

### Export config.xml {#askozia-export}

**Export config.xml** downloads the current configuration in the AskoziaPBX format, for example to go back to an AskoziaPBX system. The export is best effort: features that AskoziaPBX does not have, such as IVR menus, business hours, TLS/SRTP and several web users, are left out.

> The exported `config.xml` contains all passwords in plain text, as the old format requires. Every export is recorded in the audit log.
