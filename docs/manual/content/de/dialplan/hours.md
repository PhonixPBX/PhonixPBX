---
title: "Geschäftszeiten"
weight: 40
description: "Anrufe während der Öffnungszeiten an ein Ziel und außerhalb an ein anderes leiten, mit Feiertagen und manueller Umschaltung."
---
Geschäftszeiten leiten Anrufe an ein Ziel, solange Sie geöffnet haben, und an ein anderes, wenn geschlossen ist, zum Beispiel tagsüber an den Empfang und nachts an ein IVR-Menü oder eine Mailbox. Sie folgen einem Wochenplan und einer Liste von Feiertagen und lassen sich von Hand auf geöffnet oder geschlossen umschalten. Geschäftszeiten verwalten Sie unter *Wählplan → Geschäftszeiten*.

Geschäftszeiten haben keine eigene interne Nummer. Verwenden Sie sie als Ziel einer [eingehenden Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) eines Providers oder einer [IVR-Taste]({{< relref "/dialplan/ivr.md#keys" >}}). Änderungen an Zeitplan und Zielen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}); der [Modus](#mode) schaltet sofort um.

## Geschäftszeitenliste {#list}

Klicken Sie über der Liste auf **Geschäftszeiten**, um einen Zeitplan hinzuzufügen. Die Liste zeigt:

| Spalte | Bedeutung |
|---|---|
| Name | Name und Beschreibung. Ein Klick darauf öffnet den Zeitplan zum Bearbeiten. |
| Jetzt | *jetzt geöffnet* oder *jetzt geschlossen*, mit *manuell umgeschaltet*, wenn der Modus erzwungen ist, oder dem Namen des heutigen Feiertags. |
| Wenn geöffnet | Das Ziel während der Öffnungszeiten. |
| Wenn geschlossen | Das Ziel außerhalb der Öffnungszeiten. |
| Funktionscode | Der Code, mit dem sich der Modus am Telefon umschalten lässt, oder `–`. |

Mit den Schaltflächen am Ende jeder Zeile bearbeiten und löschen Sie den Zeitplan. Beim Löschen werden die eingehenden Routen und IVR-Tasten entfernt, die zu ihm führten.

## Geschäftszeiten anlegen oder bearbeiten {#edit}

### Wöchentliche Öffnungszeiten {#weekly}

Jeder Wochentag hat eigene Zeitbereiche. Mit **Zeitbereich hinzufügen** fügen Sie einen hinzu; ein Tag kann mehrere Bereiche haben, zum Beispiel `08:00`–`12:00` und `13:00`–`17:00` für eine Mittagspause. Ein Tag ohne Bereiche ist *Ganztägig geschlossen*. Die Schaltfläche **x** entfernt einen Bereich.

- Die Zeiten gelten in der Zeitzone des Systems, siehe [*System → Grundeinstellungen*]({{< relref "/system/general.md#time" >}}).
- Das Ende ist die erste Minute, in der geschlossen ist: `08:00`–`17:00` ist bis 16:59 geöffnet.
- Ein Ende von `23:59` bedeutet bis Mitternacht.
- Das Ende muss nach dem Beginn liegen. Einen Bereich über Mitternacht tragen Sie als zwei Bereiche an zwei Tagen ein.

Neue Geschäftszeiten beginnen mit Montag bis Freitag, 08:00–12:00 und 13:00–17:00. Die **Wochenübersicht** zeigt die Öffnungszeiten als grüne Balken; bei einem gespeicherten Zeitplan markiert eine Linie die aktuelle Uhrzeit.

### Feiertage und Schließtage {#holidays}

An den hier eingetragenen Tagen ist ganztägig geschlossen, unabhängig vom Wochenplan. Klicken Sie auf **Tag hinzufügen** und geben Sie das **Datum** und optional einen **Namen** ein, zum Beispiel `1. Weihnachtstag`. Mit **jedes Jahr** wiederholt sich der Tag jedes Jahr am selben Datum. Bewegliche Feiertage wie Ostern tragen Sie für jedes Jahr einzeln ein. Es können bis zu 200 Tage eingetragen werden.

### Weiterleitung {#routing}

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Ein Name für Listen und Zielauswahl. | – |
| Beschreibung | Eine Notiz für Sie. | leer |
| Wenn geöffnet | Wohin Anrufe während der Öffnungszeiten gehen. | Auflegen |
| Wenn geschlossen | Wohin Anrufe außerhalb der Öffnungszeiten und an Feiertagen gehen. | Auflegen |
| Funktionscode | Optionaler Code, zum Beispiel `*31`, der an einem internen Telefon gewählt zwischen *Automatisch* und *Geschlossen* umschaltet. Ziffern, `*` und `#`; er darf nicht anderweitig als Nummer vergeben sein und nicht mit dem Code für die Gesprächsübernahme beginnen (standardmäßig `*8`). | leer |

Beide Ziele können ein Telefon, eine Rufgruppe, ein Konferenzraum, eine Anwendung, ein IVR-Menü, eine Mailbox oder *Auflegen* sein, aber keine anderen Geschäftszeiten. Siehe [Ziele]({{< relref "/dialplan/ivr.md#destinations" >}}).

## Zwischen geöffnet und geschlossen umschalten {#mode}

Bei einem gespeicherten Zeitplan zeigt der Kasten oben, ob **Aktuell** geöffnet ist, und Sie können den **Modus** wählen:

| Modus | Verhalten |
|---|---|
| Automatisch | Folgt den wöchentlichen Öffnungszeiten und Feiertagen. |
| Geöffnet | Geöffnet, bis zurückgeschaltet wird, zum Beispiel für eine Sonderveranstaltung. |
| Geschlossen | Geschlossen, bis zurückgeschaltet wird, zum Beispiel wenn das Büro früher schließt. |

Mit **Jetzt umschalten** ändern Sie ihn. Der Modus **gilt sofort, ohne dass die Konfiguration übernommen werden muss**, und bleibt auch nach einem Neustart erhalten. Asterisk muss laufen; andernfalls ist der Modus unbekannt und lässt sich nicht ändern.

Telefonbenutzer können den Modus mit dem **Funktionscode** umschalten: Einmal gewählt, schaltet er auf *Geschlossen* (Ansage „aktiviert“), erneut gewählt zurück auf *Automatisch* („deaktiviert“). War der Modus *Geöffnet*, schaltet der Code auf *Automatisch*. Siehe auch [Telefonieren mit PhonixPBX]({{< relref "/phone-users/_index.md#business-hours" >}}).

> Der Modus ist ein Laufzeitzustand und nicht Teil eines Backups. Ein erzwungener Modus kann beim Wiederherstellen eines Backups verloren gehen; prüfen Sie den Modus danach.

### Anrufe außerhalb der Bürozeiten umleiten {#example}

1. Legen Sie ein IVR-Menü an oder wählen Sie ein Telefon mit Mailbox für die Zeit, in der geschlossen ist.
2. Fügen Sie Geschäftszeiten hinzu, legen Sie die Wochenzeiten und Feiertage fest und wählen Sie **Wenn geöffnet** (zum Beispiel die Rufgruppe des Empfangs) und **Wenn geschlossen** (das Menü für außerhalb der Bürozeiten).
3. Klicken Sie auf **Erstellen** und übernehmen Sie die Änderungen.
4. Setzen Sie die Geschäftszeiten als Ziel der [eingehenden Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) Ihrer Nummer.
