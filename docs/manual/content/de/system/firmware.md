---
title: "Firmware"
weight: 40
description: "Installierte Version, Suche nach Updates und Installation signierter Update-Pakete mit A/B-Slots und Rollback."
---
*System → Firmware* zeigt die installierte Version, prüft, ob eine neuere Version verfügbar ist, und installiert signierte Update-Pakete. Wie ein Update abläuft, hängt davon ab, wie PhonixPBX betrieben wird: als Disk-Image (Raspberry Pi, PC), als LXC-/Incus-Systemcontainer oder als OCI-Container (Docker, Podman). Ihre Konfiguration und Ihre Daten bleiben in jedem Fall erhalten.

## Installierte Firmware {#installed}

| Feld | Bedeutung |
|---|---|
| Version | Die laufende PhonixPBX-Version. |
| Board | Der Hardware- oder Containertyp, für den das System gebaut wurde, zum Beispiel `rpi-arm64`, `pc-amd64`, `lxc-amd64` oder `oci-amd64`. Ein Update-Paket muss für dasselbe Board gebaut sein. |
| Boot-Slot | Nur bei Disk-Images: der laufende System-Slot, `A` oder `B`. |
| Plattform | Nur bei Containern: *LXC-/Incus-Systemcontainer* oder *OCI-Container (Docker / Podman)*. |

## Nach Updates suchen {#check}

| Feld | Bedeutung | Standard |
|---|---|---|
| URL für Update-Informationen | Wo die neueste Version abgefragt wird. Sie muss mit `https://` beginnen. Entweder eine GitHub-API-URL für das neueste Release oder eine URL, die JSON der Form `{"version": "1.4.0", "url": "https://…"}` liefert. | `https://api.github.com/repos/PhonixPBX/PhonixPBX/releases/latest` |
| Automatisch prüfen | Einmal täglich nach der neuesten Version suchen. | aus |

**Speichern** speichert die beiden Einstellungen (ohne Übernehmen). **Jetzt prüfen** fragt die URL ab und meldet, ob Sie die neueste Version verwenden oder welche neuere Version mit welchem Download-Link verfügbar ist. Mit *Automatisch prüfen* macht die Anlage dasselbe einmal täglich, zu einer zufälligen Zeit innerhalb einer Stunde nach dem Start der täglichen Wartungsaufgaben.

Findet eine Prüfung – automatisch oder von Hand – eine neuere Version, zeigt die [Übersicht]({{< relref "/status/summary.md#notices" >}}) den Hinweis *PhonixPBX X ist verfügbar. System aktualisieren.*, bis diese Version installiert ist. Die Prüfung meldet nur; sie lädt nichts herunter und installiert nichts: Laden Sie das Update-Paket herunter und spielen Sie es wie unten beschrieben ein. Das System benötigt dafür Internetzugang.

## Disk-Image aktualisieren {#update-image}

Disk-Images (Raspberry Pi, PC) haben zwei System-Slots, A und B. Ein Update wird in den Slot geschrieben, der gerade nicht läuft. Ein fehlgeschlagenes Update beschädigt deshalb nie das laufende System.

1. Laden Sie das Update-Paket für Ihr Board herunter, `phonix-<version>-<board>.update` (höchstens 1 GiB).
2. Ziehen Sie die Datei auf **Update installieren**, oder klicken Sie auf das Feld, um sie auszuwählen. Das Feld zeigt den Fortschritt des Hochladens.
3. Sobald die Datei hochgeladen ist, zeigt die Seite den Fortschritt der Installation in Schritten (*Prüfen*, *Installieren*, *Fertig*) mit der vergangenen Zeit. Sie können die Seite verlassen; das Update läuft weiter, und *System → Firmware* zeigt den Fortschritt wieder an, wenn Sie zurückkehren. Eine weitere Datei kann erst hochgeladen werden, wenn es fertig ist. Schalten Sie das System nicht aus.
4. *Prüfen*: Bevor etwas geschrieben wird, wird das Paket geprüft. Es wird abgelehnt, wenn die ed25519-Signatur nicht zum im System eingebauten Schlüssel passt, wenn es für ein anderes Board ist oder wenn eine Prüfsumme nicht stimmt. Die Seite zeigt dann den Grund an.
5. *Installieren*: Die neue Version wird in den inaktiven Slot geschrieben und zur Kontrolle zurückgelesen. Das dauert einige Minuten, auf einer SD-Karte länger. Die aktuelle Version läuft weiter.
6. Klicken Sie auf **Mit der neuen Firmware neu starten**. Aktive Gespräche werden unterbrochen.
7. Während das System neu startet, wartet die Seite darauf und öffnet danach wieder *System → Firmware*. Dort steht *Das Update war erfolgreich: PhonixPBX X läuft*, oder dass die neue Version nicht gestartet ist und wieder die vorherige läuft (siehe unten).

