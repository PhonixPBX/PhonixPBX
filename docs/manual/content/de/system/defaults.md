---
title: "Werkseinstellungen"
weight: 60
description: "Die gesamte Konfiguration und alle Daten löschen und wie beim ersten Start neu beginnen."
---
*System → Werkseinstellungen* löscht die gesamte Konfiguration und alle Daten und startet das System neu. Danach verhält es sich genau wie beim ersten Start. Verwenden Sie diese Funktion, bevor Sie ein System weitergeben, oder um ganz von vorn zu beginnen.

## Was gelöscht wird {#erased}

Das Zurücksetzen löscht die gesamte Datenpartition (`/data`):

- die Konfiguration mit allen Telefonen, Providern, Benutzern und Einstellungen,
- Mailbox-Nachrichten und Mediendateien,
- **alle Backups**, die auf dem System gespeichert sind,
- das TLS-Zertifikat, die SSH-Hostschlüssel und Ihre SSH-Schlüssel.

Die installierte PhonixPBX-Version bleibt erhalten. Das Zurücksetzen lässt sich nicht rückgängig machen.

> Laden Sie vor dem Zurücksetzen unter [System → Backup/Wiederherstellung]({{< relref "/system/backup.md" >}}) ein Backup herunter, falls Sie die Konfiguration noch einmal benötigen könnten.

## Zurücksetzen {#reset}

1. Geben Sie `RESET` (in Großbuchstaben) in das Feld **Zur Bestätigung RESET eingeben** ein.
2. Klicken Sie auf **Zurücksetzen und neu starten**. Aktive Gespräche werden unterbrochen.

Wie es weitergeht, hängt davon ab, wie PhonixPBX betrieben wird:

- **Disk-Image:** Das System startet neu und formatiert die Datenpartition beim Hochfahren.
- **LXC-/Incus-Container:** Der Container startet neu und leert `/data`, bevor PhonixPBX startet.
- **OCI-Container:** Der Container wird gestoppt. `/data` wird gelöscht, wenn derselbe Container wieder startet; mit einer Neustart-Richtlinie wie `--restart unless-stopped` geschieht das sofort. Entfernen Sie den Container stattdessen und erstellen einen neuen, wird das Daten-Volume nicht gelöscht.

Nach dem Zurücksetzen startet das System wie beim ersten Start: Es erstellt eine neue Datenbank, ein neues selbstsigniertes Zertifikat und ein **neues zufälliges Administratorpasswort**. Lesen Sie das Passwort im Konsolenmenü ab (bei einem Container: auf der Container-Konsole bzw. beim OCI-Image im Container-Log) und melden Sie sich an, wie unter [Erste Schritte]({{< relref "/getting-started/_index.md#login" >}}) beschrieben. Bei einem Disk-Image wird das Netzwerk wieder auf DHCP an der ersten Netzwerkkarte gesetzt; das System kann also eine andere Adresse erhalten.

Das Konsolenmenü bietet dasselbe Zurücksetzen an, siehe [Konsolenmenü]({{< relref "/getting-started/_index.md#console" >}}).
