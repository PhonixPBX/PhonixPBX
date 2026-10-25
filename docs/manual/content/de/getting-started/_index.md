---
title: "Erste Schritte"
weight: 10
icon: rocket
description: "Erster Start, Anmeldung, die Bedienoberfläche, Änderungen übernehmen und das Konsolenmenü."
---
Dieses Kapitel führt Sie von einer frisch installierten PhonixPBX bis zum ersten Gespräch. Wie Sie das Disk-Image schreiben oder den Container anlegen, steht in der Installationsanleitung (`docs/INSTALL.md` im Quellcode-Repository); hier beginnen wir mit dem ersten Start.

## Erster Start und die Adresse der Anlage {#first-boot}

Schließen Sie das Netzwerkkabel an und schalten Sie das Gerät ein. Die erste Netzwerkkarte bezieht ihre Adresse per **DHCP**. Der erste Start dauert ein bis zwei Minuten. Dabei

- vergrößert die Anlage die Datenpartition auf die ganze Festplatte bzw. Speicherkarte,
- legt sie die Datenbank, ein selbstsigniertes HTTPS-Zertifikat und die SSH-Hostschlüssel an,
- erzeugt sie ein **zufälliges Passwort** für den Administrator `admin`.

Sobald sie bereit ist, zeigt der Bildschirm (und die serielle Konsole, 115200 Baud) eine Meldung wie diese:

```
  PhonixPBX 1.3.0

  LAN (eth0, DHCP): 192.168.1.23
  Web interface: https://192.168.1.23/
                 https://phonix.local/

  Initial login: admin / 3W7YaMJMUei5
  (you must change the password at the first login)
```

Hat das Gerät keinen Bildschirm, finden Sie es auf zwei anderen Wegen:

- Öffnen Sie `https://phonix.local/` (bzw. `https://<hostname>.local/`, nachdem Sie den Hostnamen geändert haben). Die Anlage meldet sich per mDNS im LAN an; das funktioniert unter macOS, iOS, Windows 10 und neuer, Android 12 und neuer sowie Linux mit nss-mdns. Die Ankündigung lässt sich unter [System → Grundeinstellungen]({{< relref "/system/general.md#mdns" >}}) abschalten.
- Suchen Sie die Adresse in der DHCP-Liste Ihres Routers.

In einem Container steht das initiale Passwort stattdessen im Container-Log (`docker logs phonix`) bzw. auf der Container-Konsole; im OCI-Image gibt es kein mDNS.

## Anmelden {#login}

1. Öffnen Sie `https://<adresse>/` im Browser. Ein Aufruf über `http://` wird auf HTTPS umgeleitet.
2. Bis Sie ein richtiges Zertifikat installieren, verwendet die Anlage ein **selbstsigniertes Zertifikat**; der Browser warnt deshalb beim ersten Aufruf. Prüfen Sie, ob die Adresse stimmt, und bestätigen Sie die Warnung. Um die Warnung loszuwerden, beziehen Sie unter [Erweitert → Zertifikat]({{< relref "/advanced/certificate.md" >}}) ein kostenloses Zertifikat von Let's Encrypt oder laden Ihr eigenes hoch.
3. Geben Sie auf der Seite *Bei Ihrer TK-Anlage anmelden* den Benutzernamen `admin` und das initiale Passwort von der Konsole ein und klicken Sie auf *Anmelden*.

Nach fünf Fehlversuchen innerhalb von fünf Minuten wird die Anmeldung für einige Minuten gesperrt (*Zu viele Fehlversuche. Bitte warten Sie einige Minuten.*).

