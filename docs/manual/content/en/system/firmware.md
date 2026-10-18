---
title: "Firmware"
weight: 40
description: "Installed version, checking for updates and installing signed update bundles, with A/B slots and rollback."
---
*System → Firmware* shows the installed version, checks whether a newer release is available and installs signed update bundles. How an update works depends on how PhonixPBX runs: as a disk image (Raspberry Pi, PC), as an LXC/Incus system container, or as an OCI container (Docker, Podman). Your configuration and data are kept in every case.

## Installed firmware {#installed}

| Field | Meaning |
|---|---|
| Version | The running PhonixPBX version. |
| Board | The hardware or container type the system was built for, for example `rpi-arm64`, `pc-amd64`, `lxc-amd64` or `oci-amd64`. An update bundle must be built for the same board. |
| Boot slot | Disk images only: the system slot that is running, `A` or `B`. |
| Platform | Containers only: *LXC / Incus system container* or *OCI container (Docker / Podman)*. |

## Check for updates {#check}

| Field | Meaning | Default |
|---|---|---|
| Update information URL | Where the latest version is looked up. It must start with `https://`. Either a GitHub "latest release" API URL, or a URL that returns JSON of the form `{"version": "1.4.0", "url": "https://…"}`. | `https://api.github.com/repos/PhonixPBX/PhonixPBX/releases/latest` |
| Check automatically | Look up the latest version once a day. | off |

**Save** stores the two settings (no apply needed). **Check now** queries the URL and tells you whether you run the latest version or which newer version is available, with a download link. With *Check automatically* on, the PBX does the same once a day, at a random time within an hour after the daily maintenance jobs start.

When a check – automatic or manual – finds a newer version, the [dashboard]({{< relref "/status/summary.md#notices" >}}) shows the notice *PhonixPBX X is available. Update the system.* until that version is installed. The check only reports; it does not download or install anything: download the update bundle and upload it as described below. The system needs internet access for it.

## Updating a disk image {#update-image}

Disk images (Raspberry Pi, PC) have two system slots, A and B. An update is written to the slot that is not running, so a failed update never breaks the running system.

1. Download the update bundle for your board, `phonix-<version>-<board>.update` (at most 1 GiB).
2. Drop the file onto **Install an update**, or click the field to choose it. The field shows the upload progress.
3. Once the file is uploaded, the page shows the progress of the installation in steps (*Check*, *Install*, *Done*) with the elapsed time. You can leave the page; the update continues, and *System → Firmware* shows its progress again when you come back. Another file cannot be uploaded until it has finished. Do not switch the system off.
4. *Check*: before anything is written, the bundle is checked. It is refused if the ed25519 signature does not match the key built into the system, if it is for another board, or if any checksum is wrong. The page then shows the reason.
5. *Install*: the new version is written to the inactive slot and read back for verification. This takes a few minutes, longer on an SD card. The current version keeps running.
6. Click **Reboot into the new firmware**. Active calls are interrupted.
7. While the system restarts, the page waits for it and then opens *System → Firmware* again. It confirms *The update was successful: PhonixPBX X is running*, or reports that the new version did not start and the previous one is running again (see below).

The new slot gets **one trial boot**. After the reboot, a health check waits until the web interface and Asterisk respond, and only then makes the new slot permanent. The previous version is started again automatically if the new one:

- does not boot or crashes,
- does not pass the health check within 10 minutes (the system then reboots by itself), or
- is rebooted before it was confirmed.

The configuration database is migrated to the new version on its first start. Afterwards *Boot slot* shows the other slot.

When the previous version was started again, *System → Firmware* shows *Version X did not start*. The reason is usually in [Status → Logs]({{< relref "/status/logs.md" >}}). The update can also be installed from the console with `phonix update install <file>` (see the [command line reference]({{< relref "/reference/cli.md#other" >}})).

## Updating an LXC/Incus container {#update-lxc}

A system container has no second system slot. The update upgrades the packages of the container in place, and there is **no automatic rollback**.

1. **Take a snapshot of the container on the container host first**, so you can go back if the new version does not work:

   | Host | Snapshot | Roll back |
   |---|---|---|
   | Proxmox VE | `pct snapshot <vmid> before-update` (or *Snapshots → Take Snapshot*) | `pct rollback <vmid> before-update` |
   | Incus | `incus snapshot create <name> before-update` | `incus snapshot restore <name> before-update` |
   | LXC | `lxc-snapshot -n <name>` | `lxc-snapshot -n <name> -r snap0` |

   With Incus, snapshot a separate `/data` volume as well.
2. Tick **I have taken a snapshot of this container**. The upload field is enabled only after that.
3. Upload the bundle `phonix-<version>-lxc-<arch>.update`. It is checked like on the disk image (signature, board, checksums).
4. PhonixPBX saves a backup of the configuration under [System → Backup/Restore]({{< relref "/system/backup.md" >}}), then upgrades the packages from the bundle. Nothing is downloaded. The page shows the progress in steps (*Check*, *Backup*, *Install*, *Done*), as for the disk image.
5. Restart the container with **Reboot into the new firmware**. Until then the previous version keeps running. The new version migrates the database at its first start.

The bundle defines the complete package set of the release: packages you added yourself with `apk add` are removed. The log of the update is in `/var/log/phonix/update.log`. Containers created from version 1.2.0 or older refuse update bundles; replace such a container once with a new one and keep the `/data` volume.

If the new version does not work, roll back to the snapshot. Without a snapshot, create a new container from the previous release and restore the backup that was saved before the update.

## Updating the OCI container {#update-oci}

Update bundles do not apply to the OCI container image; the page explains this instead of offering an upload. Pull the new image and recreate the container with the same `/data` volume, for example:

```sh
docker compose pull && docker compose up -d
```

The new version migrates the database at its first start. Create and download a backup before you update, so you can set up the previous version again if needed.
