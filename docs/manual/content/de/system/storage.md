---
title: "Speicher"
weight: 30
description: "Belegung der Datenpartition und der Platz für Konfiguration, Medien, Backups und Mailbox-Nachrichten."
---
*System → Speicher* zeigt, wie voll die Datenpartition ist und was den Platz belegt. Die Seite dient nur der Anzeige; es gibt nichts einzustellen.

## Datenpartition {#data-partition}

Alle Daten, die einen Neustart oder ein Firmware-Update überstehen müssen, liegen auf der Datenpartition, eingehängt unter `/data`: die Konfigurationsdatenbank, Mailbox-Nachrichten, Mediendateien, Backups, das TLS-Zertifikat und die SSH-Schlüssel. Die Systemsoftware selbst liegt auf einer eigenen, schreibgeschützten Partition.

Der Balken zeigt den belegten Platz in Prozent und wird ab 90 % rot. Darunter stehen der belegte und der gesamte Speicherplatz.

Bei einem Disk-Image wird die Datenpartition beim ersten Start auf die gesamte Festplatte vergrößert. In einem Container ist `/data` ein Verzeichnis oder Volume des Containers; seine Größe legen Sie auf dem Container-Host fest.

## Belegung nach Inhalt {#usage}

Die Tabelle zeigt Größe und Ort der wichtigsten Bereiche:

| Inhalt | Bedeutung |
|---|---|
| Konfigurationsdatenbank | `phonix.db`, die vollständige Konfiguration. |
| Medien (Wartemusik, Ansagen) | Audiodateien, die unter [Dienste → Medien]({{< relref "/services/media.md" >}}) hochgeladen wurden. |
| Backups | Die Backup-Archive von [System → Backup/Wiederherstellung]({{< relref "/system/backup.md" >}}). |
| Mailbox | Die Nachrichten aller Mailboxen. |
| Asterisk-Datenbank | Laufzeitdaten von Asterisk, zum Beispiel an den Telefonen eingerichtete Rufumleitungen. Sie sind nicht Teil eines Backups. |

## Platz freigeben {#free-space}

Wenn die Partition voll wird:

- Löschen Sie alte Backups unter [System → Backup/Wiederherstellung]({{< relref "/system/backup.md#backups" >}}), nachdem Sie die heruntergeladen haben, die Sie behalten möchten. Es werden ohnehin höchstens 10 Backups aufbewahrt.
- Löschen Sie nicht mehr verwendete Mediendateien unter [Dienste → Medien]({{< relref "/services/media.md" >}}).
- Bitten Sie die Benutzer, alte Mailbox-Nachrichten zu löschen, oder verkürzen Sie die maximale Nachrichtenlänge unter [Dienste → Mailbox]({{< relref "/services/voicemail.md" >}}).
