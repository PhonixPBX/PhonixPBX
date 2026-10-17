---
title: "Getting started"
weight: 10
icon: rocket
description: "First boot, login, the user interface, applying changes and the console menu."
---
This chapter takes you from a freshly installed PhonixPBX to the first working call. How to write the disk image or create the container is described in the installation guide (`docs/INSTALL.md` in the source repository); here we start with the first boot.

## First boot and the address of the PBX {#first-boot}

Connect the network cable and power on. The first network card gets its address via **DHCP**. The first boot takes one to two minutes. During it, the PBX:

- enlarges the data partition to fill the disk,
- creates the database, a self-signed HTTPS certificate and the SSH host keys,
- generates a **random password** for the administrator `admin`.

When it is ready, the screen (and the serial console, 115200 baud) shows a banner like this:

```
  PhonixPBX 1.3.0

  LAN (eth0, DHCP): 192.168.1.23
  Web interface: https://192.168.1.23/
                 https://phonix.local/

  Initial login: admin / 3W7YaMJMUei5
  (you must change the password at the first login)
```

If the box has no screen, you have two other ways to find it:

- Open `https://phonix.local/` (or `https://<hostname>.local/` once you have changed the host name). The PBX announces itself on the LAN with mDNS; this works on macOS, iOS, Windows 10 and newer, Android 12 and newer, and Linux with nss-mdns. The announcement can be switched off under [System → General Setup]({{< relref "/system/general.md#mdns" >}}).
- Look up the address in the DHCP lease list of your router.

In a container, the initial password is printed in the container log (`docker logs phonix`) or on the container console instead; mDNS is not available in the OCI image.

## Logging in {#login}

1. Open `https://<address>/` in a browser. Plain `http://` is redirected to HTTPS.
2. The PBX uses a **self-signed certificate** until you install a proper one, so the browser warns you the first time. Check that the address is right and accept the warning. To get rid of the warning, obtain a free certificate from Let's Encrypt or upload your own under [Advanced → Certificate]({{< relref "/advanced/certificate.md" >}}).
3. On the page *Login to your PBX*, enter the username `admin` and the initial password from the console, then click *Sign in*.

After five failed attempts within five minutes, the login is blocked for a few minutes (*Too many failed attempts. Please wait a few minutes.*).

