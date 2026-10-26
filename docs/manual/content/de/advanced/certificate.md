---
title: "Zertifikat"
weight: 60
description: "Das TLS-Zertifikat für Weboberfläche und SIP über TLS: selbstsigniert, hochgeladen oder von Let's Encrypt/ACME."
---
Unter *Erweitert → Zertifikat* verwalten Sie das TLS-Zertifikat, das die Weboberfläche (HTTPS) und SIP über TLS verwenden. Es gibt drei Wege zu einem Zertifikat:

- ein **selbstsigniertes Zertifikat**, das beim ersten Start automatisch erstellt wird;
- ein **hochgeladenes Zertifikat** Ihrer eigenen oder einer kommerziellen CA;
- ein **automatisches Zertifikat** einer ACME-CA wie Let's Encrypt, das PhonixPBX selbst erneuert.

Oben zeigt die Seite das verwendete Zertifikat. Darunter enthalten die Reiter **Automatisch (ACME)**, **Hochladen** und **Selbstsigniert** je einen dieser Wege. Der Reiter des Wegs, über den das aktuelle Zertifikat kam, trägt die Markierung *aktiv* und ist beim Laden der Seite geöffnet.

Änderungen auf dieser Seite wirken sofort, ohne Übernehmen: Der Webserver lädt das Zertifikat neu, und wenn SIP über TLS verwendet wird, startet Asterisk neu, sobald kein Gespräch aktiv ist, um es zu laden.

## Aktuelles Zertifikat {#current}

Die Karte zeigt die Namen, für die das verwendete Zertifikat gilt, das Datum, bis zu dem es gültig ist, und die verbleibenden Tage (orange unter 30 Tagen, rot unter 14). Die Markierung *selbstsigniert* kennzeichnet ein selbstsigniertes Zertifikat, *wird automatisch erneuert* eine aktive ACME-Einrichtung. **Details** zeigt **Betreff**, **Namen**, **Aussteller** und den SHA-256-Fingerabdruck. Vergleichen Sie den Fingerabdruck mit dem, den Ihr Browser anzeigt, um sicherzugehen, dass Sie mit Ihrer TK-Anlage verbunden sind.

Die Karte zeigt auch das Ergebnis der letzten ACME-Anfrage; während eine Anfrage läuft, aktualisiert sich die Anzeige von selbst.

## Selbstsigniertes Zertifikat {#self-signed}

Beim ersten Start erstellt PhonixPBX ein selbstsigniertes Zertifikat für `<Hostname>.<Domain>` aus [System → Grundeinstellungen]({{< relref "/system/general.md#name" >}}). Browser warnen bei einem solchen Zertifikat, weil keine vertrauenswürdige CA es signiert hat; die Verbindung ist trotzdem verschlüsselt.

Der Reiter **Selbstsigniert** zeigt den Namen, für den das Zertifikat erstellt wird. **Neues selbstsigniertes Zertifikat erstellen** ersetzt das aktuelle Zertifikat durch ein neues selbstsigniertes, zum Beispiel nach einer Änderung des Hostnamens. Dabei werden automatische Zertifikate deaktiviert.

## Zertifikat hochladen {#upload}

Auf dem Reiter **Hochladen**:

| Feld | Bedeutung |
|---|---|
| Zertifikat (PEM, darf die Kette enthalten) | Das Zertifikat im PEM-Format (`.pem`, `.crt`, `.cer`). Zwischenzertifikate gehören in dieselbe Datei hinter das Serverzertifikat. |
| Privater Schlüssel (PEM, unverschlüsselt) | Der passende private Schlüssel im PEM-Format (`.pem`, `.key`), ohne Passphrase. |

Klicken Sie auf **Installieren**. PhonixPBX prüft, ob die Dateien gültiges PEM sind und der Schlüssel zum Zertifikat passt, und installiert sie dann. Das Installieren eines Zertifikats deaktiviert automatische Zertifikate. Jede Datei darf bis zu 1 MB groß sein.

## Automatisches Zertifikat (ACME) {#acme}

PhonixPBX kann mit dem Client `lego` ein Zertifikat von einer ACME-CA beziehen und automatisch erneuern. Der Reiter **Automatisch (ACME)** hat zwei Abschnitte: *Konto und Domainnamen* und *Validierung*. Das Ergebnis der letzten Anfrage steht in der Karte *Aktuelles Zertifikat*.

| Feld | Bedeutung | Standard |
|---|---|---|
| Zertifikat automatisch beziehen und erneuern | Automatische Zertifikate einschalten. | aus |
| Zertifizierungsstelle | **Let's Encrypt**; **Let's Encrypt Staging (Test, nicht vertrauenswürdig)**, um die Einrichtung ohne Ratenbegrenzungen auszuprobieren; **ZeroSSL**; oder **Anderer ACME-Server**. | Let's Encrypt |
| ACME-Directory-URL | Directory-URL des ACME-Servers, muss mit `https://` beginnen. Nur bei *Anderer ACME-Server*. | leer |
| EAB-Key-ID, EAB-HMAC-Schlüssel | External Account Binding. Erforderlich bei ZeroSSL (aus dem ZeroSSL-Dashboard) und bei manchen privaten CAs. Der gespeicherte HMAC-Schlüssel wird nicht angezeigt; lassen Sie das Feld leer, um ihn beizubehalten. | leer |
| E-Mail-Adresse des Kontos | Kontaktadresse des ACME-Kontos; die CA schickt dorthin Hinweise zu ablaufenden Zertifikaten. Erforderlich. | leer |
| Domainnamen | Die Namen, für die das Zertifikat ausgestellt wird, einer pro Zeile. Es müssen öffentliche, vollständige DNS-Namen sein; Wildcards (`*.example.com`) erfordern die DNS-Validierung. Leer: `<Hostname>.<Domain>`. | leer |
| Validierung | Wie die CA prüft, dass Sie die Namen kontrollieren: **HTTP (Port 80)** oder **DNS-Provider-API**. | HTTP (Port 80) |

