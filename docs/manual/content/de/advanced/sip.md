---
title: "SIP"
weight: 10
description: "SIP-Ports und Transporte (UDP, TCP, TLS), SRTP-Medienverschlüsselung und Registrierungs-Timer."
---
Unter *Erweitert → SIP* stellen Sie die globalen SIP-Parameter von Asterisk (PJSIP) ein: die Ports und Transporte, die Telefone und Provider verwenden, die Medienverschlüsselung und die Registrierungsintervalle. Die Einstellungen der Telefone und Provider selbst finden Sie auf eigenen Seiten unter *Konten*.

Klicken Sie auf **Speichern** und übernehmen Sie anschließend die Änderungen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}). Die Firewall-Regeln folgen den hier eingestellten Ports und Transporten automatisch.

> Eine Änderung des SIP-Ports oder der Transporte betrifft alle Telefone und Provider. Telefone, die noch den alten Port verwenden, können sich erst wieder registrieren, wenn Sie sie ebenfalls umstellen.

## Ports und Transporte {#transports}

| Feld | Bedeutung | Standard |
|---|---|---|
| SIP-Port (UDP/TCP) | Port für SIP über UDP und, wenn aktiviert, über TCP. | `5060` |
| TCP aktivieren | SIP über TCP auf demselben Port annehmen. Wird automatisch aktiviert, wenn ein Provider den TCP-Transport verwendet. | aus |
| TLS aktivieren | SIP über TLS (verschlüsselte Signalisierung) annehmen. Wird automatisch aktiviert, wenn ein Provider den TLS-Transport verwendet. | aus |
| TLS-Port | Port für SIP über TLS. Nur sichtbar mit *TLS aktivieren*. | `5061` |

UDP ist immer aktiv und wird von den meisten Telefonen verwendet.

## TLS {#tls}

SIP über TLS verschlüsselt die Signalisierung einschließlich der Authentifizierung und der SRTP-Schlüssel. Asterisk verwendet das Zertifikat aus [Erweitert → Zertifikat]({{< relref "/advanced/certificate.md" >}}) und TLS 1.2. Mit dem selbstsignierten Standardzertifikat müssen Telefone so eingestellt werden, dass sie es akzeptieren oder die Zertifikatsprüfung überspringen; mit einem Zertifikat einer öffentlichen CA (zum Beispiel über [ACME]({{< relref "/advanced/certificate.md#acme" >}})) funktionieren sie meist ohne Weiteres, sofern sie sich über den Namen im Zertifikat verbinden.

Wenn sich das Zertifikat ändert, wird Asterisk neu gestartet, sobald kein Gespräch aktiv ist, um es zu laden.

## Medienverschlüsselung (SRTP) {#srtp}

| Option | Bedeutung |
|---|---|
| aus | Audio wird unverschlüsselt übertragen (RTP). |
| SRTP (SDES) anbieten, sonst RTP | PhonixPBX bietet Telefonen und Providern verschlüsseltes Audio an (SRTP mit SDES-Schlüsselaustausch) und verwendet normales RTP, wenn die Gegenseite SRTP nicht unterstützt. |

SDES überträgt die Schlüssel in den SIP-Nachrichten. SRTP schützt das Audio deshalb nur, wenn auch die Signalisierung verschlüsselt ist. Verwenden Sie es zusammen mit TLS.

## Registrierungs-Timer {#timers}

| Feld | Bedeutung | Standard |
|---|---|---|
| Standard-Ablaufzeit (s) | Wie lange eine Registrierung von PhonixPBX bei einem Provider gültig ist, bevor sie erneuert wird. Mindestens 60. | `3600` |
| Minimale Ablaufzeit (s) | Kürzestes Registrierungsintervall, das ein Telefon anfordern darf. Kürzere Anforderungen werden auf diesen Wert angehoben. Mindestens 10. | `60` |
| Maximale Ablaufzeit (s) | Längstes Registrierungsintervall, das ein Telefon anfordern darf. Längere Anforderungen werden auf diesen Wert gesenkt. Mindestens 60. | `7200` |
| DNS-SRV-Abfragen verwenden | Bei Providern ohne Port: den Hostnamen zuerst per DNS-SRV auflösen (RFC 3263). Wenn aus, wird direkt der Standardport verwendet (5060 für UDP und TCP, 5061 für TLS). | ein |

Die *Standard-Ablaufzeit* gilt außerdem für Telefone, die bei der Registrierung kein eigenes Intervall anfordern.

## NAT {#nat}

Ob die TK-Anlage hinter einem NAT-Router steht und welche öffentliche Adresse sie hat, stellen Sie unter [System → Netzwerk]({{< relref "/system/network.md#nat" >}}) ein. Leiten Sie bei NAT den SIP-Port (und gegebenenfalls den TLS-Port) sowie den [RTP-Portbereich]({{< relref "/advanced/rtp.md" >}}) am Router an die TK-Anlage weiter.

## Zusätzliche Optionen {#manual}

**Zusätzliche [global]-Optionen** nimmt `key=value`-Zeilen auf, die an die Sektion `[global]` der erzeugten `pjsip.conf` angehängt werden. Das ist für Experten und für Optionen gedacht, die die Weboberfläche nicht anbietet. Falsche Optionen können SIP lahmlegen; prüfen Sie nach dem Übernehmen das [Asterisk-Log]({{< relref "/status/logs.md" >}}).
