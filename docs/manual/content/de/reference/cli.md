---
title: "Kommandozeile"
weight: 10
description: "Der Befehl phonix: Benutzer, Tokens, Backups, Import und Export der Konfiguration, Übernehmen."
---
Alles, was Sie im Alltag brauchen, steht in der Weboberfläche. Der Befehl `phonix` dient der Automatisierung, der Wiederherstellung und Servicearbeiten. Er läuft auf der Anlage selbst, als `root`:

- **Gerät:** per SSH anmelden (einschalten unter [System → Grundeinstellungen]({{< relref "/system/general.md#ssh" >}})).
- **LXC-/Incus-/Proxmox-Container:** `pct enter <id>`, `incus exec pbx -- sh` oder `lxc-attach -n pbx`.
- **OCI-Container:** `docker exec -it phonix phonix <befehl>`.

`phonix --help` listet alle Befehle, `phonix <befehl> --help` die Optionen eines Befehls, `phonix --version` gibt die Version aus. `-v` macht die Ausgabe ausführlicher.

> Befehle, die die Konfiguration ändern (`config import`, `legacy import`), schreiben nur in die Datenbank – wie das Speichern einer Seite in der Weboberfläche. Führen Sie danach `phonix apply` aus, um die Änderungen zu aktivieren.

## Administratoren: phonix user {#user}

```sh
phonix user list                       # Administratoren mit Rolle und letzter Anmeldung
phonix user add alice                  # anlegen; fragt nach dem Passwort
phonix user passwd admin               # neues Passwort setzen; fragt danach
phonix user passwd admin --must-change # ... und Änderung bei der nächsten Anmeldung erzwingen
phonix user delete alice
```

Ohne Angabe gilt der Benutzername `admin`. `--password <pw>` übergibt das Passwort auf der Kommandozeile, statt danach zu fragen (es landet dann in der Shell-Historie). Passwörter brauchen mindestens 8 Zeichen.

## API-Tokens: phonix token {#token}

```sh
phonix token create monitoring --read-only          # gibt das Token (phx_...) einmalig aus
phonix token create crm --allow-calls --expires-days 365
phonix token list                                    # ID, Name, Präfix, Zugriff, Status, Besitzer, letzte Nutzung, Gültigkeit
phonix token disable 3
phonix token enable 3
phonix token delete 3
```

| Option (create) | Bedeutung |
|---|---|
| `--user <name>` | Administrator, dem das Token gehört (Standard `admin`). |
| `--read-only` | Nur GET-Anfragen und lesende MCP-Werkzeuge. |
| `--allow-calls` | Darf Anrufe tätigen (Click-to-Call), auch zusammen mit `--read-only`. |
| `--expires-days <n>` | Gültigkeit in Tagen; ohne die Option läuft das Token nicht ab. |

Das Token selbst wird nur einmal angezeigt. Siehe [REST-API und MCP]({{< relref "/reference/api.md#tokens" >}}) und [Erweitert → API-Tokens]({{< relref "/advanced/tokens.md" >}}).

## Konfiguration übernehmen: phonix apply {#apply}

`phonix apply` bewirkt dasselbe wie *Änderungen übernehmen* in der Weboberfläche: Es erzeugt alle Konfigurationsdateien, schreibt die geänderten und lädt die betroffenen Dienste neu. Dabei gibt es jede geschriebene Datei und jede Neuladeaktion aus.

| Option | Bedeutung |
|---|---|
| `--force` | Alle Dateien neu schreiben und alles neu laden, auch wenn sich nichts geändert hat. Nützlich nach einer Reparatur von Hand. |
| `--json` | Ergebnis als JSON ausgeben. |
| `--boot` | Nur die Dateien schreiben, ohne neu zu laden (beim Systemstart verwendet). |

`phonix generate <verzeichnis>` erzeugt alle Konfigurationsdateien in einem Verzeichnis, ohne etwas zu aktivieren – zum Ansehen.

## Backups: phonix backup {#backup}

