---
title: "Logs"
weight: 40
description: "Die Logs von Asterisk, System, Webanwendung und Monitor, live verfolgt."
---
*Status → Logs* zeigt die Logdateien der Anlage. Mit den Schaltflächen oben rechts wählen Sie ein Log. Die Seite zeigt die letzten 300 Zeilen und verfolgt die Datei dann **live**: Neue Zeilen erscheinen unten, sobald sie geschrieben werden, solange die Seite geöffnet ist.

## Verfügbare Logs {#logs}

| Schaltfläche | Datei | Inhalt |
|---|---|---|
| Asterisk | `/var/log/asterisk/messages` | Meldungen des Telefonie-Kerns: Registrierungen, fehlgeschlagene Anmeldungen, Anrufe, die nicht zustande kamen, Fehler in der Konfiguration. Das wichtigste Log bei Telefonieproblemen. |
| System | `/var/log/messages` | Das Systemlog: Netzwerk, Dienste, Firewall, E-Mail-Versand (`msmtp`), Updates und die privilegierten Aktionen der Weboberfläche. |
| Webanwendung | `/var/log/phonix/web.log` | Meldungen der PhonixPBX-Weboberfläche und der API, auch Fehler beim Übernehmen der Konfiguration. |
| Monitor | `/var/log/phonix/monitor.log` | Der Sicherheitsmonitor: Adressen, die nach wiederholten fehlgeschlagenen Anmeldungen an SIP, IAX oder dem Asterisk Manager gesperrt wurden. |

Die Kopfzeile des Logs zeigt den Pfad der Datei. *Das Log ist leer oder nicht verfügbar.* erscheint, wenn die Datei noch nicht existiert oder leer ist.

## Logs lesen {#reading}

- Stellen Sie das Problem nach, während die Seite geöffnet ist – lassen Sie etwa ein Telefon registrieren oder führen Sie einen Testanruf durch – und beobachten Sie die neuen Zeilen.
- Im Asterisk-Log sind die Zeilen mit `WARNING` und `ERROR` die interessanten. Eine fehlgeschlagene Registrierung eines Telefons zeigt sich typischerweise als Meldung `Failed to authenticate` mit der Adresse des Geräts.
- Die Zeile `There are no local system nameservers configured, resorting to system resolution` erscheint bei jedem Neuladen von SIP. Sie ist harmlos, die Namensauflösung funktioniert normal.

## Größe und Aufbewahrung {#retention}

Auf dem Gerät und in einem LXC-/Incus-Systemcontainer liegen die Logs im Arbeitsspeicher und belasten so den Datenträger nicht. Sie werden alle 15 Minuten geprüft und ab 1–2 MB rotiert. Bei einem Neustart der Anlage oder des Containers gehen sie verloren. Wollen Sie Informationen zu einem Problem behalten, kopieren Sie die betreffenden Zeilen, bevor Sie die Anlage neu starten.

## OCI-Container {#oci}

In einem OCI-Container (Docker, Podman) schreibt PhonixPBX keine Logdateien. Asterisk, die Webanwendung und der Sicherheitsmonitor schreiben stattdessen in die Ausgabe des Containers, und *Status → Logs* zeigt nur den Hinweis *Die Logs stehen in der Container-Ausgabe*. Lesen Sie die Logs auf dem Container-Host, zum Beispiel mit `docker logs -f <container>` oder `podman logs -f <container>`. Wie lange sie aufbewahrt werden, bestimmt der Log-Treiber der Container-Engine.

Dieselben Logs können Sie auch auf der Konsole ansehen: [Konsolenmenü]({{< relref "/getting-started/_index.md#console" >}}), *View logs*. Über MCP angebundene KI-Assistenten lesen die letzten Zeilen eines Logs mit dem Werkzeug `tail_log`, siehe [REST-API und MCP]({{< relref "/reference/api.md#mcp" >}}).
