---
title: "Umstieg von AskoziaPBX"
weight: 30
description: "Die config.xml einer AskoziaPBX 1.x/2.x importieren, was übernommen wird, und der Export zurück."
---
PhonixPBX ist der Nachfolger von AskoziaPBX und kann die Konfiguration einer bestehenden AskoziaPBX übernehmen: Telefone, Provider samt Wählmustern und eingehenden Routen, Rufgruppen, Anwendungen, Konferenzräume, Mailbox- und E-Mail-Einstellungen, Codes für Vermittlung und Parken, Manager-Benutzer und die Systemeinstellungen. Grundlage ist die Datei `config.xml` der alten Anlage, Version 2.1 oder älter; ältere Versionen werden beim Import automatisch aktualisiert.

## config.xml beschaffen {#export-old}

Laden Sie `config.xml` in der Weboberfläche der alten Anlage herunter (*System → Backup*) oder kopieren Sie `conf/config.xml` von der ersten Partition ihrer CompactFlash-Karte bzw. Festplatte. Bewahren Sie die Datei sicher auf: Sie enthält alle Passwörter im Klartext.

## Import beim ersten Start {#first-boot}

Der einfachste Weg bei einer Neuinstallation:

1. Schreiben Sie das PhonixPBX-Image auf die Karte bzw. Festplatte.
2. Kopieren Sie vor dem ersten Start `config.xml` auf die Boot-Partition (`PHXBOOT`), entweder direkt ins Hauptverzeichnis oder als `conf/config.xml` – an dieselbe Stelle wie bei der alten Anlage.
3. Starten Sie die Anlage. Beim ersten Start wird die Datei im Modus *Ersetzen* importiert und in `config.xml.imported` umbenannt.

Im OCI-Container legen Sie die Datei vor dem ersten Start unter `import/config.xml` im Datenvolume ab.

Nach der Anmeldung zeigt die [Übersicht]({{< relref "/status/summary.md#notices" >}}) den Importbericht, bis ein Administrator auf **Ausblenden** klickt. Prüfen Sie ihn wie das Ergebnis eines Imports in der Weboberfläche (siehe unten).

## Import in der Weboberfläche {#import}

1. Öffnen Sie [System → Backup/Wiederherstellung]({{< relref "/system/backup.md#askozia" >}}) und gehen Sie zur Karte *Altes AskoziaPBX*.
2. Ziehen Sie `config.xml` auf das Feld *config.xml hierher ziehen oder zum Hochladen klicken* (oder klicken Sie darauf und wählen Sie die Datei).
3. Es erscheint eine **Vorschau**. Geändert ist noch nichts. Sie zeigt je Abschnitt, wie viele Objekte angelegt (*anlegen*), aktualisiert (*aktualisieren*) oder übersprungen (*überspringen*) würden, die nicht unterstützten Abschnitte (*Nicht unterstützt, verworfen: …*) und eine Liste von Meldungen, jeweils als `error`, `warning` oder `info` gekennzeichnet.
4. Wählen Sie den **Modus** (siehe unten) und klicken Sie auf **Importieren**. Bestätigen Sie die Frage *Diese Konfiguration jetzt importieren?*.
5. Das *Importergebnis* erscheint. Prüfen Sie die importierte Konfiguration und klicken Sie dann oben im Hinweis auf **Änderungen übernehmen**.

Enthält die Vorschau Fehler, lässt sich der Import so nicht durchführen: Korrigieren Sie die Datei oder die kollidierenden Objekte und laden Sie sie erneut hoch.

## Ersetzen oder zusammenführen {#modes}

| Modus | Wirkung |
|---|---|
| Aktuelle Konfiguration ersetzen (vorher Backup) | Die Voreinstellung. Zuerst wird ein Backup der aktuellen Konfiguration angelegt. Dann werden alle Telefone, Provider, Rufgruppen, Konferenzräume, Anwendungen und Manager-Benutzer entfernt und durch die aus der Datei ersetzt. Auch die Systemeinstellungen (Hostname, Zeitzone, Netzwerk, SIP/IAX/RTP, Mailbox, E-Mail, Funktionscodes) und das Web-Passwort werden aus der Datei übernommen. |
| Mit aktueller Konfiguration zusammenführen | Fügt die Objekte aus der Datei zur aktuellen Konfiguration hinzu. Objekte werden über ihre AskoziaPBX-ID und dann über die Nummer zugeordnet; bei einem Konflikt wird das Objekt übersprungen und gemeldet. Globale Einstellungen und das Web-Passwort bleiben unverändert. |

