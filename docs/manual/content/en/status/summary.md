---
title: "Summary"
weight: 10
description: "The start page: notices, key figures, system information, telephony status and graphs."
---
*Status → Summary* is the start page of the web interface. You reach it after logging in and with a click on the PhonixPBX logo. It gives an overview of the whole system on one page.

## Notices {#notices}

At the top the page may show notices that need your attention:

- *You are still using the initial administrator password.* The password from the console is still in use. Follow the link *Change it now* and choose your own, see [Changing your password]({{< relref "/getting-started/_index.md#password" >}}).
- *The web interface uses a self-signed certificate.* Browsers warn about this certificate. Follow the link to [Advanced → Certificate]({{< relref "/advanced/certificate.md" >}}) to get a certificate from Let's Encrypt or upload your own.
- *PhonixPBX X is available. Update the system.* A check for updates found a newer release. The link leads to [System → Firmware]({{< relref "/system/firmware.md#check" >}}). The notice disappears once that version is installed.
- *The AskoziaPBX configuration (config.xml) found on the boot partition was imported at first boot.* Below it, the import report lists what was taken over, skipped or dropped, see [Migrating from AskoziaPBX]({{< relref "/reference/askozia.md#first-boot" >}}). Check the report and the imported settings, then click **Dismiss** to hide it.

## Key figures {#figures}

The four cards in the first row:

| Card | Shows |
|---|---|
| Phones | Number of configured phones, with a link to *manage phones*. |
| Providers | Number of configured providers, with a link to *manage providers*. |
| CPU load | Load average of the last minute, below it the averages of 1, 5 and 15 minutes and the number of CPUs. A value permanently above the number of CPUs means the system is overloaded. |
| Memory | Share of memory in use, with a bar and the absolute figures. |

## System information {#system}

| Row | Meaning |
|---|---|
| Hostname | Host name and domain, set under [System → General Setup]({{< relref "/system/general.md#name" >}}). |
| LAN | Network interface and its configuration: `DHCP` or the static address with prefix length. |
| Version | Installed PhonixPBX version. |
| Board / slot | Hardware type of the image (for example `pc-amd64`, `rpi-arm64` or a container board) and the active system slot (A or B), see [System → Firmware]({{< relref "/system/firmware.md" >}}). |
| Platform | CPU model and architecture. |
| Kernel | Version of the running Linux kernel. |
| Uptime | Time since the last start. |
| Data partition | Used and total space on the data partition, see [System → Storage]({{< relref "/system/storage.md" >}}). |
| Time zone | Time zone of the system. |

## Telephony {#telephony}

The *Telephony* card shows the state of Asterisk, the telephony engine of PhonixPBX, and is refreshed every 10 seconds:

- the Asterisk version, the number of *Active channels* and how many SIP phones are registered out of all SIP phones (*SIP phones registered*),
- the providers with their registration or reachability state.

If Asterisk does not answer, the card shows *Asterisk is not reachable* with the error. The link *details* leads to [Calls & Registrations]({{< relref "/status/calls.md" >}}), which also lists every phone and the active calls.

## Graphs {#graphs}

At the bottom, two small graphs show the CPU usage in percent and the network traffic of the last minutes. They are filled only while the page is open. Larger versions are under [Status → Graphs]({{< relref "/status/graphs.md" >}}).
