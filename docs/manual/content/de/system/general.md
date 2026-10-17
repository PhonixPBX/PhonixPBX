---
title: "Grundeinstellungen"
weight: 10
description: "Hostname, Domain, Zeitzone, Zeitserver, Töne, Sprache der Ansagen, mDNS und SSH-Zugang."
---
*System → Grundeinstellungen* enthält die grundlegende Identität des Systems: seinen Namen im Netzwerk, die Zeiteinstellungen, die länderspezifischen Töne und die Standardsprache der Ansagen. Außerdem schalten Sie hier die mDNS-Bekanntgabe und den SSH-Zugang ein oder aus.

Klicken Sie auf **Speichern**, um die Einstellungen zu speichern. Sie werden wirksam, wenn Sie die Änderungen übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Name und Domain {#name}

| Feld | Bedeutung | Standard |
|---|---|---|
| Hostname | Name des Systems, 1–63 Buchstaben, Ziffern oder `-`, ohne Punkte. Er wird als Hostname des Systems, für das TLS-Zertifikat, für Asterisk und für den mDNS-Namen `<hostname>.local` verwendet. | `phonix` |
| Domain | DNS-Domain des Systems. Zusammen mit dem Hostnamen ergibt sie den vollständigen Namen (zum Beispiel `phonix.example.com`). Sie ist auch die DNS-Suchdomain, wenn PhonixPBX die Resolver-Konfiguration schreibt (statische Adresse oder DNS-Server unter *System → Netzwerk* eingetragen). | `local` |

In einem Container (LXC/Incus oder OCI) ändert PhonixPBX den Hostnamen des Containers selbst nicht; dieser wird auf dem Container-Host festgelegt. Der Hostname auf dieser Seite wird von PhonixPBX trotzdem für das Zertifikat und Asterisk verwendet.

## Zeit {#time}

| Feld | Bedeutung | Standard |
|---|---|---|
| Zeitzone | Zeitzone des Systems, aus einer durchsuchbaren Liste gewählt. Sie bestimmt die lokale Zeit von System und Asterisk, zum Beispiel in Logs, in den Zeitstempeln von Mailbox-Nachrichten und für die Zeitbedingungen der [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}). | `UTC` |
| Zeitserver | NTP-Server, mit denen das System seine Uhr abgleicht, einer pro Zeile (Hostname oder IP-Adresse). | `pool.ntp.org` |

In einem Container werden die Zeitserver nicht verwendet: Die Uhrzeit kommt vom Container-Host.

## Töne und Sprache {#tones-language}

| Feld | Bedeutung | Standard |
|---|---|---|
| Tonzone | Länderspezifische Wähl-, Besetzt- und Ruftöne, die Anrufer hören. Wählen Sie das Land, in dem die Telefone verwendet werden. | USA |
| Standardsprache der Ansagen | Sprache der Asterisk-Ansagen (Mailbox, Konferenzen usw.), wenn ein Telefon oder Provider keine eigene festlegt. Verfügbar: Englisch, Englisch (UK), Deutsch, Französisch, Spanisch, Italienisch, Niederländisch, Dänisch, Schwedisch, Polnisch, Portugiesisch (Brasilien), Russisch, Japanisch. | Englisch |

Die Sprache der Weboberfläche wird nicht hier eingestellt: Jeder Administrator wählt sie für sein eigenes Konto, siehe [Ihr Konto]({{< relref "/getting-started/_index.md#account" >}}).

## mDNS-Bekanntgabe {#mdns}

**Im lokalen Netzwerk bekannt geben (mDNS)** (Standard: ein) macht die Weboberfläche unter `https://<hostname>.local/` erreichbar und lässt Suchwerkzeuge sie als HTTPS-Dienst finden. Das funktioniert unter macOS, iOS, Windows 10 und neuer, Android 12 und neuer sowie Linux mit nss-mdns.

- Geben Sie jeder PhonixPBX im selben LAN einen eigenen Hostnamen. Verwenden zwei Systeme denselben Namen, wird das zweite als `<hostname>-2.local` bekannt gegeben.
- In einem LXC-/Incus-Container funktioniert mDNS, wenn der Container an eine Bridge Ihres LANs angeschlossen ist.
- Das OCI-Container-Image gibt sich nicht bekannt; die Option wird dort nicht angezeigt.

## SSH-Zugang {#ssh}

SSH ist standardmäßig ausgeschaltet. Sie benötigen es nur zur Fehlersuche; alles andere erledigen Sie in der Weboberfläche, im Konsolenmenü oder mit dem Befehl `phonix` (siehe [Kommandozeile]({{< relref "/reference/cli.md" >}})).

| Feld | Bedeutung | Standard |
|---|---|---|
| SSH-Zugang aktivieren (Anmeldung als root mit Schlüssel oder Passwort) | Startet den SSH-Server und öffnet Port 22 in der Firewall. Sie melden sich als `root` an. | aus |
| SSH-Passwort für root | Passwort für die Anmeldung als `root` über SSH, mindestens 8 Zeichen. Das Passwort wird nur als Hash gespeichert und nie wieder angezeigt. Lassen Sie das Feld leer, um ein bereits gesetztes Passwort beizubehalten. | keines |
| Passwort entfernen (nur Anmeldung mit Schlüssel) | Wird angezeigt, wenn ein Passwort gesetzt ist. Löscht das Passwort, sodass nur noch die Anmeldung mit Schlüssel möglich ist. | aus |

Für die Anmeldung mit Schlüssel legen Sie Ihre öffentlichen Schlüssel in `/data/ssh/authorized_keys` ab. Ohne Passwort ist nur die Anmeldung mit Schlüssel möglich.

> Aktivieren Sie SSH nur bei Bedarf. Unter [Erweitert → Firewall]({{< relref "/advanced/firewall.md" >}}) können Sie zusätzlich einschränken, aus welchen Netzen SSH und die Weboberfläche erreichbar sind.

Beachten Sie, dass das Root-Dateisystem auf dem Gerät schreibgeschützt ist: Änderungen, die Sie über SSH daran vornehmen, gehen beim nächsten Neustart verloren. Die Konfiguration liegt in der Datenbank `/data/phonix.db` und wird über die Weboberfläche oder den Befehl `phonix` geändert.
