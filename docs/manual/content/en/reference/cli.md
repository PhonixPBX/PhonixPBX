---
title: "Command line"
weight: 10
description: "The phonix command: users, tokens, backups, configuration import and export, apply."
---
Everything that is needed day to day is in the web interface. The `phonix` command is for automation, recovery and service work. It runs on the PBX itself, as `root`:

- **Appliance:** log in with SSH (switch it on under [System → General Setup]({{< relref "/system/general.md#ssh" >}})).
- **LXC/Incus/Proxmox container:** `pct enter <id>`, `incus exec pbx -- sh` or `lxc-attach -n pbx`.
- **OCI container:** `docker exec -it phonix phonix <command>`.

`phonix --help` lists all commands, `phonix <command> --help` the options of one command, `phonix --version` prints the version. `-v` makes the output more verbose.

> Commands that change the configuration (`config import`, `legacy import`) only write the database, like saving a page in the web interface. Run `phonix apply` afterwards to activate the changes.

## Administrators: phonix user {#user}

```sh
phonix user list                       # administrators with role and last login
phonix user add alice                  # create; asks for the password
phonix user passwd admin               # set a new password; asks for it
phonix user passwd admin --must-change # ... and force a change at the next login
phonix user delete alice
```

The user name defaults to `admin`. `--password <pw>` passes the password on the command line instead of asking for it (it then ends up in the shell history). Passwords need at least 8 characters.

## API tokens: phonix token {#token}

```sh
phonix token create monitoring --read-only          # prints the token (phx_...) once
phonix token create crm --allow-calls --expires-days 365
phonix token list                                    # id, name, prefix, access, status, owner, last use, validity
phonix token disable 3
phonix token enable 3
phonix token delete 3
```

| Option (create) | Meaning |
|---|---|
| `--user <name>` | Administrator who owns the token (default `admin`). |
| `--read-only` | GET requests and read-only MCP tools only. |
| `--allow-calls` | May place calls (click-to-call), also with `--read-only`. |
| `--expires-days <n>` | Validity in days; without it the token does not expire. |

The token itself is shown only once. See [REST API and MCP]({{< relref "/reference/api.md#tokens" >}}) and [Advanced → API tokens]({{< relref "/advanced/tokens.md" >}}).

## Applying the configuration: phonix apply {#apply}

`phonix apply` does the same as *Apply changes* in the web interface: it generates all configuration files, writes the changed ones and reloads the affected services. It prints each written file and each reload action.

| Option | Meaning |
|---|---|
| `--force` | Rewrite all files and reload everything, even if nothing changed. Useful after a manual repair. |
| `--json` | Print the result as JSON. |
| `--boot` | Only write the files, without reloading (used during system start). |

`phonix generate <directory>` renders all configuration files into a directory without activating anything, for inspection.

## Backups: phonix backup {#backup}

```sh
phonix backup create                          # into /data/backups/phonix-backup-<date>-<time>.tar.zst
phonix backup create /tmp/pbx.tar.zst         # to a file of your choice
phonix backup restore /tmp/pbx.tar.zst --dry-run
phonix backup restore /tmp/pbx.tar.zst
```

The PBX keeps the 10 newest backups in `/data/backups`. A restore applies the configuration right away. By default it keeps the current network, firewall and SSH settings, so the PBX stays reachable.

| Option (restore) | Meaning |
|---|---|
| `--dry-run` | Only check the file and show what it contains. |
| `--restore-network` | Also take the network, firewall and SSH settings from the backup. |
| `--keep-users` | Keep the current administrators and API tokens. |
| `--keep-certificate` | Keep the current TLS certificate and ACME settings. |

See also [System → Backup/Restore]({{< relref "/system/backup.md" >}}).

## Configuration as JSON: phonix config {#config}

```sh
phonix config export pbx.json        # or without file name / with "-" to stdout
phonix config import pbx.json --dry-run
phonix config import pbx.json        # then: phonix apply
phonix config schema                 # JSON schema of the file
```

`config.json` contains the whole configuration (settings, phones, providers, dialplan, users, media list) including all passwords and PINs; protect the file accordingly. Unlike a backup it contains no media files and no certificate. `import -` reads from standard input.

## AskoziaPBX config.xml: phonix legacy {#legacy}

```sh
phonix legacy import config.xml --dry-run     # report only
phonix legacy import config.xml               # replace the configuration (backup first)
phonix legacy import config.xml --merge       # merge into the configuration
phonix legacy export config.xml
```

The import prints its report. See [Migrating from AskoziaPBX]({{< relref "/reference/askozia.md" >}}).

## Certificate: phonix cert {#cert}

`phonix cert renew` requests or renews the ACME certificate (Let's Encrypt) when it is due; `--force` requests a new one anyway. It runs automatically once a day. The settings are under [Advanced → Certificate]({{< relref "/advanced/certificate.md" >}}).

## Other commands {#other}

| Command | Purpose |
|---|---|
| `phonix tui` | Start the [console menu]({{< relref "/getting-started/_index.md#console" >}}). |
| `phonix banner` | Print the console banner with the addresses of the PBX. |
| `phonix update check` | Look up the latest release at the *Update information URL* of [System → Firmware]({{< relref "/system/firmware.md#check" >}}) and print whether a newer version is available. With `--auto` it does nothing unless *Check automatically* is on (used by the daily job). |
| `phonix update install <file>` | Check and install an update bundle, like the upload on [System → Firmware]({{< relref "/system/firmware.md#update-image" >}}); the page shows its progress too. The file must be below `/data`. Reboot afterwards to start the new version. |
| `phonix healthcheck` | Check that the web interface and Asterisk respond; exit code 0 when healthy. `--mark-good` confirms the booted update slot. |
| `phonix migrate` | Create or upgrade the database schema. Runs automatically at system start. |
| `phonix firstboot` | Initialise the data partition. Runs automatically at the first start. |
| `phonix web`, `phonix monitor` | The web application and the security monitor; started by the system services, not by hand. |
