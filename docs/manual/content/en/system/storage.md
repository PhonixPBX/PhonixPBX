---
title: "Storage"
weight: 30
description: "Usage of the data partition and the space taken by configuration, media, backups and voicemail."
---
*System → Storage* shows how full the data partition is and what takes up the space. The page only displays information; there is nothing to set.

## Data partition {#data-partition}

All data that has to survive a reboot or a firmware update lives on the data partition, mounted at `/data`: the configuration database, voicemail, media files, backups, the TLS certificate and the SSH keys. The system software itself is on a separate, read-only partition.

The bar shows the used space in percent and turns red above 90 %. Below it you see the used and the total size.

On a disk image the data partition is enlarged to fill the whole disk on first boot. In a container, `/data` is a directory or volume of the container; its size is set on the container host.

## Usage by content {#usage}

The table lists the size and location of the main areas:

| Content | What it is |
|---|---|
| Configuration database | `phonix.db`, the complete configuration. |
| Media (music on hold, greetings) | Audio files uploaded under [Services → Media]({{< relref "/services/media.md" >}}). |
| Backups | The backup archives of [System → Backup/Restore]({{< relref "/system/backup.md" >}}). |
| Voicemail | Voicemail messages of all mailboxes. |
| Asterisk database | Runtime state of Asterisk, for example call forwarding set from the phones. It is not part of a backup. |

## Freeing space {#free-space}

If the partition fills up:

- Delete old backups under [System → Backup/Restore]({{< relref "/system/backup.md#backups" >}}) after downloading the ones you want to keep. At most 10 backups are kept anyway.
- Delete media files that are no longer used under [Services → Media]({{< relref "/services/media.md" >}}).
- Have users delete old voicemail messages, or shorten the maximum message length under [Services → Voicemail]({{< relref "/services/voicemail.md" >}}).