> **Ersetzen übernimmt auch die Netzwerkeinstellungen** der alten Anlage (DHCP oder feste Adresse, Gateway, DNS). Laufen beide Anlagen gleichzeitig, prüfen Sie vor dem Übernehmen *System → Netzwerk*, damit die neue Anlage nicht die Adresse der alten belegt oder unerreichbar wird.

> **Web-Passwort:** Beim *Ersetzen* erhält die Web-Anmeldung der alten Anlage (meist `admin`) deren Passwort, sofern es mindestens 8 Zeichen hat. Kürzere Passwörter werden nicht übernommen, und das aktuelle Passwort bleibt gültig. Der Bericht sagt, was zutrifft.

## Was umgewandelt wird {#converted}

- SIP-Telefone und -Provider werden vom alten `chan_sip` auf PJSIP umgestellt; Codecs (in ihrer Reihenfolge), NAT-, DTMF- und Qualify-Einstellungen werden übernommen.
- Für Asterisk 1.8 geschriebene Anwendungslogik wird nach Möglichkeit angepasst, zum Beispiel wird aus `MeetMe` nun `ConfBridge`. Was sich nicht automatisch anpassen lässt, markiert der Bericht zur Prüfung – sehen Sie sich diese Anwendungen nach dem Import an.
- Die eingebauten Anwendungen (Mailbox `000086`, Rufumleitung `000023`, Testnummern) werden den PhonixPBX-Fassungen zugeordnet.

## Was nicht importiert wird {#not-imported}

PhonixPBX unterstützt keine Telefonie-Hardware. Diese Teile bleiben außen vor und werden im Bericht aufgeführt:

- analoge und ISDN-Telefone, -Provider und Fax (DAHDI, Redfone-Gateways, GSM),
- Skinny-(SCCP-)Telefone, virtuelle Faxgeräte,
- Speicherplatten und -dienste, dynamisches DNS und RFC-2136-Updates, das Captive Portal, Telefon-Provisionierung, Integrationen von Drittanbietern, von Hand bearbeitete Konfigurationsdateien.

Hingen Telefone oder Wählmuster an einem analogen oder ISDN-Provider, weist der Bericht darauf hin. Ersetzen Sie einen solchen Anschluss durch ein SIP-Gateway und richten Sie es als Provider ein.

## Export zurück nach config.xml {#export}

Auf derselben Karte lädt *config.xml exportieren* die aktuelle Konfiguration im AskoziaPBX-Format herunter, etwa um zu einer alten Anlage zurückzukehren. Der Export erfolgt nach bestem Bemühen: Funktionen, die AskoziaPBX nicht kennt – IVR-Menüs, Geschäftszeiten, TLS/SRTP, die Firewall, mehrere Administratoren, reine PJSIP-Optionen –, fehlen darin. Die Datei enthält alle Passwörter im Klartext.

## Auf der Kommandozeile {#cli}

Import und Export gibt es auch mit [`phonix legacy`]({{< relref "/reference/cli.md#legacy" >}}): `phonix legacy import config.xml --dry-run` gibt den Bericht aus, ohne etwas zu ändern, `--merge` wählt das Zusammenführen, `phonix legacy export config.xml` schreibt den Export. Skripte verwenden die [REST-API]({{< relref "/reference/api.md#legacy" >}}) (`/api/v1/legacy/import` und `/api/v1/legacy/export`).

## AskoziaPBX-Hardware {#hardware}

PhonixPBX läuft nicht auf den Boards PC Engines ALIX und WRAP, die viele AskoziaPBX-Anlagen verwendeten (deren CPUs fehlt SSE2). Kopieren Sie `config.xml` von einem solchen Gerät und importieren Sie sie auf einem Raspberry Pi, einem PC, einer virtuellen Maschine oder in einem Container.
