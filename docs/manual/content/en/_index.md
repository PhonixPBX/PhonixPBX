---
title: "PhonixPBX Manual"
---
PhonixPBX is a telephone system (PBX) for small offices and homes. It runs on a Raspberry Pi, a PC, a virtual machine or in a container, connects your desk phones and softphones with each other and, through one or more providers, with the public telephone network. Everything is set up in the web interface; no command line is needed.

## Who this manual is for {#audience}

- **Administrators** who install the PBX and configure it in the web interface: phones, providers, call routing, voicemail, backups and updates. Most chapters are written for you.
- **Phone users** who make calls with a phone connected to the PBX. The chapter [Using your phone]({{< relref "/phone-users/_index.md" >}}) explains the dial codes for transfers, call pickup, parking, voicemail and conferences. Administrators can hand it out as it is.

## How the manual is organised {#structure}

The chapters follow the menu of the web interface:

| Chapter | Contents |
|---|---|
| [Getting started]({{< relref "/getting-started/_index.md" >}}) | First boot, login, the user interface, applying changes, the console menu |
| [Using your phone]({{< relref "/phone-users/_index.md" >}}) | Dial codes and features for phone users |
| [Status]({{< relref "/status/_index.md" >}}) | Dashboard, registrations, active calls, graphs, logs and the audit log |
| [System]({{< relref "/system/_index.md" >}}) | Host name, network, storage, firmware updates, backups, factory reset, reboot |
| [Accounts]({{< relref "/accounts/_index.md" >}}) | Phones and providers |
| [Dialplan]({{< relref "/dialplan/_index.md" >}}) | Applications, call groups, IVR menus, business hours, transfers and parking |
| [Services]({{< relref "/services/_index.md" >}}) | E-mail notifications, voicemail, conferencing, media files |
| [Advanced]({{< relref "/advanced/_index.md" >}}) | SIP, IAX, RTP, Asterisk Manager, firewall, certificate, administrators, API tokens |
| [Reference]({{< relref "/reference/_index.md" >}}) | Command line, REST API and MCP, migration from AskoziaPBX, troubleshooting |

## Help in the web interface {#help-button}

Every page of the web interface has a **Help** button (the question mark icon at the right of the page title). It opens, in a new browser tab, the chapter of this manual that describes the page, in the language of the web interface when the manual exists in that language, otherwise in English. The *Manual* link in the footer opens this start page.
