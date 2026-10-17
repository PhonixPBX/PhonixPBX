---
title: "Gespräche & Registrierungen"
weight: 20
description: "Live-Zustand von Asterisk, Registrierungen von Providern und Telefonen sowie laufende Gespräche."
---
*Status → Gespräche & Registrierungen* zeigt den aktuellen Zustand der Telefonanlage. Die Seite aktualisiert sich alle 5 Sekunden selbst; Sie können sie also geöffnet lassen, während Sie ein Telefon oder einen Provider testen.

## Asterisk {#asterisk}

Die erste Zeile zeigt die Asterisk-Version, die Zahl der *Aktiven Kanäle* (jede Gesprächsseite zählt als ein Kanal, ein Gespräch zwischen zwei Telefonen hat also meist zwei) und *Registrierte SIP-Telefone*: wie viele der SIP-Telefone gerade ein registriertes Gerät haben, gemessen an allen SIP-Telefonen.

Zeigt die Seite *Asterisk ist nicht erreichbar* mit einer Fehlermeldung, läuft der Telefonie-Kern nicht oder antwortet nicht. Schauen Sie in das Asterisk-Log unter [Status → Logs]({{< relref "/status/logs.md" >}}); erneutes Übernehmen der Konfiguration oder ein [Neustart]({{< relref "/system/reboot.md" >}}) bringt ihn meist zurück.

## Provider {#providers}

| Spalte | Bedeutung |
|---|---|
| Name | Name des Providers. |
| Typ | `SIP` oder `IAX`. |
| Registrierung / Zustand | Bei SIP-Providern mit Registrierung: der Registrierungszustand. Bei SIP-Providern ohne Registrierung und bei IAX-Providern: ob der Provider erreichbar ist. Deaktivierte Provider zeigen *deaktiviert*. |

*nicht geladen* bedeutet, dass der Provider zwar in der Konfiguration steht, in Asterisk aber noch nicht aktiv ist; übernehmen Sie die ausstehenden Änderungen.

## Telefone {#phones}

| Spalte | Bedeutung |
|---|---|
| Nummer | Interne Nummer des Telefons. |
| Name | Anrufername des Telefons. |
| Zustand | Gerätezustand laut Asterisk, oder *deaktiviert*. |
| Kontakt | Für jedes registrierte Gerät: seine Adresse (SIP-URI), der Qualify-Zustand und die Antwortzeit in Millisekunden. Leer, wenn kein Gerät registriert ist. |
| User-Agent | Hersteller und Firmware, die das Gerät meldet, zum Beispiel Name und Version des Softphones. |

Externe Telefone (Nummern, die über einen Provider oder eine SIP-URI angewählt werden) erscheinen nicht, da sie sich nie registrieren.

## Aktive Gespräche {#active-calls}

Jeder Kanal eines laufenden Gesprächs ist eine Zeile:

| Spalte | Bedeutung |
|---|---|
| Kanal | Technischer Name des Kanals, zum Beispiel `PJSIP/21-00000004`. |
| Anrufer | Rufnummer und Name des Kanals. |
| Gewählt | Die gewählte Nummer. |
| Zustand | Kanalzustand, zum Beispiel *Verbunden* oder *Klingelt*. |
| Anwendung | Was Asterisk mit dem Kanal tut, zum Beispiel `Dial`, `VoiceMail` oder `ConfBridge`. |
| Dauer | Dauer des Kanals. |

*Keine aktiven Gespräche.* bedeutet, dass gerade niemand telefoniert.

## Zustände {#states}

Der farbige Punkt neben einem Zustand zeigt seine Bedeutung auf einen Blick:

- **Grün:** *Registriert*, *Erreichbar*, *Nicht in Benutzung*, *In Benutzung* – das Telefon bzw. der Provider funktioniert.
- **Grau:** unbekannt – Asterisk hat noch keine Information, etwa direkt nach einem Start.
- **Rot:** alle anderen Zustände, etwa *Nicht registriert*, *Abgelehnt*, *Nicht erreichbar*, *Nicht verfügbar* oder *nicht geladen*.

Ein roter Zustand bei einem Telefon bedeutet meist, dass das Gerät ausgeschaltet oder nicht eingerichtet ist oder die Anlage nicht erreicht. Hilfe finden Sie unter [Fehlersuche]({{< relref "/reference/troubleshooting.md#phone-registration" >}}).
