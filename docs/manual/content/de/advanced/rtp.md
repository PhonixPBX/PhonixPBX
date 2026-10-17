---
title: "RTP"
weight: 30
description: "Der UDP-Portbereich für Audio und Video der Gespräche."
---
Unter *Erweitert → RTP* legen Sie den UDP-Portbereich fest, den Asterisk für Audio und Video der Gespräche (RTP) verwendet. Die Firewall von PhonixPBX öffnet diesen Bereich automatisch.

Klicken Sie auf **Speichern** und übernehmen Sie anschließend die Änderungen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Portbereich {#ports}

| Feld | Bedeutung | Standard |
|---|---|---|
| Erster Port | Erster UDP-Port des Bereichs, 1024–65535. | `10000` |
| Letzter Port | Letzter UDP-Port des Bereichs, 1024–65535. Er muss größer als der erste Port sein. | `20000` |

Jedes Gespräch belegt zwei Ports pro Verbindungsabschnitt; ein Gespräch zwischen einem Telefon und einem Provider hat zwei Abschnitte. Der Standardbereich mit 10 000 Ports reicht für jede realistische Last. Verkleinern Sie ihn nur, wenn ein Router oder eine Firewall vor der TK-Anlage das verlangt, und behalten Sie mindestens einige hundert Ports.

> Hinter einem NAT-Router leiten Sie genau diesen UDP-Bereich zusammen mit dem SIP-Port an die TK-Anlage weiter (siehe [NAT]({{< relref "/system/network.md#nat" >}})). Eine fehlende Weiterleitung führt typischerweise zu Gesprächen ohne Ton oder mit Ton nur in eine Richtung.
