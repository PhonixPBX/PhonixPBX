---
title: "Factory Defaults"
weight: 60
description: "Erase all configuration and data and start again as on the first boot."
---
*System → Factory Defaults* erases the complete configuration and all data and restarts the system. Afterwards it behaves exactly as on its first boot. Use it before you pass a system on, or to start over from scratch.

## What is erased {#erased}

A factory reset erases the whole data partition (`/data`):

- the configuration with all phones, providers, users and settings,
- voicemail messages and media files,
- **all backups** stored on the system,
- the TLS certificate, the SSH host keys and your SSH keys.

The installed PhonixPBX version stays. The reset cannot be undone.

> Download a backup under [System → Backup/Restore]({{< relref "/system/backup.md" >}}) before you reset, if you might need the configuration again.

## Resetting {#reset}

1. Type `RESET` (in capital letters) into **Type RESET to confirm**.
2. Click **Reset and reboot**. Active calls are interrupted.

What happens next depends on how PhonixPBX runs:

- **Disk image:** the system reboots and formats the data partition during boot.
- **LXC/Incus container:** the container restarts and empties `/data` before PhonixPBX starts.
- **OCI container:** the container stops. `/data` is erased when the same container starts again; with a restart policy such as `--restart unless-stopped` this happens right away. If you remove the container instead and create a new one, the data volume is not erased.

After the reset, the system starts as on its first boot: it creates a new database, a new self-signed certificate and a **new random administrator password**. Read the password from the console menu (on a container: the container console or, for the OCI image, the container log) and log in as described in [Getting started]({{< relref "/getting-started/_index.md#login" >}}). On a disk image the network is set to DHCP on the first network card again, so the system may get a different address.

The console menu offers the same reset, see [Console menu]({{< relref "/getting-started/_index.md#console" >}}).
