---
title: "Troubleshooting"
weight: 40
description: "Solutions for the most common problems: registration, audio, e-mail, lost passwords, lockouts and certificate warnings."
---
This page lists the most common problems and how to solve them. Most of them can be narrowed down with two pages of the web interface; start there.

## Where to look {#where-to-look}

- **[Status → Calls & Registrations]({{< relref "/status/calls.md" >}})** shows whether each phone and provider is registered, from which address and with which device, and which calls are running. It refreshes every 5 seconds, so leave it open while you test.
- **[Status → Logs]({{< relref "/status/logs.md" >}})**, log *Asterisk*, shows why a registration or a call failed. Reproduce the problem while the log is open and look for `WARNING` and `ERROR` lines.
- The log *Monitor* shows addresses that the PBX has blocked; the log *System* shows e-mail delivery and network problems.
- **Pending changes:** if the yellow banner is still visible, the change you are testing is not active yet. Click *Apply changes* first.

## A phone does not register {#phone-registration}

The phone shows "not registered" or similar, and *Status → Calls & Registrations* has no *Contact* for it.

1. **Credentials:** the user name in the phone must be the **extension**, the password the one from [Accounts → Phones]({{< relref "/accounts/phones.md#edit" >}}), and the server (registrar) the address of the PBX. A typo here produces `Failed to authenticate` lines in the Asterisk log.
2. **Applied?** A newly created phone exists for Asterisk only after *Apply changes*.
3. **Enabled?** Disabled phones are listed as *disabled* and cannot register.
4. **Several devices:** if more devices register to the same extension than *Max. registered devices* allows, each new registration replaces the oldest one, so devices seem to drop out in turn. Raise the value on the phone's page.
5. **Firewall:** if *Networks allowed to use SIP/IAX* is set under [Advanced → Firewall]({{< relref "/advanced/firewall.md" >}}), the network of the phone must be in the list.
6. **Blocked address:** after repeated wrong passwords the PBX blocks the address of the device for a while; the *Monitor* log shows it. See [Blocked by the firewall](#locked-out).
7. **Transport and port:** the phone must use the same transport (UDP, TCP or TLS) and port as configured under [Advanced → SIP]({{< relref "/advanced/sip.md" >}}); UDP port 5060 is the default.

To check the phone itself, dial `000063` once it is registered: the PBX reads back the extension the phone is registered as.

## One-way or no audio {#one-way-audio}

The call is connected, but one side hears nothing, or both. This is almost always a NAT or firewall problem: signalling (SIP) gets through, the audio (RTP) does not.

- **PBX behind a NAT router** (providers or remote phones on the internet): set [System → Network → NAT / public address]({{< relref "/system/network.md#nat" >}}) to *NAT, static public IP* or *NAT, dynamic IP (hostname)* with your public address or DynDNS name. Forward the SIP port (5060/udp) and the RTP port range (default 10000–20000/udp, under [Advanced → RTP]({{< relref "/advanced/rtp.md" >}})) on the router to the PBX.
- **Phones outside the LAN** (home office, mobile softphone): enable *Phone is behind NAT (symmetric RTP, rewrite contact)* on the phone.
- **Provider through NAT:** enable *Provider is reached through NAT (symmetric RTP)* on the provider.
- **SIP ALG:** many routers have a "SIP ALG" or "SIP helper" that rewrites SIP packets and often breaks audio. Switch it off on the router.
- **Container with published ports:** the published UDP range must match the RTP range set in PhonixPBX exactly.

Test with the echo number `00003246`: if you hear yourself on an internal phone, the path between phone and PBX is fine, and the problem is on the provider side.

## The provider does not register {#provider-registration}

*Status → Calls & Registrations* shows the provider in red.

- *Rejected*: the provider refused the credentials. Check *Username* and *Password*; some providers need a separate *Authentication user* or a *From user* – see the details from your provider and [Accounts → Providers]({{< relref "/accounts/providers.md#edit" >}}).
- *Unregistered* or *Unreachable*: the PBX does not reach the provider. Check the host name of the provider, the DNS servers under [System → Network]({{< relref "/system/network.md" >}}) and that the PBX can reach the internet.
- *not loaded*: the provider was created or changed but not applied yet.
- If *Networks allowed to use SIP/IAX* is set under *Advanced → Firewall*, the provider's addresses must be in the list.
- The Asterisk log shows the provider's answer, for example `403 Forbidden` (wrong credentials) or a timeout (not reachable).

Incoming calls also need an [incoming route]({{< relref "/accounts/providers.md#incoming-routes" >}}) for the dialled number; outgoing calls a matching [dial pattern]({{< relref "/accounts/providers.md#dial-patterns" >}}).

## No e-mails arrive {#email}

Voicemail and missed call e-mails need three things:

1. A working mail server under [Services → Notifications]({{< relref "/services/email.md" >}}). Use *Send a test message* there. The test uses the applied configuration, so apply pending changes first. The error message usually names the problem: wrong password, wrong port or encryption, a certificate the PBX does not trust (*Verify the server certificate*).
2. On the phone: an e-mail address and *Send voicemail to e-mail* or *E-mail notification on missed calls*.
3. Applied changes.

Delivery attempts and errors are logged in the *System* log (`msmtp`). Many internet providers block outgoing port 25; use port 587 (STARTTLS) or 465 (TLS) of your mail provider instead. Also check the spam folder.

## Forgotten administrator password {#forgot-password}

On the console of the PBX (screen and keyboard, or the serial console), choose *Reset administrator password* in the [console menu]({{< relref "/getting-started/_index.md#console" >}}) and enter a new password.

- **LXC/Incus/Proxmox:** open the container console (`pct console <id>`, `incus console pbx`) – the menu runs there.
- **OCI container:** `docker exec -it phonix phonix user passwd admin`.
- If another administrator can still log in, they can set a new password under [Advanced → Administrators]({{< relref "/advanced/users.md" >}}).

After five failed logins within five minutes, the login page refuses further attempts for a few minutes; wait, then try again.

## Locked out by the firewall {#locked-out}

**Blocked after failed logins.** The security monitor blocks an address for the *Block duration* (default one hour) after repeated failed authentications at SIP, IAX or the Asterisk Manager – for example a phone with a wrong password. A blocked address cannot reach the PBX at all, including the web interface. The *Monitor* log lists the blocks. To lift a block:

- wait until the block duration has passed, or
- access the PBX from another address and apply a change under [Advanced → Firewall]({{< relref "/advanced/firewall.md" >}}) (reloading the firewall clears all blocks), or
- reboot the PBX; blocks are not kept across a restart.

Then fix the device that caused it. Addresses in *Networks allowed to manage the PBX* and, if the PBX has a static address, its own LAN subnet are never blocked.

**Your own network is not allowed.** If *Networks allowed to manage the PBX* does not contain the network of your computer, the web interface and SSH are unreachable from it. Connect from an allowed network and correct the list. If that is not possible, open a root shell on the PBX (in a container: `pct enter <id>`, `incus exec pbx -- sh` or `docker exec -it phonix sh`; on the appliance: boot with the kernel option `phonix.console=shell`, see `docs/INSTALL.md`) and run `nft delete table inet phonix`. This switches the firewall off until the next apply or reboot: log in, correct the list and apply.

## Certificate warnings in the browser {#certificate-warning}

- **Self-signed certificate:** after installation the PBX uses a certificate that it signed itself. Browsers warn about it; this is expected. Get a trusted certificate under [Advanced → Certificate]({{< relref "/advanced/certificate.md" >}}) – automatically from Let's Encrypt or another ACME CA, or upload your own.
- **Wrong name:** a certificate is valid only for the names it contains (*Names* on the certificate page). Open the PBX by one of these names. After changing the host name, use *Create new self-signed certificate* or request a new automatic certificate.
- **Let's Encrypt fails:** with *HTTP (port 80)* validation the names must resolve to the PBX in public DNS and port 80 must be reachable from the internet. For a PBX that is only reachable internally, use the validation via *DNS provider API*.
- **Expired:** automatic certificates are renewed daily when they expire in less than 30 days. If that fails, the certificate page shows the error of the last attempt.

## Asterisk is not reachable {#asterisk-down}

If the status pages show *Asterisk is not reachable*, look at the end of the Asterisk log for the reason. Apply the configuration again (`phonix apply --force` on the command line rewrites and reloads everything) or reboot the PBX under [System → Reboot]({{< relref "/system/reboot.md" >}}). If the problem started after an update, see [System → Firmware]({{< relref "/system/firmware.md" >}}).
