---
title: "Backup/Wiederherstellung"
weight: 50
description: "Backups erstellen, herunterladen und wiederherstellen sowie AskoziaPBX-Dateien config.xml importieren oder exportieren."
---
Unter *System → Backup/Wiederherstellung* erstellen Sie Backups der vollständigen Konfiguration, stellen sie auf demselben oder einem anderen System wieder her und übernehmen die Konfiguration eines alten AskoziaPBX.

Erstellen Sie vor größeren Änderungen und vor jedem Update ein Backup, und bewahren Sie eine Kopie außerhalb des Systems auf: Backups liegen auf der Datenpartition und werden beim [Zurücksetzen auf Werkseinstellungen]({{< relref "/system/defaults.md" >}}) gelöscht.

## Inhalt eines Backups {#contents}

Ein Backup ist eine einzelne Datei `phonix-backup-JJJJMMTT-HHMMSS.tar.zst`. Sie enthält:

- die vollständige Konfiguration: alle Einstellungen, Telefone, Provider, Rufgruppen, Konferenzräume, Anwendungen, IVR-Menüs, Geschäftszeiten, Manager-Benutzer sowie die Web-Benutzer mit ihren API-Tokens,
- alle Geheimnisse dieser Konfiguration: SIP- und IAX-Passwörter, Mailbox-PINs, Manager-Passwörter, das E-Mail-Passwort und die Passwort-Hashes der Web-Benutzer,
- die Mediendateien (Wartemusik, Ansagen),
- das TLS-Zertifikat mit seinem privaten Schlüssel und das ACME-Konto.

> Ein Backup enthält Passwörter und private Schlüssel. Bewahren Sie heruntergeladene Backups ebenso sorgfältig auf wie das System selbst.

Nicht enthalten sind:

- Mailbox-Nachrichten,
- die Asterisk-Datenbank (Laufzeitdaten wie an den Telefonen eingerichtete Rufumleitungen),
- die Verbindungsdaten (CDR), das Audit-Log und die System-Logs,
- die SSH-Hostschlüssel, Ihre SSH-Schlüssel in `/data/ssh/authorized_keys` und die gerätespezifischen Schlüssel des Systems.

Die Konfiguration wird als versioniertes Dokument gespeichert, nicht als Kopie der Datenbank. Ein Backup lässt sich deshalb auch auf einer neueren PhonixPBX-Version wiederherstellen. Ein Backup, das von einer neueren als der laufenden Version erstellt wurde, wird abgelehnt.

## Backups {#backups}

Die Karte *Backups* listet die auf dem System gespeicherten Backups mit ihrer Größe auf, das neueste zuerst.

