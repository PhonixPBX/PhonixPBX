---
title: "Migrating from AskoziaPBX"
weight: 30
description: "Importing the config.xml of an AskoziaPBX 1.x/2.x system, what is carried over, and exporting back."
---
PhonixPBX is the successor of AskoziaPBX and can take over the configuration of an existing AskoziaPBX system: phones, providers with their dial patterns and incoming routes, call groups, applications, conference rooms, voicemail and e-mail settings, transfer and parking codes, manager users and the system settings. The source is the `config.xml` file of the old system, version 2.1 or older; older versions are upgraded automatically during the import.

## Getting config.xml {#export-old}

Download `config.xml` from the web interface of the old system (*System → Backup*) or copy `conf/config.xml` from the first partition of its CompactFlash card or disk. Keep the file safe: it contains all passwords in plain text.

## Importing at the first boot {#first-boot}

The easiest way for a new installation:

1. Write the PhonixPBX image to the card or disk.
2. Before the first start, copy `config.xml` to the boot partition (`PHXBOOT`), either at the top level or as `conf/config.xml` – the same place as on the old system.
3. Start the PBX. During the first boot the file is imported in *Replace* mode and renamed to `config.xml.imported`.

In the OCI container, place the file at `import/config.xml` in the data volume before the first start.

After logging in, the [dashboard]({{< relref "/status/summary.md#notices" >}}) shows the import report until an administrator clicks **Dismiss**. Review it like the result of an import in the web interface (see below).

## Importing in the web interface {#import}

1. Open [System → Backup/Restore]({{< relref "/system/backup.md#askozia" >}}) and go to the card *Legacy AskoziaPBX*.
2. Drop `config.xml` on the field *Drop config.xml here or click to upload* (or click it and choose the file).
3. A **preview** appears. Nothing has been changed yet. It shows, per section, how many objects would be created (*create*), updated (*update*) or skipped (*skip*), the sections that are not supported (*Not supported, dropped: …*) and a list of messages, each marked `error`, `warning` or `info`.
4. Choose the **Mode** (see below) and click **Import**. Confirm the question *Import this configuration now?*.
5. The *Import result* appears. Review the imported configuration, then click **Apply changes** in the banner at the top.

If the preview contains errors, the import cannot be applied as is (*The import has errors and cannot be applied as is.*): correct the file or the conflicting objects and upload it again.

## Replace or merge {#modes}

| Mode | Effect |
|---|---|
| Replace current configuration (backup first) | The default. A backup of the current configuration is created first. Then all phones, providers, call groups, conference rooms, applications and manager users are removed and replaced by those from the file. The system settings (host name, time zone, network, SIP/IAX/RTP, voicemail, e-mail, feature codes) and the web password are taken from the file as well. |
| Merge into current configuration | Adds the objects from the file to the current configuration. Objects are matched by their AskoziaPBX ID, then by extension; on a conflict the object is skipped and reported. Global settings and the web password stay as they are. |

> **Replace also takes over the network settings** of the old system (DHCP or static address, gateway, DNS). If both systems run at the same time, check *System → Network* before you apply, so the new PBX does not take the address of the old one or become unreachable.

> **Web password:** with *Replace*, the web login of the old system (usually `admin`) gets the old system's password, if it has at least 8 characters. Shorter passwords are not imported and the current password stays. The report says which applies.

## What is converted {#converted}

- SIP phones and providers are converted from the old `chan_sip` to PJSIP; codecs (in their order), NAT, DTMF and qualify settings are carried over.
- Application logic written for Asterisk 1.8 is adapted where possible, for example `MeetMe` becomes `ConfBridge`. Anything that cannot be adapted automatically is marked for review in the report – check those applications after the import.
- The built-in applications (voicemail `000086`, call forwarding `000023`, test numbers) are matched with the PhonixPBX versions.

## What is not imported {#not-imported}

PhonixPBX does not support telephony hardware. These parts are left out and listed in the report:

- analog and ISDN phones, providers and fax (DAHDI, Redfone gateways, GSM),
- Skinny (SCCP) phones, virtual fax machines,
- storage disks and services, dynamic DNS and RFC 2136 updates, the captive portal, phone provisioning, third-party integrations, manually edited configuration files.

If phones or dial patterns depended on an analog or ISDN provider, the report tells you. Replace such a line with a SIP gateway and add it as a provider.

## Exporting back to config.xml {#export}

On the same card, *Export config.xml* downloads the current configuration in the AskoziaPBX format, for example to return to an old system. The export is best effort: features that AskoziaPBX does not know – IVR menus, business hours, TLS/SRTP, the firewall, several administrators, PJSIP-only options – are left out. The file contains all passwords in plain text.

## On the command line {#cli}

The same import and export is available with [`phonix legacy`]({{< relref "/reference/cli.md#legacy" >}}): `phonix legacy import config.xml --dry-run` prints the report without changing anything, `--merge` selects the merge mode, `phonix legacy export config.xml` writes the export. Scripts can use the [REST API]({{< relref "/reference/api.md#legacy" >}}) (`/api/v1/legacy/import` and `/api/v1/legacy/export`).

## AskoziaPBX hardware {#hardware}

PhonixPBX does not run on the PC Engines ALIX and WRAP boards that many AskoziaPBX systems used (their CPUs lack SSE2). Copy `config.xml` from such a box and import it on a Raspberry Pi, a PC, a virtual machine or a container.
