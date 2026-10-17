---
title: "IAX"
weight: 20
description: "IAX2-Port, Firewall-Zugang und Jitter-Buffer."
---
Unter *Erweitert → IAX* stellen Sie die globalen Optionen von IAX2 ein, dem Inter-Asterisk eXchange Protocol. IAX wird von manchen Providern und zur Kopplung von Asterisk-Systemen verwendet; es überträgt Signalisierung und Audio über einen einzigen UDP-Port und kommt dadurch gut durch NAT. Telefone und Provider mit IAX richten Sie wie SIP-Konten unter *Konten* ein.

Klicken Sie auf **Speichern** und übernehmen Sie anschließend die Änderungen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Einstellungen {#settings}

| Feld | Bedeutung | Standard |
|---|---|---|
| IAX-Verbindungen annehmen (Firewall) | Den IAX-Port in der Firewall öffnen. Schalten Sie das aus, wenn Sie keine IAX-Telefone oder -Provider verwenden. Es ändert sich nur die Firewall-Regel; ausgehende IAX-Verbindungen, etwa eine Registrierung bei einem Provider, funktionieren weiter. | ein |
| IAX-Port | UDP-Port für IAX, 1–65535. | `4569` |
| Jitter-Buffer aktivieren | Ungleichmäßig eintreffende Pakete bei IAX-Gesprächen ausgleichen, auf Kosten einer etwas höheren Verzögerung. | aus |
| Jitter-Buffer erzwingen | Den Jitter-Buffer auch dann verwenden, wenn die Gegenseite des Gesprächs den Jitter selbst ausgleichen könnte. | aus |
| Zusätzliche [general]-Optionen | `key=value`-Zeilen, die an die Sektion `[general]` der `iax.conf` angehängt werden, für Experten. | leer |

Wenn unter [Erweitert → Firewall]({{< relref "/advanced/firewall.md#networks" >}}) die Netzwerke eingeschränkt sind, die SIP/IAX nutzen dürfen, gilt diese Einschränkung auch für den IAX-Port.
