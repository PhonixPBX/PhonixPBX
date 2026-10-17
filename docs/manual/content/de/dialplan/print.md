---
title: "Übersicht (Druck)"
weight: 60
description: "Eine druckbare Liste aller internen Nummern, Funktionscodes und Provider-Routen."
---
*Wählplan → Übersicht (Druck)* fasst den Nummernplan der Anlage auf einer Seite zusammen, zum Beispiel zum Aushang am Empfang oder um vor dem Vergeben neuer Nummern freie Bereiche zu finden. Mit **Drucken** drucken Sie die Seite; die Menüleisten werden dabei weggelassen.

Die Seite zeigt die gespeicherte Konfiguration, einschließlich noch nicht übernommener Änderungen.

## Interne Nummern {#internal-numbers}

Alle Telefone, Rufgruppen mit Nummer, Konferenzräume und Anwendungen, sortiert nach Nummer:

| Spalte | Bedeutung |
|---|---|
| Nummer | Die interne Nummer. |
| Typ | *Telefon (SIP)*, *Telefon (IAX)*, *Telefon (extern)*, *Rufgruppe*, *Konferenz* oder *Anwendung*. |
| Name | Die Anruferkennung (Name) eines Telefons oder der Name des Objekts. |
| Details | Die Beschreibung eines Telefons oder einer Anwendung, die Mitgliedsnummern einer Rufgruppe oder *PIN-geschützt* bei einem Konferenzraum. |
| Öffentlich | *ja* (oder der öffentliche Name), wenn die Nummer von außen erreichbar ist. |

IVR-Menüs und Geschäftszeiten sind nicht Teil dieser Liste; siehe [*Wählplan → IVR-Menüs*]({{< relref "/dialplan/ivr.md#list" >}}) und [*Wählplan → Geschäftszeiten*]({{< relref "/dialplan/hours.md#list" >}}).

## Funktionscodes {#feature-codes}

Die Codes für Vermittlung mit und ohne Rückfrage, Gesprächsübernahme und Trennen sowie die Parknummer mit ihren Parkplätzen, wie unter [*Wählplan → Vermittlung & Parken*]({{< relref "/dialplan/transfers.md" >}}) eingestellt.

## Provider {#providers}

Für jeden Provider die [Wählmuster]({{< relref "/accounts/providers.md#dial-patterns" >}}) für ausgehende Anrufe und die [eingehenden Routen]({{< relref "/accounts/providers.md#incoming-routes" >}}) als *Muster → Ziel* (*alle* bei Routen ohne Muster).
