---
title: "Telefone"
weight: 10
description: "SIP-, IAX- und externe Telefone: Nummern, Passwörter, Mailbox, Regeln für ausgehende Anrufe und die Einrichtung eines Geräts."
---
Ein Telefon ist eine interne Nummer, die ein Gerät klingeln lässt. Jedes Tischtelefon, Softphone und jede Smartphone-App, die sich an der Telefonanlage registriert, braucht ein eigenes Telefonkonto. Ein *externes* Telefon lässt eine interne Nummer ein Mobiltelefon oder ein anderes System klingeln. Telefone verwalten Sie unter *Konten → Telefone*.

Änderungen an Telefonen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Telefontypen {#types}

| Typ | Verwendung |
|---|---|
| SIP-Telefon | Tischtelefone, Softphones und Apps, die SIP sprechen. Das ist der Normalfall. |
| IAX-Telefon | Geräte oder andere Asterisk-Systeme, die IAX2 sprechen (Port 4569 UDP). |
| Externes Telefon | Eine interne Nummer, die an eine Nummer außerhalb der Anlage weiterleitet: eine Mobilnummer, die über einen Provider gewählt wird, oder eine SIP- bzw. IAX-Adresse (`user@host`). Es hat kein Passwort und registriert sich nicht. |

Den Typ wählen Sie mit den Schaltflächen **SIP-Telefon**, **IAX-Telefon** und **Externes Telefon** über der Liste; er lässt sich später nicht ändern. Um ihn zu ändern, legen Sie ein neues Telefon an und löschen das alte.

## Telefonliste {#list}

Die Liste zeigt alle Telefone, sortiert nach Nummer:

| Spalte | Bedeutung |
|---|---|
| Nummer | Die interne Nummer. Ein Klick darauf öffnet das Telefon zum Bearbeiten. |
| Name | Der Name der Anruferkennung. |
| Typ | SIP, IAX oder Extern. |
| Status | Bei SIP-Telefonen *registriert* (mit der Adresse des Geräts) oder *nicht registriert*, bei IAX-Telefonen der Peer-Status, bei externen Telefonen die Nummer oder Adresse, an die weitergeleitet wird. Die Spalte wird alle 15 Sekunden aktualisiert. *Asterisk nicht aktiv* bedeutet, dass der Telefoniedienst nicht läuft. |
| Mailbox | Ein Briefsymbol, wenn das Telefon eine Mailbox hat. |
| Beschreibung | Ihre Notiz. |

Mit den Schaltflächen am Ende jeder Zeile bearbeiten, deaktivieren/aktivieren und löschen Sie das Telefon. Ein deaktiviertes Telefon behält seine Einstellungen, wird aber nicht in die Konfiguration übernommen: Es kann sich nicht registrieren und ist nicht erreichbar. Beim Löschen eines Telefons werden auch die eingehenden Routen und IVR-Tasten entfernt, die auf das Telefon oder seine Mailbox zeigten; feste Ziele von IVR-Menüs und Geschäftszeiten, die darauf zeigten, fallen auf *Auflegen* zurück.

Die aktuell registrierten Geräte und laufenden Gespräche sehen Sie auch unter [*Status → Gespräche & Registrierungen*]({{< relref "/status/calls.md" >}}).

## Telefon anlegen oder bearbeiten {#edit}

Das Formular hat bis zu vier Reiter. Externe Telefone haben nur die ersten beiden.

### Allgemein {#general}

| Feld | Bedeutung | Standard |
|---|---|---|
| Nummer | Die interne Nummer (1–20 Ziffern), unter der das Telefon erreichbar ist. Bei SIP- und IAX-Telefonen ist sie auch der Benutzername, mit dem sich das Gerät registriert. Sie darf nicht von einem anderen Telefon, einer Rufgruppe, einem Konferenzraum, einer Anwendung, einem IVR-Menü, dem Funktionscode von Geschäftszeiten oder dem Parkbereich belegt sein. | nächste freie Nummer ab 101 |
| Anruferkennung (Name) | Der Name, den die Angerufenen sehen, zum Beispiel `Anna Meier`. Er darf `" < > ; \` nicht enthalten. | – |
| Passwort | Nur SIP/IAX. Das Passwort, mit dem sich das Gerät registriert, 4–128 Zeichen ohne Leerzeichen, Anführungszeichen, `;` oder `\`. Für neue Telefone wird ein starkes Zufallspasswort vorgeschlagen; **Generieren** erzeugt ein neues, die Augen-Schaltfläche zeigt es an. Beim Bearbeiten lassen Sie das Feld leer, um das gespeicherte Passwort zu behalten. | generiert, 16 Zeichen |
| Dieses Telefon erreichen über | Nur extern: *einen Provider* (die Nummer wird über einen Provider gewählt), *SIP-URI (user@host)* oder *IAX-URI (user@host)*. | einen Provider |
| Nummer / URI | Nur extern: die zu wählende Rufnummer (Ziffern, optional mit führendem `+`, `*` und `#`) oder die Adresse `user@host`. | – |
| Provider | Nur extern mit *einen Provider*: der Provider, über den die Nummer gewählt wird. Wird dieser Provider gelöscht, wird das externe Telefon deaktiviert. | – |
| Sprache | Sprache der Ansagen, die dieses Telefon hört (Mailbox, Ansagen, vorgelesene Nummern). | Englisch |
| Klingeldauer (Sekunden) | Wie lange das Telefon klingelt, bevor der Anruf zur Mailbox geht (5–600). Leer bedeutet: Es klingelt, bis der Anrufer auflegt. | leer |
| Beschreibung | Nur eine Notiz für Sie. | – |
| Von außen erreichbar (öffentliche Direktwahl) | Anrufer über Provider oder SIP-Adressen dürfen dieses Telefon direkt unter seiner Nummer anrufen. | aus |
| Öffentlicher Name | Erscheint, wenn das Telefon von außen erreichbar ist: ein Alias für den öffentlichen Kontext, zum Beispiel `vertrieb` für `sip:vertrieb@pbx`. Buchstaben, Ziffern und `. _ + -`. Leer verwendet die Nummer. | leer |

### Mailbox & Benachrichtigungen {#voicemail}

| Feld | Bedeutung | Standard |
|---|---|---|
| Mailbox aktivieren | Gibt dem Telefon eine Mailbox. Anrufe, die nicht innerhalb der Klingeldauer angenommen werden oder auf ein besetztes Telefon treffen, gehen zur Mailbox. Benutzer hören ihre Nachrichten unter `000086` ab. | aus |
| Mailbox-PIN | Die Ziffern, mit denen der Benutzer die Mailbox öffnet. Für neue Telefone wird eine zufällige 4-stellige PIN vorgeschlagen. | generiert |
| Mailbox-Nachrichten per E-Mail senden | Neue Nachrichten werden an diese Adresse gesendet (mit der Aufnahme als Anhang, je nach den Einstellungen unter [*Dienste → Mailbox*]({{< relref "/services/voicemail.md" >}})). Setzt funktionierenden E-Mail-Versand voraus, siehe [*Dienste → Benachrichtigungen*]({{< relref "/services/email.md" >}}). | leer |
| E-Mail-Benachrichtigung bei verpassten Anrufen | Sendet für jeden Anruf, den dieses Telefon nicht angenommen hat, eine E-Mail. | aus |
| Benachrichtigungsadresse | Empfänger der E-Mails zu verpassten Anrufen. Pflichtfeld, wenn die Option darüber eingeschaltet ist. | – |
| E-Mail-Sprache | Sprache der Mailbox-E-Mails und der E-Mails zu verpassten Anrufen. Die Texte lassen sich unter [*Dienste → Mailbox*]({{< relref "/services/voicemail.md" >}}) ändern. | Wie Sprache des Telefons |

### Ausgehende Anrufe {#outgoing}

Nur SIP- und IAX-Telefone. Dieser Reiter listet die eingerichteten Provider auf.

| Feld | Bedeutung | Standard |
|---|---|---|
| Provider sperren | Das Telefon kann über die gewählten Provider keine ausgehenden Anrufe führen, zum Beispiel damit ein Telefon im Eingangsbereich nur intern telefoniert. | keine |
| Ausgehende Anruferkennung pro Provider | Ein Feld pro Provider. Eine Anruferkennung wie `Vertrieb <4930123456>` (oder nur eine Nummer), die gesendet wird, wenn dieses Telefon über diesen Provider anruft. Sie hat Vorrang vor der Einstellung *Ausgehende Anruferkennung* des Providers. Leer verwendet die Einstellung des Providers. | leer |

Welche Nummern über welchen Provider gehen, bestimmen die [Wählmuster]({{< relref "/accounts/providers.md#dial-patterns" >}}) des Providers.

### Codecs & Erweitert {#advanced}

Nur SIP- und IAX-Telefone. Die Standardwerte passen für die meisten Geräte.

| Feld | Bedeutung | Standard |
|---|---|---|
| Codecs | Die Audio- und Video-Codecs, die dem Gerät angeboten werden, in der Reihenfolge der Bevorzugung (zum Umsortieren ziehen). Audio: ulaw, alaw, g722, opus, gsm, g726, g729, ilbc, speex, slin. Video: h264, vp8, vp9, h263. Mindestens einer ist nötig. | g722, alaw, ulaw, opus |
| DTMF-Modus | Nur SIP. Wie Tastendrücke übertragen werden: *RFC 4733 (RFC 2833)*, *In-Band*, *SIP INFO* oder *Auto*. Ändern Sie ihn nur, wenn Tastendrücke in Menüs oder in der Mailbox nicht erkannt werden. | RFC 4733 |
| Qualify-Intervall (s) | Wie oft die Anlage prüft, ob das Gerät erreichbar ist (0–3600). 0 schaltet die Prüfung ab. Bei IAX-Telefonen schaltet jeder Wert außer 0 die Prüfung nur ein. | 60 |
| Max. registrierte Geräte | Nur SIP. Wie viele Geräte sich gleichzeitig mit diesem Konto registrieren dürfen (1–10), zum Beispiel ein Tischtelefon und ein Softphone. Ist die Grenze erreicht, ersetzt eine neue Registrierung die älteste. | 1 |
| Besetzt-Schwelle | Nur SIP. Ab so vielen gleichzeitigen Gesprächen gilt das Telefon als besetzt (1–100); weitere Anrufer werden wie bei Besetzt behandelt (Mailbox, falls aktiviert). Leer bedeutet keine Grenze. | leer |
| Telefon ist hinter NAT (symmetrisches RTP, Contact umschreiben) | Nur SIP. Sendet Audio und Signalisierung an die Adresse zurück, von der die Pakete kamen. Lassen Sie die Option eingeschaltet, außer das Telefon ist im selben Netz und Sie wissen, dass sie nicht nötig ist. | an |
| Zusätzliche PJSIP-Endpoint-Optionen / Zusätzliche IAX-Peer-Optionen | Für Fortgeschrittene: ein `key=value` pro Zeile, an den erzeugten Endpoint- bzw. Peer-Abschnitt angehängt. Zeilen, die mit `;` beginnen, werden ignoriert. | leer |

### SIP-Telefon hinzufügen {#add-sip-phone}

1. Öffnen Sie *Konten → Telefone* und klicken Sie auf **SIP-Telefon**.
2. Übernehmen Sie die vorgeschlagene **Nummer** oder geben Sie eine eigene ein, und tragen Sie die **Anruferkennung (Name)** ein.
3. Kopieren Sie das generierte **Passwort** (Augen-Schaltfläche), bevor Sie speichern.
4. Schalten Sie bei Bedarf auf dem Reiter *Mailbox & Benachrichtigungen* **Mailbox aktivieren** ein.
5. Klicken Sie auf **Telefon anlegen** und übernehmen Sie danach die Änderungen.
6. Richten Sie das Gerät wie unten beschrieben ein.

## SIP-Telefon oder Softphone einrichten {#configure-device}

Tragen Sie diese Werte in den Kontoeinstellungen des Telefons oder Softphones ein:

| Einstellung am Gerät | Wert |
|---|---|
| Server, Registrar, Domain oder Proxy | Die IP-Adresse (oder der Hostname) der Telefonanlage. |
| Benutzername, Benutzer-ID, Authentifizierungsbenutzer | Die **Nummer** des Telefons, zum Beispiel `101`. |
| Passwort | Das **Passwort** des Telefons. |
| Anzeigename | Beliebig; die Anlage verwendet die **Anruferkennung (Name)**. |
| Transport und Port | UDP auf Port 5060. TCP (ebenfalls Port 5060) und TLS (Port 5061) funktionieren, wenn sie unter [*Erweitert → SIP*]({{< relref "/advanced/sip.md" >}}) eingeschaltet sind. |
| Mailbox-Nummer | `000086` |

Sobald sich das Gerät registriert hat, wechselt sein Status in der Liste auf *registriert*. Wählen Sie `00003246` (den Echotest), um den Ton in beide Richtungen zu prüfen.

> Registriert sich das Telefon nicht, prüfen Sie zuerst Benutzername und Passwort, dann die Firewall: Der SIP-Port kann unter [*Erweitert → Firewall*]({{< relref "/advanced/firewall.md" >}}) auf bestimmte Netze beschränkt sein, und wiederholt falsche Passwörter können dazu führen, dass die Adresse eines Geräts eine Zeit lang gesperrt wird.

IAX-Telefone richten Sie genauso ein: Server = Adresse der Anlage, Benutzername = Nummer, das Passwort, Port 4569 UDP.