Ist das initiale Passwort verloren, setzen Sie es im [Konsolenmenü](#console) mit *Reset administrator password* zurück.

## Passwort ändern {#password}

Bei der ersten Anmeldung landen Sie direkt auf der Seite *Passwort ändern* mit dem Hinweis *Bitte wählen Sie ein eigenes Passwort, bevor Sie fortfahren.* Andere Seiten sind erst erreichbar, wenn Sie ein eigenes Passwort gesetzt haben.

Sie können Ihr Passwort jederzeit ändern: Öffnen Sie das Benutzermenü (Ihre Initialen oben rechts) und wählen Sie *Passwort ändern*.

| Feld | Bedeutung |
|---|---|
| Aktuelles Passwort | Ihr bisheriges Passwort (bei der ersten Anmeldung das initiale Passwort). |
| Neues Passwort | Mindestens 8 Zeichen. |
| Neues Passwort wiederholen | Dasselbe noch einmal, um Tippfehler auszuschließen. |

Weitere Administratoren und deren Passwörter verwalten Sie unter [Erweitert → Administratoren]({{< relref "/advanced/users.md" >}}).

## Einstellungen: die Sprache der Oberfläche {#account}

Öffnen Sie das Benutzermenü und wählen Sie *Einstellungen*. Unter *Sprache* legen Sie die Sprache der Weboberfläche für Ihr eigenes Konto fest; ohne Auswahl gilt *English (Standard)*. Die Einstellung gilt pro Administrator und wirkt sofort nach *Speichern*.

Die Sprache der Ansagen, die Anrufer hören, ist eine eigene Einstellung, siehe [System → Grundeinstellungen]({{< relref "/system/general.md#tones-language" >}}).

## Sich zurechtfinden {#navigation}

- Das **Menü** links hat dieselben Bereiche wie AskoziaPBX: *System*, *Konten*, *Wählplan*, *Dienste*, *Status* und *Erweitert*. Ein Klick auf einen Bereich klappt seine Seiten auf. Auf kleinen Bildschirmen ist das Menü hinter der Schaltfläche oben eingeklappt.
- Das PhonixPBX-Logo führt zu *Status → Übersicht*, der Startseite.
- Die **obere Leiste** zeigt den Hostnamen der Anlage, das Mond- bzw. Sonnensymbol zum Umschalten zwischen **dunklem Modus** und **hellem Modus** (der Browser merkt sich die Wahl) und das Benutzermenü mit *Einstellungen*, *Passwort ändern* und *Abmelden*.
- Jede Seite hat rechts neben dem Seitentitel eine Schaltfläche **Hilfe** (Fragezeichen). Sie öffnet das passende Kapitel dieses Handbuchs.
- Die Fußzeile zeigt die installierte Version, einen Link zu diesem *Handbuch* und zur interaktiven *API*-Dokumentation.

Nach einer Zeit ohne Aktivität werden Sie automatisch abgemeldet; die Dauer stellen Sie unter [Erweitert → Weboberflächenoptionen]({{< relref "/advanced/gui.md" >}}) ein.

## Listen {#lists}

Listen wie *Konten → Telefone* lassen sich durchsuchen und werden in Seiten angezeigt. Suchfeld und Seitengröße stehen über der Tabelle, die Seitenlinks darunter.

- **Suchen**: Tippen Sie in das Suchfeld über der Liste (sein Platzhaltertext nennt die durchsuchten Spalten, bei Telefonen *Nummer, Name oder Beschreibung*). Die Liste folgt beim Tippen, kurz nachdem Sie innehalten; die Eingabetaste sucht sofort, und das × im Feld leert es. Die Suche findet den Text an beliebiger Stelle in diesen Spalten, Groß- und Kleinschreibung spielen keine Rolle, auch nicht bei Umlauten und anderen Akzenten: „mei“ findet „Meier“, „müller“ findet „Müller“. Die Treffer werden in den Zeilen hervorgehoben. Neben dem Feld steht die Anzahl der Telefone, bei einer Suche die Treffer von allen, zum Beispiel *11 von 64*. Passt nichts, sagt die Liste das, zum Beispiel *Keine Telefone gefunden*, mit einer Schaltfläche *Suche zurücksetzen*.
- **Pro Seite**: Wählen Sie, wie viele Zeilen eine Seite zeigt: 25, 50 (Standard), 100 oder *Alle*.
- **Seitenlinks**: Passt die Liste nicht auf eine Seite, zeigt die untere Zeile, welche Zeilen Sie sehen (zum Beispiel *51–100 von 500*), und Links zur ersten und letzten Seite, zu den Seiten um die aktuelle herum sowie ‹ und › für die vorherige und nächste Seite.

Suche, Seite und Seitengröße sind Teil der Adresse im Browser (zum Beispiel `/accounts/phones?q=meier&page=2`). Neu laden, die Zurück-Taste, ein Lesezeichen oder ein Link, den Sie einer Kollegin schicken, zeigen dieselbe Ansicht. Ein neuer Aufruf über das Menü beginnt ohne Suche auf der ersten Seite mit 50 Zeilen.

Nachdem Sie eine Zeile gelöscht haben, werden die Anzahl und die Seitenlinks bei der nächsten Suche oder dem nächsten Seitenwechsel aktualisiert.

## Änderungen speichern und übernehmen {#apply}

PhonixPBX trennt das **Speichern** vom **Aktivieren**. Wenn Sie ein Formular speichern, steht die Änderung sofort in der Datenbank, die Telefonanlage läuft aber noch mit der alten Konfiguration. Oben auf jeder Seite erscheint ein gelber Hinweis:

> **Ausstehende Änderungen** — die Konfiguration wurde geändert (Telefone und Provider, Wählplan). Übernehmen Sie sie, um sie zu aktivieren.

Die Liste in Klammern nennt die geänderten Bereiche. Klicken Sie auf **Änderungen übernehmen**, um sie zu aktivieren. Die Anlage erzeugt dann die Konfigurationsdateien, schreibt nur die Dateien, die sich tatsächlich geändert haben, und lädt nur die betroffenen Teile neu (zum Beispiel den SIP-Stack oder den Wählplan). Laufende Gespräche werden dabei normalerweise nicht unterbrochen.

- Bei Erfolg wird der Hinweis grün: *Konfiguration übernommen.*, mit der Zahl der Neuladeaktionen.
- Schlägt etwas fehl, zeigt der Hinweis *Das Übernehmen der Konfiguration ist fehlgeschlagen.* mit den Fehlermeldungen und bleibt stehen, sodass Sie die Eingabe korrigieren und erneut übernehmen können.

Sie können mehrere Änderungen vornehmen und gemeinsam übernehmen. Der Hinweis nennt diese Bereiche:

| Bereich im Hinweis | Geändert über |
|---|---|
| Telefone und Provider | *Konten → Telefone*, *Konten → Provider* |
| Wählplan | alles unter *Wählplan* |
| Mailbox, Telefonkonferenzen und Medien | *Dienste → Mailbox*, *Telefonkonferenzen*, *Medien* |
| E-Mail-Benachrichtigungen | *Dienste → Benachrichtigungen* |
| SIP-, IAX- und RTP-Einstellungen | *Erweitert → SIP*, *IAX*, *RTP* und die Netzwerkeinstellungen |
| Asterisk-Manager-Benutzer | *Erweitert → Manager (AMI)* |
| Netzwerk | *System → Netzwerk* und der Hostname |
| Systemeinstellungen | *System → Grundeinstellungen* |
| Firewall | *Erweitert → Firewall* |

Manche Aktionen wirken **sofort**, ohne *Änderungen übernehmen*:

- das Umschalten des Modus von Geschäftszeiten (*Automatisch*, *Geöffnet*, *Geschlossen*) auf der Seite [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}), über die API oder mit dem Funktionscode am Telefon,
- Ihr Passwort und Ihre Sprache, Administratoren und API-Tokens,
- die Optionen unter *Erweitert → Weboberflächenoptionen*,
- das Installieren, Neuerzeugen oder Anfordern eines Zertifikats unter *Erweitert → Zertifikat*,
- das Wiederherstellen eines Backups (es wird dabei gleich übernommen), Firmware-Updates, Neustart und Werkseinstellungen.

