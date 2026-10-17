---
title: "Übersicht"
weight: 10
description: "Die Startseite: Hinweise, Kennzahlen, Systeminformationen, Telefoniestatus und Graphen."
---
*Status → Übersicht* ist die Startseite der Weboberfläche. Sie erreichen sie nach der Anmeldung und mit einem Klick auf das PhonixPBX-Logo. Sie zeigt den Zustand des ganzen Systems auf einen Blick.

## Hinweise {#notices}

Oben auf der Seite erscheinen gegebenenfalls Hinweise, die Ihre Aufmerksamkeit brauchen:

- *Sie verwenden noch das initiale Administratorpasswort.* Das Passwort von der Konsole ist noch in Gebrauch. Folgen Sie dem Link *Ändern Sie es jetzt* und wählen Sie ein eigenes, siehe [Passwort ändern]({{< relref "/getting-started/_index.md#password" >}}).
- *Die Weboberfläche verwendet ein selbstsigniertes Zertifikat.* Browser warnen vor diesem Zertifikat. Unter [Erweitert → Zertifikat]({{< relref "/advanced/certificate.md" >}}) beziehen Sie ein Zertifikat von Let's Encrypt oder laden Ihr eigenes hoch.
- *PhonixPBX X ist verfügbar. System aktualisieren.* Eine Suche nach Updates hat eine neuere Version gefunden. Der Link führt zu [System → Firmware]({{< relref "/system/firmware.md#check" >}}). Der Hinweis verschwindet, sobald diese Version installiert ist.
- *Die AskoziaPBX-Konfiguration (config.xml) von der Boot-Partition wurde beim ersten Start importiert.* Darunter zeigt der Importbericht, was übernommen, übersprungen oder verworfen wurde, siehe [Umstieg von AskoziaPBX]({{< relref "/reference/askozia.md#first-boot" >}}). Prüfen Sie den Bericht und die importierten Einstellungen und klicken Sie dann auf **Ausblenden**.

## Kennzahlen {#figures}

Die vier Karten in der ersten Reihe:

| Karte | Zeigt |
|---|---|
| Telefone | Anzahl der eingerichteten Telefone, mit dem Link *Telefone verwalten*. |
| Provider | Anzahl der eingerichteten Provider, mit dem Link *Provider verwalten*. |
| CPU-Last | Durchschnittliche Last der letzten Minute, darunter die Mittelwerte über 1, 5 und 15 Minuten und die Zahl der CPUs. Liegt der Wert dauerhaft über der Zahl der CPUs, ist das System überlastet. |
| Arbeitsspeicher | Anteil des belegten Arbeitsspeichers, als Balken und in absoluten Zahlen. |

## Systeminformationen {#system}

| Zeile | Bedeutung |
|---|---|
| Hostname | Hostname und Domain, festgelegt unter [System → Grundeinstellungen]({{< relref "/system/general.md#name" >}}). |
| LAN | Netzwerkschnittstelle und ihre Konfiguration: `DHCP` oder die statische Adresse mit Präfixlänge. |
| Version | Installierte PhonixPBX-Version. |
| Board / Slot | Hardwaretyp des Images (zum Beispiel `pc-amd64`, `rpi-arm64` oder ein Container-Board) und der aktive Systemslot (A oder B), siehe [System → Firmware]({{< relref "/system/firmware.md" >}}). |
| Plattform | CPU-Modell und Architektur. |
| Kernel | Version des laufenden Linux-Kernels. |
| Betriebszeit | Zeit seit dem letzten Start. |
| Datenpartition | Belegter und gesamter Platz auf der Datenpartition, siehe [System → Speicher]({{< relref "/system/storage.md" >}}). |
| Zeitzone | Zeitzone des Systems. |

## Telefonie {#telephony}

Die Karte *Telefonie* zeigt den Zustand von Asterisk, dem Telefonie-Kern von PhonixPBX, und wird alle 10 Sekunden aktualisiert:

- die Asterisk-Version, die Zahl der *Aktiven Kanäle* und wie viele SIP-Telefone von allen SIP-Telefonen registriert sind (*Registrierte SIP-Telefone*),
- die Provider mit ihrem Registrierungs- bzw. Erreichbarkeitszustand.

Antwortet Asterisk nicht, zeigt die Karte *Asterisk ist nicht erreichbar* mit der Fehlermeldung. Der Link *Details* führt zu [Gespräche & Registrierungen]({{< relref "/status/calls.md" >}}), wo zusätzlich jedes Telefon und die aktiven Gespräche aufgeführt sind.

## Graphen {#graphs}

Unten zeigen zwei kleine Graphen die CPU-Auslastung in Prozent und den Netzwerkverkehr der letzten Minuten. Sie werden nur gefüllt, solange die Seite geöffnet ist. Größere Fassungen finden Sie unter [Status → Graphen]({{< relref "/status/graphs.md" >}}).
