---
title: "Firewall"
weight: 50
description: "Paketfilter, Netzwerke für Verwaltung und SIP/IAX sowie Sperren nach fehlgeschlagenen Anmeldungen."
---
Unter *Erweitert → Firewall* steuern Sie den Paketfilter (nftables) von PhonixPBX. Ist er aktiviert, sind nur die Dienste der TK-Anlage erreichbar: die Weboberfläche (HTTP und HTTPS), SSH, falls aktiviert, SIP und IAX auf ihren eingestellten Ports, der RTP-Portbereich sowie der Asterisk-Manager-Port 5038 für die IPv4-Netzwerke unter *Erlaubte Netzwerke* der [Manager-Benutzer]({{< relref "/advanced/manager.md#network" >}}). Alles andere von außen wird verworfen. Die Regeln folgen den Ports unter *Erweitert → SIP*, *IAX* und *RTP* automatisch.

Klicken Sie auf **Speichern** und übernehmen Sie anschließend die Änderungen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

> Stellen Sie sicher, dass das Netzwerk Ihres Computers erlaubt ist, bevor Sie Einschränkungen übernehmen. Falls Sie sich aussperren, verwenden Sie das Konsolenmenü am lokalen Bildschirm oder an der seriellen Schnittstelle (siehe [Konsolenmenü]({{< relref "/getting-started/_index.md#console" >}})).

## Erlaubte Netzwerke {#networks}

| Feld | Bedeutung | Standard |
|---|---|---|
| Firewall aktivieren | Eingehenden Verkehr wie oben beschrieben filtern. Wenn aus, sind alle Ports offen und die Einstellungen unten wirkungslos. | ein |
| Netzwerke, die die TK-Anlage verwalten dürfen | Netzwerke, die die Weboberfläche (Ports 80 und 443) und SSH (Port 22) erreichen dürfen. Ein CIDR pro Zeile, z. B. `192.168.1.0/24`; IPv4 und IPv6. Leer: alle. | leer |
| Netzwerke, die SIP/IAX nutzen dürfen | Netzwerke, die die SIP- und IAX-Ports erreichen dürfen: Ihre Telefone und die Server Ihrer Provider. Gleiches Format. Leer: alle. | leer |

Empfehlungen:

- Wenn die TK-Anlage aus dem Internet erreichbar ist, beschränken Sie *Netzwerke, die die TK-Anlage verwalten dürfen* auf Ihr lokales Netzwerk oder VPN.
- Wenn alle Telefone lokal sind und Ihr Provider seine Serveradressen veröffentlicht, beschränken Sie *Netzwerke, die SIP/IAX nutzen dürfen* auf Ihr LAN und die Netzwerke des Providers. Lassen Sie das Feld nur leer, wenn sich Telefone von wechselnden Adressen registrieren, und verwenden Sie dann starke Passwörter.
- Eine einzelne Adresse schreiben Sie als `/32` (IPv4) oder `/128` (IPv6), z. B. `203.0.113.10/32`.

> Wenn *Netzwerke, die die TK-Anlage verwalten dürfen* eingeschränkt ist, kann eine CA Port 80 für die HTTP-Validierung [automatischer Zertifikate]({{< relref "/advanced/certificate.md#acme" >}}) nicht erreichen. Verwenden Sie in diesem Fall die DNS-Validierung.

## Brute-Force-Schutz {#ban}

PhonixPBX beobachtet die Sicherheitsereignisse von Asterisk. Wenn sich eine Adresse zu oft nicht authentifizieren kann (falsches SIP- oder IAX-Passwort, unbekanntes Konto, falsches AMI-Passwort, Verbindung aus einem nicht erlaubten Netzwerk), wird die Adresse für eine Weile vollständig gesperrt.

| Feld | Bedeutung | Standard |
|---|---|---|
| Adressen nach wiederholten Anmeldefehlern sperren | Den Schutz ein- oder ausschalten. Er wirkt nur bei aktivierter Firewall. | ein |
| Fehlversuche innerhalb von 10 Minuten | Anzahl der Fehlversuche innerhalb von 10 Minuten, nach der eine Adresse gesperrt wird, 1–1000. | `10` |
| Sperrdauer (s) | Wie lange die Adresse gesperrt bleibt, mindestens 60 Sekunden. | `3600` |

Adressen aus *Netzwerke, die die TK-Anlage verwalten dürfen* und, bei statischer LAN-Adresse, aus dem lokalen Netzwerk werden nie gesperrt. Sperren werden im Systemlog protokolliert.

Änderungen an diesen Einstellungen wirken ohne Neustart: Der Sicherheitsmonitor übernimmt sie spätestens etwa eine Minute danach beim nächsten Anmeldefehler und behält die bisher gezählten Fehlversuche.

Die Weboberfläche zeigt keine Liste gesperrter Adressen und bietet keine Schaltfläche, um eine Sperre aufzuheben. Eine Sperre endet nach der Sperrdauer oder wenn eine geänderte Firewall-Konfiguration übernommen wird, wodurch die Regeln neu geladen werden.

> Ein Telefon mit falschem Passwort, das es immer wieder versucht, sperrt seine ganze Adresse, und hinter einem NAT-Router können das alle Geräte eines Standorts sein. Wenn Telefone plötzlich nicht mehr funktionieren, prüfen Sie ihre Passwörter und die [Logs]({{< relref "/status/logs.md" >}}).