> Eine geänderte IP-Adresse unter *System → Netzwerk* unterbricht beim Übernehmen Ihre Verbindung. Öffnen Sie danach die neue Adresse.

## Das Konsolenmenü {#console}

Auf dem lokalen Bildschirm (`tty1`) und auf der seriellen Konsole zeigt PhonixPBX die Meldung mit ihrer Adresse und darunter ein Menü. In einem LXC-/Incus-Container läuft es auf der Container-Konsole; im OCI-Container starten Sie es mit `docker exec -it phonix phonix tui`. Wer Zugang zur Konsole hat, hat physischen Zugang zum Gerät; das Menü fragt deshalb kein Passwort ab. Geben Sie die Nummer eines Eintrags ein und drücken Sie die Eingabetaste:

| Nr. | Eintrag | Funktion |
|---|---|---|
| 1 | Show status | Zeigt die Meldung erneut an: Version, LAN-Adresse, Webadresse und, bis es geändert wurde, das initiale Passwort. |
| 2 | Set LAN IP address | DHCP wählen oder eine statische Adresse, Präfixlänge, Gateway und DNS-Server eingeben. Die Änderung wird sofort übernommen. In Containern nicht verfügbar, dort verwaltet der Host das Netzwerk. |
| 3 | Reset administrator password | Setzt ein neues Passwort (mindestens 8 Zeichen) für `admin` oder einen anderen Administrator; legt das Konto an, falls es nicht existiert. Der Weg, wenn Sie sich ausgesperrt haben. |
| 4 | View logs | Zeigt das Log von Asterisk, des Systems, der Webanwendung oder des Monitors und verfolgt es live, bis Sie Strg-C drücken. |
| 5 | Reboot | Startet die Anlage nach einer Rückfrage neu. |
| 6 | Shut down | Schaltet die Anlage nach einer Rückfrage aus. |
| 7 | Reset to factory defaults | Löscht nach einer Rückfrage **die gesamte Konfiguration und alle Daten** und startet neu, siehe [Werkseinstellungen]({{< relref "/system/defaults.md" >}}). |