- **Backup erstellen** sichert sofort den aktuellen Stand.
- Das Wiederherstellen-Symbol öffnet die [Vorschau der Wiederherstellung](#restore) für dieses Backup.
- Das Download-Symbol lädt die Datei auf Ihren Computer herunter.
- Das Löschen-Symbol entfernt das Backup vom System.

PhonixPBX bewahrt die **10 neuesten** Backups auf und löscht ältere automatisch. Dazu zählen auch die automatisch erstellten Backups: vor jeder Wiederherstellung, vor einem AskoziaPBX-Import im Modus *Ersetzen* und vor einem Container-Update. Laden Sie Backups herunter, die Sie länger aufbewahren möchten.

Backups lassen sich auch auf der Kommandozeile mit `phonix backup create` erstellen (siehe [Kommandozeile]({{< relref "/reference/cli.md" >}})).

## Backup wiederherstellen {#restore}

1. Ziehen Sie unter *Wiederherstellen* eine Backup-Datei (`.tar.zst`, höchstens 2 GiB) auf das Upload-Feld, oder klicken Sie darauf, um eine Datei auszuwählen. Für ein auf dem System gespeichertes Backup klicken Sie stattdessen in der Liste auf sein Wiederherstellen-Symbol.
2. Das Backup wird vollständig geprüft, und eine Vorschau wird angezeigt: wann und mit welcher PhonixPBX-Version es erstellt wurde, wie viele Objekte jeder Art es enthält und ob es ein TLS-Zertifikat und ein ACME-Konto enthält. Bis hierhin wurde nichts geändert.
3. Wählen Sie, welche Teile des aktuellen Systems erhalten bleiben sollen (siehe unten).
4. Klicken Sie auf **Wiederherstellen** und bestätigen Sie.

PhonixPBX sichert dann den aktuellen Stand (das Sicherheits-Backup), ersetzt die Konfiguration und die Mediendateien und übernimmt alles sofort; ein separates Übernehmen ist nicht nötig. Der Browser lädt die Übersicht neu. Wurden die Web-Benutzer aus dem Backup wiederhergestellt, melden Sie sich erneut mit einem Benutzer und Passwort aus dem Backup an.

Ist etwas im Backup ungültig, bricht die Wiederherstellung ab, bevor etwas geändert wird. Schlägt das Übernehmen der wiederhergestellten Konfiguration fehl, bleibt die Konfiguration trotzdem wiederhergestellt, und der Fehler wird angezeigt; beheben Sie die Ursache und übernehmen Sie erneut.

Eine hochgeladene Datei, die Sie nicht wiederherstellen, wird nach 24 Stunden gelöscht.

### Beizubehaltende Teile {#keep}

| Option | Bedeutung | Standard |
|---|---|---|
| Aktuelle Netzwerk-, Firewall- und SSH-Einstellungen beibehalten | Behält *System → Netzwerk*, *Erweitert → Firewall* und die SSH-Einstellungen aus *System → Grundeinstellungen* unverändert bei. Empfohlen, wenn das Backup von einem anderen System oder aus einem anderen Netzwerk stammt: Dessen IP-Adresse, Firewall-Regeln oder SSH-Einstellungen könnten Sie aussperren. | ein |
| Aktuelle Web-Benutzer und API-Tokens beibehalten | Behält die Administratoren und API-Tokens dieses Systems. Andernfalls ersetzen die Benutzer, Passwörter und API-Tokens aus dem Backup die aktuellen. | aus |
| Aktuelles TLS-Zertifikat und ACME-Einstellungen beibehalten | Behält das Zertifikat, seinen Schlüssel und die ACME-Einstellungen unter [Erweitert → Zertifikat]({{< relref "/advanced/certificate.md" >}}), zum Beispiel wenn das Backup von einem System mit anderem Hostnamen stammt. | aus |

Alles andere, auch die Mediendateien, wird immer durch den Inhalt des Backups ersetzt.

## Altes AskoziaPBX {#askozia}

Die Karte *Altes AskoziaPBX* übernimmt die Konfiguration eines AskoziaPBX-2.x-Systems. Weitere Einzelheiten zur Umwandlung finden Sie unter [Umstieg von AskoziaPBX]({{< relref "/reference/askozia.md" >}}).

### config.xml importieren {#askozia-import}

1. Laden Sie die `config.xml` vom AskoziaPBX herunter (über dessen Backup-Funktion) und ziehen Sie sie auf das Upload-Feld (höchstens 10 MB).
2. Eine Vorschau zeigt je Abschnitt, wie viele Objekte angelegt, aktualisiert oder übersprungen werden, die nicht unterstützten Abschnitte, die verworfen werden (zum Beispiel analoge und ISDN-Hardware), sowie eine Liste von Warnungen und Fehlern je Objekt. Bis hierhin wurde nichts geändert.
3. Wenn keine Fehler vorliegen, wählen Sie den **Modus**:
   - **Aktuelle Konfiguration ersetzen (vorher Backup)**: entfernt die aktuellen Telefone, Provider usw. und importiert die Datei. Vorher wird ein Backup des aktuellen Stands erstellt.
   - **Mit aktueller Konfiguration zusammenführen**: fügt die Objekte aus der Datei zur aktuellen Konfiguration hinzu. Bereits vorhandene Objekte werden zugeordnet und aktualisiert; bei einem Konflikt (zum Beispiel einer bereits verwendeten Nebenstelle) wird das Objekt übersprungen und gemeldet.
4. Klicken Sie auf **Importieren** und bestätigen Sie.

Der Import wird nicht automatisch übernommen. Prüfen Sie die importierte Konfiguration und übernehmen Sie dann die ausstehenden Änderungen (siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}})).

### config.xml exportieren {#askozia-export}

**config.xml exportieren** lädt die aktuelle Konfiguration im AskoziaPBX-Format herunter, zum Beispiel um zu einem AskoziaPBX-System zurückzukehren. Der Export erfolgt nach bestem Bemühen: Funktionen, die AskoziaPBX nicht kennt, etwa IVR-Menüs, Geschäftszeiten, TLS/SRTP und mehrere Web-Benutzer, werden weggelassen.

> Die exportierte `config.xml` enthält alle Passwörter im Klartext, wie es das alte Format verlangt. Jeder Export wird im Audit-Log festgehalten.
