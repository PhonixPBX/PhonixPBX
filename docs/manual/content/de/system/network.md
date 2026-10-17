---
title: "Netzwerk"
weight: 20
description: "LAN-Adresse per DHCP oder statisch, DNS-Server, IPv6 und die NAT-Einstellungen für SIP."
---
Unter *System → Netzwerk* legen Sie fest, wie das System seine Adresse im LAN erhält, und teilen Asterisk mit, ob es hinter einem NAT-Router steht. Beim ersten Start erhält die erste Netzwerkkarte (`eth0`) ihre Adresse per DHCP. Kennt PhonixPBX die aktuelle Adresse des gewählten Interfaces, wird sie oben auf der Seite angezeigt.

Klicken Sie auf **Speichern** und übernehmen Sie anschließend die Änderungen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

> Eine Änderung der Adresse unterbricht die Verbindung zur Weboberfläche. Öffnen Sie nach dem Übernehmen die neue Adresse im Browser. Haben Sie sich ausgesperrt, können Sie die LAN-Adresse im Konsolenmenü am lokalen Bildschirm oder an der seriellen Schnittstelle neu setzen (siehe [Konsolenmenü]({{< relref "/getting-started/_index.md#console" >}})).

## LAN-Interface {#lan}

| Feld | Bedeutung | Standard |
|---|---|---|
| Interface | Die Netzwerkkarte, die konfiguriert wird. Die Liste zeigt die Interfaces, die das System hat. | `eth0` |
| Konfiguration | **DHCP**: Adresse, Gateway und DNS-Server vom DHCP-Server Ihres Netzwerks beziehen. **Statisch**: die unten eingetragene Adresse verwenden. | DHCP |
| IP-Adresse | Statische IPv4-Adresse des Systems. Nur bei *Statisch* sichtbar. | `192.168.1.2` |
| Präfix | Netzgröße in Präfix-Schreibweise, 1–32 (`24` = `255.255.255.0`). Nur bei *Statisch* sichtbar. | `24` |
| Gateway | Standard-Gateway (Router). Optional. Nur bei *Statisch* sichtbar. | leer |
| DNS-Server | DNS-Server, einer pro Zeile (IPv4 oder IPv6). Bei DHCP leer lassen, um die Server vom DHCP-Server zu verwenden. Bei statischer Adresse ohne DNS-Server wird das Gateway als DNS-Server verwendet. | leer |
| IPv6 | **Automatisch (SLAAC)**: Das Interface bezieht eine IPv6-Adresse aus den Router Advertisements. **Aus**: keine automatische IPv6-Konfiguration. | Automatisch (SLAAC) |

Eine Telefonanlage sollte eine feste Adresse haben, weil Telefone und Provider sie finden müssen. Konfigurieren Sie hier entweder eine statische Adresse oder reservieren Sie die Adresse des Systems in Ihrem DHCP-Server.

## NAT / öffentliche Adresse {#nat}

Diese Einstellungen sind erforderlich, wenn Provider oder entfernte Telefone das System über einen NAT-Router erreichen, zum Beispiel einen üblichen Internet-Router. Asterisk trägt dann für alles außerhalb des lokalen Netzes die öffentliche Adresse in seine SIP- und SDP-Nachrichten ein, damit die Sprache in beide Richtungen übertragen wird.

| Feld | Bedeutung | Standard |
|---|---|---|
| Topologie | **Öffentliche Adresse / kein NAT**: Das System hat eine öffentliche Adresse, oder alle Telefone und Provider befinden sich im lokalen Netz. **NAT, statische öffentliche IP**: Der Router hat eine feste öffentliche IPv4-Adresse. **NAT, dynamische IP (Hostname)**: Die öffentliche Adresse des Routers wechselt, und ein DNS-Name zeigt auf sie. | Öffentliche Adresse / kein NAT |
| Öffentliche IP-Adresse | Die feste öffentliche IPv4-Adresse des Routers. Nur bei *NAT, statische öffentliche IP* sichtbar. | leer |
| Öffentlicher Hostname | Ein DNS-Name, der immer auf die öffentliche Adresse des Routers zeigt, zum Beispiel ein DynDNS-Name. Nur bei *NAT, dynamische IP (Hostname)* sichtbar. | leer |

Das lokale Netz wird aus dem LAN-Interface ermittelt (statische Adresse und Präfix oder das Netz der DHCP-Adresse). Leiten Sie bei NAT außerdem den SIP-Port und den RTP-Portbereich am Router an das System weiter (siehe [Erweitert → SIP]({{< relref "/advanced/sip.md" >}}) und [Erweitert → RTP]({{< relref "/advanced/rtp.md" >}})).

## In einem Container {#containers}

In einem LXC-/Incus-Systemcontainer oder im OCI-Container-Image gehören Adresse, Gateway, DNS-Server und Hostname des Containers zum Container-Host. Die Seite zeigt einen Hinweis, und PhonixPBX schreibt keine Netzwerkkonfiguration:

- Die Einstellungen *Konfiguration*, *IP-Adresse*, *Präfix*, *Gateway*, *DNS-Server* und *IPv6* werden nicht angewendet. Konfigurieren Sie das Netzwerk in den Container-Einstellungen von Proxmox VE, Incus, LXC, Docker oder Podman.
- *Interface* legt weiterhin fest, welche Adresse für SIP verwendet wird.
- Die NAT-Einstellungen gelten wie gewohnt.

Damit Telefone in Ihrem LAN das System erreichen, schließen Sie einen LXC-/Incus-Container an eine Bridge Ihres LANs an, sodass er eine eigene Adresse erhält.
