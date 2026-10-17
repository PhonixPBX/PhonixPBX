---
title: "PhonixPBX Handbuch"
---
PhonixPBX ist eine Telefonanlage (TK-Anlage) für kleine Büros und für zu Hause. Sie läuft auf einem Raspberry Pi, einem PC, einer virtuellen Maschine oder in einem Container, verbindet Ihre Tischtelefone und Softphones untereinander und über einen oder mehrere Provider mit dem öffentlichen Telefonnetz. Eingerichtet wird alles über die Weboberfläche; eine Kommandozeile ist nicht nötig.

## Für wen dieses Handbuch ist {#audience}

- **Administratoren**, die die Anlage installieren und in der Weboberfläche konfigurieren: Telefone, Provider, Anrufverteilung, Mailbox, Backups und Updates. Die meisten Kapitel richten sich an Sie.
- **Telefonbenutzer**, die mit einem an die Anlage angeschlossenen Telefon telefonieren. Das Kapitel [Telefonieren mit PhonixPBX]({{< relref "/phone-users/_index.md" >}}) erklärt die Wählcodes für Vermittlung, Gesprächsübernahme, Parken, Mailbox und Telefonkonferenzen. Administratoren können es unverändert weitergeben.

## Aufbau des Handbuchs {#structure}

Die Kapitel folgen dem Menü der Weboberfläche:

| Kapitel | Inhalt |
|---|---|
| [Erste Schritte]({{< relref "/getting-started/_index.md" >}}) | Erster Start, Anmeldung, die Bedienoberfläche, Änderungen übernehmen, das Konsolenmenü |
| [Telefonieren mit PhonixPBX]({{< relref "/phone-users/_index.md" >}}) | Wählcodes und Funktionen für Telefonbenutzer |
| [Status]({{< relref "/status/_index.md" >}}) | Übersicht, Registrierungen, aktive Gespräche, Graphen, Logs und Audit-Log |
| [System]({{< relref "/system/_index.md" >}}) | Hostname, Netzwerk, Speicher, Firmware-Updates, Backups, Werkseinstellungen, Neustart |
| [Konten]({{< relref "/accounts/_index.md" >}}) | Telefone und Provider |
| [Wählplan]({{< relref "/dialplan/_index.md" >}}) | Anwendungen, Rufgruppen, IVR-Menüs, Geschäftszeiten, Vermittlung und Parken |
| [Dienste]({{< relref "/services/_index.md" >}}) | E-Mail-Benachrichtigungen, Mailbox, Telefonkonferenzen, Mediendateien |
| [Erweitert]({{< relref "/advanced/_index.md" >}}) | SIP, IAX, RTP, Asterisk Manager, Firewall, Zertifikat, Administratoren, API-Tokens |
| [Referenz]({{< relref "/reference/_index.md" >}}) | Kommandozeile, REST-API und MCP, Umstieg von AskoziaPBX, Fehlersuche |

## Hilfe in der Weboberfläche {#help-button}

Jede Seite der Weboberfläche hat eine Schaltfläche **Hilfe** (das Fragezeichen-Symbol rechts neben dem Seitentitel). Sie öffnet in einem neuen Browser-Tab das Kapitel dieses Handbuchs, das die Seite beschreibt – in der Sprache der Weboberfläche, sofern das Handbuch in dieser Sprache vorliegt, sonst auf Englisch. Der Link *Handbuch* in der Fußzeile öffnet diese Startseite.