Der neue Slot erhält **einen Probestart**. Nach dem Neustart wartet eine Zustandsprüfung, bis Weboberfläche und Asterisk antworten, und macht erst dann den neuen Slot dauerhaft. Die vorherige Version wird automatisch wieder gestartet, wenn die neue:

- nicht startet oder abstürzt,
- die Zustandsprüfung nicht innerhalb von 10 Minuten besteht (das System startet dann selbst neu) oder
- neu gestartet wird, bevor sie bestätigt wurde.

Die Konfigurationsdatenbank wird beim ersten Start der neuen Version migriert. Danach zeigt *Boot-Slot* den anderen Slot.

Wurde wieder die vorherige Version gestartet, zeigt *System → Firmware* *Version X ist nicht gestartet*. Den Grund finden Sie meist unter [Status → Logs]({{< relref "/status/logs.md" >}}). Das Update lässt sich auch an der Konsole mit `phonix update install <Datei>` installieren (siehe [Kommandozeile]({{< relref "/reference/cli.md#other" >}})).

## LXC-/Incus-Container aktualisieren {#update-lxc}

Ein Systemcontainer hat keinen zweiten System-Slot. Das Update aktualisiert die Pakete des Containers direkt, und es gibt **kein automatisches Rollback**.

1. **Erstellen Sie zuerst einen Snapshot des Containers auf dem Container-Host**, damit Sie zurückkehren können, falls die neue Version nicht funktioniert:

   | Host | Snapshot | Zurücksetzen |
   |---|---|---|
   | Proxmox VE | `pct snapshot <vmid> before-update` (oder *Snapshots → Take Snapshot*) | `pct rollback <vmid> before-update` |
   | Incus | `incus snapshot create <name> before-update` | `incus snapshot restore <name> before-update` |
   | LXC | `lxc-snapshot -n <name>` | `lxc-snapshot -n <name> -r snap0` |

   Erstellen Sie bei Incus auch einen Snapshot eines separaten `/data`-Volumes.
2. Setzen Sie das Häkchen bei **Ich habe einen Snapshot dieses Containers erstellt**. Erst dann ist das Upload-Feld freigegeben.
3. Laden Sie das Paket `phonix-<version>-lxc-<arch>.update` hoch. Es wird wie beim Disk-Image geprüft (Signatur, Board, Prüfsummen).
4. PhonixPBX speichert ein Backup der Konfiguration unter [System → Backup/Wiederherstellung]({{< relref "/system/backup.md" >}}) und aktualisiert dann die Pakete aus dem Update-Paket. Es wird nichts heruntergeladen. Die Seite zeigt den Fortschritt in Schritten (*Prüfen*, *Backup*, *Installieren*, *Fertig*), wie beim Disk-Image.
5. Starten Sie den Container mit **Mit der neuen Firmware neu starten** neu. Bis dahin läuft die bisherige Version weiter. Die neue Version migriert die Datenbank bei ihrem ersten Start.

Das Update-Paket legt den vollständigen Paketbestand des Release fest: Pakete, die Sie selbst mit `apk add` installiert haben, werden entfernt. Das Protokoll des Updates liegt in `/var/log/phonix/update.log`. Container, die mit Version 1.2.0 oder älter erstellt wurden, lehnen Update-Pakete ab; ersetzen Sie einen solchen Container einmalig durch einen neuen und behalten Sie das `/data`-Volume.

Funktioniert die neue Version nicht, kehren Sie zum Snapshot zurück. Ohne Snapshot erstellen Sie einen neuen Container mit dem vorherigen Release und stellen das Backup wieder her, das vor dem Update gespeichert wurde.

## OCI-Container aktualisieren {#update-oci}

Update-Pakete gelten nicht für das OCI-Container-Image; die Seite erklärt das, statt einen Upload anzubieten. Laden Sie das neue Image herunter und erstellen Sie den Container mit demselben `/data`-Volume neu, zum Beispiel:

```sh
docker compose pull && docker compose up -d
```

Die neue Version migriert die Datenbank bei ihrem ersten Start. Erstellen Sie vor dem Update ein Backup und laden Sie es herunter, damit Sie bei Bedarf die vorherige Version wieder einrichten können.