```sh
phonix backup create                          # nach /data/backups/phonix-backup-<datum>-<zeit>.tar.zst
phonix backup create /tmp/pbx.tar.zst         # in eine Datei Ihrer Wahl
phonix backup restore /tmp/pbx.tar.zst --dry-run
phonix backup restore /tmp/pbx.tar.zst
```

Die Anlage behält die 10 neuesten Backups in `/data/backups`. Eine Wiederherstellung übernimmt die Konfiguration sofort. Standardmäßig bleiben dabei die aktuellen Netzwerk-, Firewall- und SSH-Einstellungen erhalten, damit die Anlage erreichbar bleibt.

| Option (restore) | Bedeutung |
|---|---|
| `--dry-run` | Datei nur prüfen und ihren Inhalt anzeigen. |
| `--restore-network` | Auch die Netzwerk-, Firewall- und SSH-Einstellungen aus dem Backup übernehmen. |
| `--keep-users` | Die aktuellen Administratoren und API-Tokens behalten. |
| `--keep-certificate` | Das aktuelle TLS-Zertifikat und die ACME-Einstellungen behalten. |

Siehe auch [System → Backup/Wiederherstellung]({{< relref "/system/backup.md" >}}).

## Konfiguration als JSON: phonix config {#config}

```sh
phonix config export pbx.json        # ohne Dateiname oder mit "-" auf die Standardausgabe
phonix config import pbx.json --dry-run
phonix config import pbx.json        # danach: phonix apply
phonix config schema                 # JSON-Schema der Datei
```

`config.json` enthält die gesamte Konfiguration (Einstellungen, Telefone, Provider, Wählplan, Benutzer, Medienliste) samt aller Passwörter und PINs; schützen Sie die Datei entsprechend. Anders als ein Backup enthält sie keine Mediendateien und kein Zertifikat. `import -` liest von der Standardeingabe.

## AskoziaPBX-config.xml: phonix legacy {#legacy}

```sh
phonix legacy import config.xml --dry-run     # nur Bericht
phonix legacy import config.xml               # Konfiguration ersetzen (vorher Backup)
phonix legacy import config.xml --merge       # mit der Konfiguration zusammenführen
phonix legacy export config.xml
```

Der Import gibt seinen Bericht aus. Siehe [Umstieg von AskoziaPBX]({{< relref "/reference/askozia.md" >}}).

## Zertifikat: phonix cert {#cert}

`phonix cert renew` beantragt oder erneuert das ACME-Zertifikat (Let's Encrypt), wenn es fällig ist; `--force` beantragt in jedem Fall ein neues. Der Befehl läuft automatisch einmal täglich. Die Einstellungen stehen unter [Erweitert → Zertifikat]({{< relref "/advanced/certificate.md" >}}).

## Weitere Befehle {#other}

| Befehl | Zweck |
|---|---|
| `phonix tui` | Das [Konsolenmenü]({{< relref "/getting-started/_index.md#console" >}}) starten. |
| `phonix banner` | Die Konsolenmeldung mit den Adressen der Anlage ausgeben. |
| `phonix update check` | Die neueste Version unter der *URL für Update-Informationen* von [System → Firmware]({{< relref "/system/firmware.md#check" >}}) abfragen und ausgeben, ob eine neuere Version verfügbar ist. Mit `--auto` geschieht nichts, solange *Automatisch prüfen* aus ist (für den täglichen Lauf). |
| `phonix healthcheck` | Prüfen, ob Weboberfläche und Asterisk antworten; Exit-Code 0, wenn alles in Ordnung ist. `--mark-good` bestätigt den gebooteten Update-Slot. |
| `phonix migrate` | Datenbankschema anlegen oder aktualisieren. Läuft beim Systemstart automatisch. |
| `phonix firstboot` | Die Datenpartition initialisieren. Läuft beim ersten Start automatisch. |
| `phonix web`, `phonix monitor` | Die Webanwendung und der Sicherheitsmonitor; werden von den Systemdiensten gestartet, nicht von Hand. |