**Speichern** speichert die Einstellungen. **Speichern und Zertifikat jetzt anfordern** speichert sie und startet sofort eine Anfrage. Die Anfrage läuft im Hintergrund; ist sie erfolgreich, lädt die Seite neu und zeigt das neue Zertifikat. Schlägt sie fehl, wird der Fehler angezeigt, und **lego-Ausgabe** enthält das vollständige Protokoll des Clients.

> Probieren Sie eine neue Einrichtung zuerst mit *Let's Encrypt Staging* aus: Dessen Zertifikate vertrauen Browser nicht, aber die Ratenbegrenzungen sind deutlich großzügiger. Wechseln Sie zu *Let's Encrypt*, sobald die Anfrage funktioniert.

### HTTP-Validierung {#http-01}

Die CA verbindet sich für jeden Namen mit `http://<Name>/.well-known/acme-challenge/`. Dafür muss gelten:

- Jeder Name löst im öffentlichen DNS auf die TK-Anlage auf oder auf einen Router, der TCP-Port 80 an sie weiterleitet.
- Port 80 ist aus dem Internet erreichbar.
- *Netzwerke, die die TK-Anlage verwalten dürfen* unter [Erweitert → Firewall]({{< relref "/advanced/firewall.md#networks" >}}) ist leer. Ist das Feld eingeschränkt, zeigt die Seite eine Warnung; verwenden Sie dann die DNS-Validierung.

### DNS-Validierung {#dns-01}

Die CA prüft einen TXT-Eintrag, den `lego` über die API Ihres DNS-Providers anlegt. Das funktioniert auch für TK-Anlagen, die nicht aus dem Internet erreichbar sind, und ist für Wildcard-Namen erforderlich.

| Feld | Bedeutung |
|---|---|
| DNS-Provider | Der Anbieter, der die DNS-Zone Ihrer Domain betreibt. Eingebaut sind Azure DNS, Cloudflare, deSEC, DigitalOcean, DuckDNS, Gandi LiveDNS, GoDaddy, Hetzner, Hurricane Electric, Infomaniak, INWX, IONOS, Linode / Akamai, Namecheap, netcup, OVH, Porkbun, Dynamisches Update nach RFC 2136 (BIND, Knot, ...) und Amazon Route 53. Nach der Auswahl zeigt die Seite die Felder für seine Zugangsdaten. |
| Felder für Zugangsdaten | API-Token, Schlüssel oder Ähnliches, je nach Anbieter. Felder mit *(optional)* dürfen leer bleiben. Gespeicherte Geheimnisse werden nicht angezeigt; lassen Sie ein Feld leer, um den Wert beizubehalten. |
| lego-Provider-Code | Bei *Anderer lego-Provider ...*: der Code eines beliebigen von lego unterstützten Anbieters, z. B. `powerdns`. Siehe die Liste der lego-DNS-Provider. |
| Zugangsdaten | Bei *Anderer lego-Provider ...*: die Umgebungsvariablen für diesen Anbieter laut lego-Dokumentation, `NAME=Wert` pro Zeile. Gespeicherte Werte werden nicht angezeigt; schreiben Sie `NAME=`, um einen gespeicherten Wert beizubehalten. |
| DNS-Resolver für die Propagationsprüfung (optional) | Unter **Erweitert**. DNS-Server, bei denen `lego` prüft, ob der TXT-Eintrag sichtbar ist, z. B. `1.1.1.1:53`. Nützlich, wenn die TK-Anlage ihre eigene Domain über einen internen DNS-Server auflöst. |

> Geben Sie den API-Zugangsdaten so wenige Rechte wie möglich, zum Beispiel ein Cloudflare-Token, das nur DNS-Einträge einer Zone bearbeiten darf.

## Erneuerung {#renewal}

Sind automatische Zertifikate aktiviert, prüft ein täglicher Job das Zertifikat und fordert ein neues an, wenn es in weniger als 30 Tagen abläuft, wenn die Domainnamen geändert wurden oder wenn ein selbstsigniertes Zertifikat installiert ist. Ein erneuertes Zertifikat wird automatisch installiert und geladen.

Das Hochladen eines Zertifikats oder das Erstellen eines selbstsignierten Zertifikats deaktiviert automatische Zertifikate. Schalten Sie sie wieder ein, um zu ACME zurückzukehren.

Zertifikat, Schlüssel und ACME-Konto sind Teil des [Backups]({{< relref "/system/backup.md" >}}).
