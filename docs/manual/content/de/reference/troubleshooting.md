---
title: "Fehlersuche"
weight: 40
description: "Lösungen für die häufigsten Probleme: Registrierung, Sprachübertragung, E-Mail, vergessene Passwörter, Sperren und Zertifikatswarnungen."
---
Diese Seite listet die häufigsten Probleme und ihre Lösungen. Die meisten lassen sich mit zwei Seiten der Weboberfläche eingrenzen; beginnen Sie dort.

## Wo Sie nachsehen {#where-to-look}

- **[Status → Gespräche & Registrierungen]({{< relref "/status/calls.md" >}})** zeigt, ob jedes Telefon und jeder Provider registriert ist, von welcher Adresse und mit welchem Gerät, und welche Gespräche laufen. Die Seite aktualisiert sich alle 5 Sekunden; lassen Sie sie beim Testen offen.
- **[Status → Logs]({{< relref "/status/logs.md" >}})**, Log *Asterisk*, zeigt, warum eine Registrierung oder ein Anruf fehlschlug. Stellen Sie das Problem bei geöffnetem Log nach und achten Sie auf Zeilen mit `WARNING` und `ERROR`.
- Das Log *Monitor* zeigt Adressen, die die Anlage gesperrt hat; das Log *System* zeigt Probleme beim E-Mail-Versand und im Netzwerk.
- **Ausstehende Änderungen:** Ist der gelbe Hinweis noch zu sehen, ist die Änderung, die Sie testen, noch nicht aktiv. Klicken Sie zuerst auf *Änderungen übernehmen*.

## Ein Telefon registriert sich nicht {#phone-registration}

Das Telefon meldet „nicht registriert“ o. Ä., und *Status → Gespräche & Registrierungen* zeigt keinen *Kontakt* dafür.