If the initial password is lost, reset it with the [console menu](#console): *Reset administrator password*.

## Changing your password {#password}

At the first login you are taken straight to the page *Change password* with the note *Please choose your own password before continuing.* Other pages are not available until you have set your own password.

You can change your password at any time: open the user menu (your initials at the top right) and choose *Change password*.

| Field | Meaning |
|---|---|
| Current password | Your password so far (the initial password at the first login). |
| New password | At least 8 characters. |
| Repeat new password | The same again, to rule out typing errors. |

Further administrators, and new passwords for them, are managed under [Advanced → Administrators]({{< relref "/advanced/users.md" >}}).

## Preferences: the interface language {#account}

Open the user menu and choose *Preferences*. Under *Language* you pick the language of the web interface for your own account; *English (default)* is used when nothing is selected. The setting is stored per administrator and takes effect immediately after *Save*.

The language of the voice prompts that callers hear is a different setting, see [System → General Setup]({{< relref "/system/general.md#tones-language" >}}).

## Finding your way around {#navigation}

- The **menu** on the left has the same sections as AskoziaPBX: *System*, *Accounts*, *Dialplan*, *Services*, *Status* and *Advanced*. Click a section to open its pages. On small screens the menu is folded behind the button at the top.
- The PhonixPBX logo leads to *Status → Summary*, the start page.
- The **top bar** shows the host name of the PBX, the moon or sun icon to switch between **dark mode** and **light mode** (your browser remembers the choice), and the user menu with *Preferences*, *Change password* and *Logout*.
- Every page has a **Help** button (question mark) at the right of the page title. It opens the matching chapter of this manual.
- The footer shows the installed version, a link to this *Manual* and to the interactive *API* documentation.

After a period of inactivity you are logged out automatically; the time is set under [Advanced → GUI Options]({{< relref "/advanced/gui.md" >}}).

## Saving and applying changes {#apply}

PhonixPBX separates **saving** from **activating**. When you save a form, the change is stored in the database right away, but the telephone system still runs with the old configuration. A yellow banner appears at the top of every page:

> **Pending changes** — the configuration has been changed (Phones and providers, Dialplan). Apply to activate.

The list in brackets names the areas that have changed. Click **Apply changes** to activate them. The PBX then generates the configuration files, writes only the files that actually changed and reloads only the affected parts (for example the SIP stack or the dialplan). Running calls are normally not interrupted.

- On success the banner turns green: *Configuration applied.*, with the number of reload actions.
- If something fails, the banner shows *Applying the configuration failed.* with the error messages and stays, so you can correct the input and apply again.

You can make several changes and apply them together. The banner names these areas:

| Area in the banner | Changed by |
|---|---|
| Phones and providers | *Accounts → Phones*, *Accounts → Providers* |
| Dialplan | everything under *Dialplan* |
| Voicemail, conferencing and media | *Services → Voicemail*, *Conferencing*, *Media* |
| E-mail notifications | *Services → Notifications* |
| SIP, IAX and RTP settings | *Advanced → SIP*, *IAX*, *RTP* and the network settings |
| Asterisk manager users | *Advanced → Manager (AMI)* |
| Network | *System → Network* and the host name |
| System settings | *System → General Setup* |
| Firewall | *Advanced → Firewall* |

Some actions take effect **immediately**, without *Apply changes*:

- switching the mode of business hours (*Automatic*, *Open*, *Closed*) on the [Business Hours]({{< relref "/dialplan/hours.md" >}}) page, through the API or with the feature code on a phone,
- your password and language, administrators and API tokens,
- the options under *Advanced → GUI Options*,
- installing, regenerating or requesting a certificate under *Advanced → Certificate*,
- restoring a backup (it is applied as part of the restore), firmware updates, reboot and factory reset.

> Changing the IP address under *System → Network* interrupts your connection when you apply it. Open the new address afterwards.

## The console menu {#console}

On the local screen (`tty1`) and on the serial console, PhonixPBX shows the banner with its address followed by a menu. In an LXC/Incus container it runs on the container console; in the OCI container start it with `docker exec -it phonix phonix tui`. Physical access to the console counts as authorisation, so the menu has no login. Type the number of an entry and press Enter:

| # | Entry | What it does |
|---|---|---|
| 1 | Show status | Shows the banner again: version, LAN address, web address and, until it is changed, the initial password. |
| 2 | Set LAN IP address | Choose DHCP or enter a static address, prefix length, gateway and DNS servers. The change is applied at once. Not available in containers, where the host manages the network. |
| 3 | Reset administrator password | Sets a new password (at least 8 characters) for `admin` or another administrator; creates the account if it does not exist. Use it when you are locked out. |
| 4 | View logs | Shows the Asterisk, system, web application or monitor log and follows it live until you press Ctrl-C. |
| 5 | Reboot | Restarts the PBX after a confirmation. |
| 6 | Shut down | Powers the PBX off after a confirmation. |
| 7 | Reset to factory defaults | Erases **all configuration and data** after a confirmation and reboots, see [Factory Defaults]({{< relref "/system/defaults.md" >}}). |

The console menu is always in English.

## Next steps {#next-steps}

A typical setup goes in this order:

1. **[System → General Setup]({{< relref "/system/general.md" >}})**: host name and domain, time zone, tones and the language of the voice prompts. Check [System → Network]({{< relref "/system/network.md" >}}) if the PBX needs a static address or sits behind a NAT router.
2. **[Accounts → Providers]({{< relref "/accounts/providers.md" >}})**: add your SIP provider account, with [dial patterns]({{< relref "/accounts/providers.md#dial-patterns" >}}) for outgoing calls.
3. **[Accounts → Phones]({{< relref "/accounts/phones.md" >}})**: create a phone for every desk phone or softphone and enter the credentials in the device.
4. **Incoming routes**: on the provider, choose which phone, call group or IVR menu receives incoming calls, see [Incoming routes]({{< relref "/accounts/providers.md#incoming-routes" >}}).
5. **Apply changes** in the yellow banner.
6. **Test**: check under [Status → Calls & Registrations]({{< relref "/status/calls.md" >}}) that the phones and the provider are registered, call between two phones, dial out, call in from a mobile phone. The [test numbers]({{< relref "/phone-users/_index.md#tests" >}}) help, for example `00003246` for an echo test.

After that, set up what you need: [e-mail notifications]({{< relref "/services/email.md" >}}) for voicemail, [call groups]({{< relref "/dialplan/callgroups.md" >}}), [business hours]({{< relref "/dialplan/hours.md" >}}), [IVR menus]({{< relref "/dialplan/ivr.md" >}}), and a first [backup]({{< relref "/system/backup.md" >}}).
