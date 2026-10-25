---
title: "Manager (AMI)"
weight: 40
description: "Benutzer für das Asterisk Manager Interface mit erlaubten Netzwerken und Rechten."
---
Unter *Erweitert → Manager (AMI)* verwalten Sie die Benutzer des Asterisk Manager Interface. AMI ist eine TCP-Schnittstelle auf Port 5038, über die externe Software die TK-Anlage überwachen und steuern kann, zum Beispiel CTI-Programme, Vermittlungsplätze, Wallboards oder Lösungen zur Gesprächsaufzeichnung. PhonixPBX verwendet AMI auch intern; Benutzer müssen Sie hier nur für externe Software anlegen.

Für eigene Skripte ist die [REST-API]({{< relref "/reference/api.md" >}}) mit einem [API-Token]({{< relref "/advanced/tokens.md" >}}) meist die bessere Wahl: Sie hat feinere Zugriffsrechte und legt keine Asterisk-Interna offen.

Änderungen werden wirksam, wenn Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

> Ein AMI-Benutzer mit Schreibrechten kann die gesamte TK-Anlage steuern, auch Anrufe auslösen und Asterisk-Befehle ausführen. Legen Sie Benutzer nur für vertrauenswürdige Software an, vergeben Sie nur die nötigen Rechte und schränken Sie die erlaubten Netzwerke so weit wie möglich ein.

## Benutzerliste {#list}

Die Liste zeigt jeden Manager-Benutzer mit seinen **Erlaubten Netzwerken** und seinen Rechten zum **Lesen** und **Schreiben**. Ohne Benutzer wird AMI nur intern verwendet.

Das Suchfeld über der Liste findet Manager-Benutzer nach Benutzername; wie Suchen und Blättern funktionieren, steht unter [Listen]({{< relref "/getting-started/_index.md#lists" >}}).

Klicken Sie über der Liste auf **Manager-Benutzer**, um einen Benutzer anzulegen, auf den Benutzernamen, um ihn zu bearbeiten, und auf das Papierkorbsymbol, um ihn zu löschen.

## Benutzereinstellungen {#edit}

| Feld | Bedeutung | Standard |
|---|---|---|
| Benutzername | Anmeldename, bis zu 64 Buchstaben, Ziffern, `_` und `-`. Die Namen `phonix` und `general` sind reserviert. | — |
| Passwort | Passwort des Benutzers, 4–128 Zeichen ohne Leerzeichen, Anführungszeichen, `;` oder Backslashes. Lassen Sie es beim Bearbeiten leer, um das gespeicherte Passwort beizubehalten. | — |
| Erlaubte Netzwerke | Die Netzwerke, aus denen sich der Benutzer verbinden darf, ein CIDR pro Zeile, z. B. `192.168.1.0/24`. Mindestens eines ist erforderlich. | `127.0.0.1/32` |
| Leserechte | Ereignisklassen, die der Benutzer erhält. | `all` |
| Schreibrechte | Aktionsklassen, die der Benutzer ausführen darf. | keine |

Die Rechte sind die AMI-Klassen von Asterisk: `all`, `system`, `call`, `log`, `verbose`, `command`, `agent`, `user`, `config`, `dtmf`, `reporting`, `cdr`, `dialplan`, `originate`, `agi`, `cc`, `aoc`, `test`, `security` und `message`. Welche Klassen eine externe Software braucht, steht meist in ihrer Dokumentation. Typische Beispiele:

- Ein Wallboard oder Monitoring-Werkzeug: Lesen `call`, `agent`, `reporting`; keine Schreibrechte.
- Ein Click-to-Dial-Werkzeug: zusätzlich Schreiben `originate`.
- `system`, `command` und `config` erlauben es, Asterisk neu zu starten, CLI-Befehle auszuführen und Konfigurationsdateien zu lesen. Vergeben Sie sie nur, wenn es wirklich nötig ist.

## Netzwerkzugriff {#network}

Solange alle Benutzer nur Loopback-Netzwerke (`127.0.0.0/8`) haben, lauscht AMI nur auf der TK-Anlage selbst. Sobald ein Benutzer ein anderes erlaubtes Netzwerk hat, lauscht AMI auf allen Schnittstellen, und jeder Benutzer kann sich nur aus seinen eigenen erlaubten Netzwerken anmelden.

Bei aktivierter Firewall unter [Erweitert → Firewall]({{< relref "/advanced/firewall.md" >}}) wird Port 5038 nur für die IPv4-Netzwerke geöffnet, die bei den Manager-Benutzern unter *Erlaubte Netzwerke* eingetragen sind (Loopback-Netzwerke brauchen keine Regel). IPv6-Netzwerke werden nicht freigegeben, da AMI nur auf IPv4 lauscht. Die Firewall-Regeln ändern sich, sobald Sie übernehmen. AMI-Verkehr einschließlich des Passworts ist unverschlüsselt; verwenden Sie ihn nur in einem vertrauenswürdigen Netzwerk.