1. **Zugangsdaten:** Der Benutzername im Telefon muss die **Nummer** sein, das Passwort das aus [Konten → Telefone]({{< relref "/accounts/phones.md#edit" >}}) und der Server (Registrar) die Adresse der Anlage. Ein Tippfehler erzeugt Zeilen mit `Failed to authenticate` im Asterisk-Log.
2. **Übernommen?** Ein neu angelegtes Telefon kennt Asterisk erst nach *Änderungen übernehmen*.
3. **Aktiviert?** Deaktivierte Telefone erscheinen als *deaktiviert* und können sich nicht registrieren.
4. **Mehrere Geräte:** Registrieren sich mehr Geräte auf dieselbe Nummer, als *Max. registrierte Geräte* erlaubt, ersetzt jede neue Registrierung die älteste – die Geräte fallen dann abwechselnd heraus. Erhöhen Sie den Wert auf der Seite des Telefons.
5. **Firewall:** Ist unter [Erweitert → Firewall]({{< relref "/advanced/firewall.md" >}}) *Netzwerke, die SIP/IAX nutzen dürfen* gesetzt, muss das Netzwerk des Telefons in der Liste stehen.
6. **Gesperrte Adresse:** Nach wiederholt falschen Passwörtern sperrt die Anlage die Adresse des Geräts eine Zeit lang; das Log *Monitor* zeigt das. Siehe [Durch die Firewall ausgesperrt](#locked-out).
7. **Transport und Port:** Das Telefon muss denselben Transport (UDP, TCP oder TLS) und Port verwenden wie unter [Erweitert → SIP]({{< relref "/advanced/sip.md" >}}) eingestellt; Standard ist UDP-Port 5060.

Zur Kontrolle des Telefons selbst wählen Sie nach erfolgreicher Registrierung `000063`: Die Anlage sagt die Nummer an, unter der das Telefon angemeldet ist.

## Einseitige oder keine Sprachübertragung {#one-way-audio}

Das Gespräch wird verbunden, aber eine Seite hört nichts, oder beide. Das ist fast immer ein NAT- oder Firewall-Problem: Die Signalisierung (SIP) kommt durch, die Sprachdaten (RTP) nicht.

- **Anlage hinter einem NAT-Router** (Provider oder entfernte Telefone im Internet): Stellen Sie unter [System → Netzwerk → NAT / öffentliche Adresse]({{< relref "/system/network.md#nat" >}}) *NAT, statische öffentliche IP* oder *NAT, dynamische IP (Hostname)* mit Ihrer öffentlichen Adresse bzw. Ihrem DynDNS-Namen ein. Leiten Sie am Router den SIP-Port (5060/udp) und den RTP-Portbereich (Standard 10000–20000/udp, unter [Erweitert → RTP]({{< relref "/advanced/rtp.md" >}})) an die Anlage weiter.
- **Telefone außerhalb des LANs** (Homeoffice, Softphone auf dem Handy): Aktivieren Sie beim Telefon *Telefon ist hinter NAT (symmetrisches RTP, Contact umschreiben)*.
- **Provider über NAT:** Aktivieren Sie beim Provider *Provider wird über NAT erreicht (symmetrisches RTP)*.
- **SIP-ALG:** Viele Router haben ein „SIP-ALG“ bzw. einen „SIP-Helper“, der SIP-Pakete umschreibt und dabei oft die Sprachübertragung stört. Schalten Sie ihn am Router ab.
- **Container mit veröffentlichten Ports:** Der veröffentlichte UDP-Bereich muss genau dem in PhonixPBX eingestellten RTP-Bereich entsprechen.

Testen Sie mit der Echonummer `00003246`: Hören Sie sich an einem internen Telefon selbst, ist der Weg zwischen Telefon und Anlage in Ordnung, und das Problem liegt auf der Seite des Providers.

## Der Provider registriert sich nicht {#provider-registration}

*Status → Gespräche & Registrierungen* zeigt den Provider in Rot.

- *Abgelehnt*: Der Provider hat die Zugangsdaten abgewiesen. Prüfen Sie *Benutzername* und *Passwort*; manche Provider verlangen zusätzlich einen *Authentifizierungsbenutzer* oder einen *From-Benutzer* – siehe die Angaben Ihres Providers und [Konten → Provider]({{< relref "/accounts/providers.md#edit" >}}).
- *Nicht registriert* oder *Nicht erreichbar*: Die Anlage erreicht den Provider nicht. Prüfen Sie den Hostnamen des Providers, die DNS-Server unter [System → Netzwerk]({{< relref "/system/network.md" >}}) und ob die Anlage ins Internet kommt.
- *nicht geladen*: Der Provider wurde angelegt oder geändert, aber noch nicht übernommen.
- Ist unter *Erweitert → Firewall* *Netzwerke, die SIP/IAX nutzen dürfen* gesetzt, müssen die Adressen des Providers in der Liste stehen.
- Das Asterisk-Log zeigt die Antwort des Providers, zum Beispiel `403 Forbidden` (falsche Zugangsdaten) oder eine Zeitüberschreitung (nicht erreichbar).

Eingehende Anrufe brauchen außerdem eine [eingehende Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) für die gewählte Nummer, ausgehende ein passendes [Wählmuster]({{< relref "/accounts/providers.md#dial-patterns" >}}).

## Es kommen keine E-Mails an {#email}

Mailbox-E-Mails und Benachrichtigungen über verpasste Anrufe brauchen drei Dinge:

1. Einen funktionierenden Mailserver unter [Dienste → Benachrichtigungen]({{< relref "/services/email.md" >}}). Nutzen Sie dort *Testnachricht senden*. Der Test verwendet die übernommene Konfiguration; übernehmen Sie ausstehende Änderungen also zuerst. Die Fehlermeldung nennt meist das Problem: falsches Passwort, falscher Port oder falsche Verschlüsselung, ein Zertifikat, dem die Anlage nicht vertraut (*Serverzertifikat überprüfen*).
2. Beim Telefon: eine E-Mail-Adresse und *Mailbox-Nachrichten per E-Mail senden* bzw. *E-Mail-Benachrichtigung bei verpassten Anrufen*.
3. Übernommene Änderungen.

Zustellversuche und Fehler stehen im Log *System* (`msmtp`). Viele Internetanbieter sperren ausgehend Port 25; verwenden Sie stattdessen Port 587 (STARTTLS) oder 465 (TLS) Ihres Mailanbieters. Schauen Sie auch im Spam-Ordner nach.

## Administratorpasswort vergessen {#forgot-password}

Wählen Sie auf der Konsole der Anlage (Bildschirm und Tastatur oder serielle Konsole) im [Konsolenmenü]({{< relref "/getting-started/_index.md#console" >}}) *Reset administrator password* und geben Sie ein neues Passwort ein.

- **LXC/Incus/Proxmox:** Öffnen Sie die Container-Konsole (`pct console <id>`, `incus console pbx`) – dort läuft das Menü.
- **OCI-Container:** `docker exec -it phonix phonix user passwd admin`.
- Kann sich noch ein anderer Administrator anmelden, kann er unter [Erweitert → Administratoren]({{< relref "/advanced/users.md" >}}) ein neues Passwort setzen.

Nach fünf fehlgeschlagenen Anmeldungen innerhalb von fünf Minuten weist die Anmeldeseite weitere Versuche für einige Minuten ab; warten Sie und versuchen Sie es dann erneut.

## Durch die Firewall ausgesperrt {#locked-out}

**Gesperrt nach fehlgeschlagenen Anmeldungen.** Der Sicherheitsmonitor sperrt eine Adresse für die *Sperrdauer* (Standard eine Stunde), wenn sie sich wiederholt nicht an SIP, IAX oder dem Asterisk Manager anmelden konnte – etwa ein Telefon mit falschem Passwort. Eine gesperrte Adresse erreicht die Anlage überhaupt nicht mehr, auch nicht die Weboberfläche. Das Log *Monitor* listet die Sperren. So heben Sie eine Sperre auf:

- warten, bis die Sperrdauer abgelaufen ist, oder
- von einer anderen Adresse aus eine Änderung unter [Erweitert → Firewall]({{< relref "/advanced/firewall.md" >}}) übernehmen (das Neuladen der Firewall hebt alle Sperren auf), oder
- die Anlage neu starten; Sperren überdauern keinen Neustart.

Beheben Sie danach die Ursache am Gerät. Adressen aus *Netzwerke, die die TK-Anlage verwalten dürfen* und, bei fester Adresse der Anlage, ihr eigenes LAN-Subnetz werden nie gesperrt.

**Das eigene Netzwerk ist nicht erlaubt.** Fehlt das Netzwerk Ihres Computers in *Netzwerke, die die TK-Anlage verwalten dürfen*, sind Weboberfläche und SSH von dort nicht erreichbar. Verbinden Sie sich aus einem erlaubten Netzwerk und korrigieren Sie die Liste. Geht das nicht, öffnen Sie eine Root-Shell auf der Anlage (im Container: `pct enter <id>`, `incus exec pbx -- sh` oder `docker exec -it phonix sh`; auf dem Gerät: mit der Kernel-Option `phonix.console=shell` starten, siehe `docs/INSTALL.md`) und führen Sie `nft delete table inet phonix` aus. Das schaltet die Firewall bis zum nächsten Übernehmen oder Neustart ab: Melden Sie sich an, korrigieren Sie die Liste und übernehmen Sie die Änderung.

## Zertifikatswarnungen im Browser {#certificate-warning}

- **Selbstsigniertes Zertifikat:** Nach der Installation verwendet die Anlage ein Zertifikat, das sie selbst signiert hat. Browser warnen davor; das ist zu erwarten. Ein vertrauenswürdiges Zertifikat erhalten Sie unter [Erweitert → Zertifikat]({{< relref "/advanced/certificate.md" >}}) – automatisch von Let's Encrypt oder einer anderen ACME-CA, oder Sie laden Ihr eigenes hoch.
- **Falscher Name:** Ein Zertifikat gilt nur für die darin enthaltenen Namen (*Namen* auf der Zertifikatsseite). Rufen Sie die Anlage unter einem dieser Namen auf. Nach einer Änderung des Hostnamens verwenden Sie *Neues selbstsigniertes Zertifikat erstellen* oder fordern ein neues automatisches Zertifikat an.
- **Let's Encrypt schlägt fehl:** Bei der Validierung über *HTTP (Port 80)* müssen die Namen im öffentlichen DNS auf die Anlage zeigen, und Port 80 muss aus dem Internet erreichbar sein. Für eine nur intern erreichbare Anlage verwenden Sie die Validierung über die *DNS-Provider-API*.
- **Abgelaufen:** Automatische Zertifikate werden täglich erneuert, sobald sie in weniger als 30 Tagen ablaufen. Schlägt das fehl, zeigt die Zertifikatsseite den Fehler des letzten Versuchs.

## Asterisk ist nicht erreichbar {#asterisk-down}

Zeigen die Statusseiten *Asterisk ist nicht erreichbar*, finden Sie den Grund am Ende des Asterisk-Logs. Übernehmen Sie die Konfiguration erneut (`phonix apply --force` auf der Kommandozeile schreibt alles neu und lädt alles neu) oder starten Sie die Anlage unter [System → Neustart]({{< relref "/system/reboot.md" >}}) neu. Trat das Problem nach einem Update auf, siehe [System → Firmware]({{< relref "/system/firmware.md" >}}).