Das Konsolenmenü ist immer englisch.

## Die nächsten Schritte {#next-steps}

Eine typische Einrichtung läuft in dieser Reihenfolge:

1. **[System → Grundeinstellungen]({{< relref "/system/general.md" >}})**: Hostname und Domain, Zeitzone, Töne und die Sprache der Ansagen. Prüfen Sie [System → Netzwerk]({{< relref "/system/network.md" >}}), wenn die Anlage eine feste Adresse braucht oder hinter einem NAT-Router steht.
2. **[Konten → Provider]({{< relref "/accounts/providers.md" >}})**: Ihr SIP-Provider-Konto anlegen, mit [Wählmustern]({{< relref "/accounts/providers.md#dial-patterns" >}}) für ausgehende Anrufe.
3. **[Konten → Telefone]({{< relref "/accounts/phones.md" >}})**: Für jedes Tischtelefon und Softphone ein Telefon anlegen und die Zugangsdaten im Gerät eintragen.
4. **Eingehende Anrufe**: Beim Provider festlegen, welches Telefon, welche Rufgruppe oder welches IVR-Menü eingehende Anrufe erhält, siehe [Eingehende Anrufe]({{< relref "/accounts/providers.md#incoming-routes" >}}).
5. Im gelben Hinweis auf **Änderungen übernehmen** klicken.
6. **Testen**: Unter [Status → Gespräche & Registrierungen]({{< relref "/status/calls.md" >}}) prüfen, ob die Telefone und der Provider registriert sind, zwischen zwei Telefonen telefonieren, nach außen wählen, vom Handy aus anrufen. Die [Testnummern]({{< relref "/phone-users/_index.md#tests" >}}) helfen dabei, zum Beispiel `00003246` für einen Echotest.

Danach richten Sie ein, was Sie brauchen: [E-Mail-Benachrichtigungen]({{< relref "/services/email.md" >}}) für die Mailbox, [Rufgruppen]({{< relref "/dialplan/callgroups.md" >}}), [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}), [IVR-Menüs]({{< relref "/dialplan/ivr.md" >}}) und ein erstes [Backup]({{< relref "/system/backup.md" >}}).
