---
title: "Graphen"
weight: 30
description: "Live-Graphen der CPU-Auslastung und des Netzwerkverkehrs."
---
*Status → Graphen* zeigt zwei große Live-Graphen. Sie sehen daran, ob die Anlage zu Stoßzeiten überlastet ist oder wie viel Bandbreite die Gespräche brauchen.

## CPU-Last {#cpu}

Der obere Graph, *CPU-Last*, zeigt die CPU-Auslastung des ganzen Systems in Prozent (0–100 %, alle CPUs zusammen). Eine gewöhnliche Anlage mit wenigen Gesprächen bleibt im niedrigen einstelligen Bereich. Dauerhaft hohe Werte deuten auf Umkodierung zwischen Codecs, viele Konferenzteilnehmer oder ein zu kleines System hin.

## Netzwerkverkehr {#network}

Der untere Graph, *Netzwerkverkehr (alle Interfaces)*, zeigt den eingehenden (*in*) und ausgehenden (*out*) Verkehr in Bytes pro Sekunde, summiert über alle Netzwerkschnittstellen außer der Loopback-Schnittstelle. Als Faustregel braucht ein Gespräch mit dem Codec G.711 (alaw/ulaw) samt Paket-Overhead etwa 10 KB/s pro Richtung und Gesprächsseite.

## Wie die Werte erfasst werden {#sampling}

Die Anlage zeichnet diese Werte nicht im Hintergrund auf. Sie werden nur gemessen, solange eine Seite mit Graphen geöffnet ist – diese Seite oder die kleinen Graphen auf [Status → Übersicht]({{< relref "/status/summary.md#graphs" >}}) –, auf dieser Seite alle zwei Sekunden. Die Anlage behält die letzten 120 Messwerte, auf dieser Seite also etwa vier Minuten. Öffnen Sie die Seite nach einer Weile wieder, beginnen die Graphen leer und füllen sich, während Sie zusehen; bis zu den ersten Werten zeigt der Graph „collecting data...“.

Für eine Langzeitüberwachung sammeln Sie die Metriken mit Prometheus über `/api/v1/metrics`, siehe [REST-API und MCP]({{< relref "/reference/api.md#metrics" >}}).
