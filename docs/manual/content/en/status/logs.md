---
title: "Logs"
weight: 40
description: "The Asterisk, system, web application and monitor logs, followed live."
---
*Status → Logs* shows the log files of the PBX. Use the buttons at the top right to choose a log. The page shows the last 300 lines and then follows the file **live**: new lines appear at the bottom as they are written, as long as the page is open.

## Available logs {#logs}

| Button | File | Contains |
|---|---|---|
| Asterisk | `/var/log/asterisk/messages` | Messages of the telephony engine: registrations, failed authentications, calls that could not be connected, errors in the configuration. The most important log for telephony problems. |
| System | `/var/log/messages` | The system log: network, services, firewall, e-mail delivery (`msmtp`), updates and the privileged actions of the web interface. |
| Web application | `/var/log/phonix/web.log` | Messages of the PhonixPBX web interface and API, including errors while applying the configuration. |
| Monitor | `/var/log/phonix/monitor.log` | The security monitor: addresses that were blocked after repeated failed logins at SIP, IAX or the Asterisk Manager. |

The header of the log shows the path of the file. *The log is empty or not available.* appears when the file does not exist yet or contains nothing.

## Reading the logs {#reading}

- Reproduce the problem while the page is open, for example let a phone register or place a test call, and watch the new lines.
- In the Asterisk log, `WARNING` and `ERROR` lines are the interesting ones. A failed registration of a phone typically shows up as a `Failed to authenticate` message with the address of the device.
- The line `There are no local system nameservers configured, resorting to system resolution` appears with every SIP reload. It is harmless: name resolution works normally.

## Size and lifetime {#retention}

On the appliance the logs are kept in RAM and rotated while they are small. They are lost on reboot. To keep information about a problem, copy the relevant lines before you restart the PBX.

The same logs can also be viewed on the console: [console menu]({{< relref "/getting-started/_index.md#console" >}}), *View logs*. AI assistants connected over MCP can read the last lines of a log with the tool `tail_log`, see [REST API and MCP]({{< relref "/reference/api.md#mcp" >}}).
