---
title: "Geschäftszeiten"
weight: 40
description: "Anrufe während der Öffnungszeiten an ein Ziel und außerhalb an ein anderes leiten, mit Feiertagen, Sonderzeiträumen, einer Abwesenheitstaste und manueller Umschaltung."
---
Geschäftszeiten leiten Anrufe an ein Ziel, solange Sie geöffnet haben, und an ein anderes, wenn geschlossen ist, zum Beispiel tagsüber an den Empfang und nachts an ein IVR-Menü oder eine Mailbox. Sie folgen einem Wochenplan, einer Liste von Feiertagen und optionalen Sonderzeiträumen wie Betriebsferien oder einer Notfallumleitung und lassen sich von Hand oder mit einer Taste an den Telefonen auf geöffnet oder geschlossen umschalten. Geschäftszeiten verwalten Sie unter *Wählplan → Geschäftszeiten*.

Geschäftszeiten haben keine eigene interne Nummer. Verwenden Sie sie als Ziel einer [eingehenden Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) eines Providers oder einer [IVR-Taste]({{< relref "/dialplan/ivr.md#keys" >}}). Änderungen an Zeitplan und Zielen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}); der [Modus](#mode), die [Abwesenheitstaste](#key) und die Schalter der [Sonderzeiträume](#specials) wirken sofort.

## Geschäftszeitenliste {#list}

Klicken Sie über der Liste auf **Geschäftszeiten**, um einen Zeitplan hinzuzufügen. Die Liste zeigt:

| Spalte | Bedeutung |
|---|---|
| Name | Name und Beschreibung. Ein Klick darauf öffnet den Zeitplan zum Bearbeiten. |
| Jetzt | *jetzt geöffnet* oder *jetzt geschlossen* und warum: *manuell umgeschaltet* (dauerhafter Modus), *per Taste umgeschaltet bis zur nächsten Änderung* (Abwesenheitstaste), der Name des geltenden Sonderzeitraums (mit seinem letzten Tag, falls er Tage hat) oder des heutigen Feiertags. Darunter ein Schalter je Sonderzeitraum, siehe [Sonderzeiträume](#specials). |
| Wenn geöffnet | Das Ziel während der Öffnungszeiten. |
| Wenn geschlossen | Das Ziel außerhalb der Öffnungszeiten. |
| Funktionscode | Der Code der [Abwesenheitstaste](#key) oder `–`. |

Das Suchfeld über der Liste findet Geschäftszeiten nach Name, Beschreibung oder Funktionscode; wie Suchen und Blättern funktionieren, steht unter [Listen]({{< relref "/getting-started/_index.md#lists" >}}).

Mit den Schaltflächen am Ende jeder Zeile bearbeiten und löschen Sie den Zeitplan. Beim Löschen werden die eingehenden Routen und IVR-Tasten entfernt, die zu ihm führten.

## Geschäftszeiten anlegen oder bearbeiten {#edit}

Das Formular hat fünf Reiter: **Allgemein**, **Wochenzeiten**, **Feiertage**, **Sonderzeiträume** und **Jahresübersicht**. **Speichern** unten speichert alle Reiter zusammen und kehrt zur Liste zurück; **Speichern und weiter bearbeiten** (**Erstellen und weiter bearbeiten** bei neuen Geschäftszeiten) speichert ebenfalls, lässt die Seite aber offen, auf demselben Reiter und mit derselben Anzahl Monate in der Jahresübersicht. Ist eine Eingabe falsch, öffnet sich der Reiter mit dem Fehler und ist mit einem roten Zeichen markiert. Ein Link auf die Seite mit `#tab-specials` (oder einem anderen Reiternamen) öffnet diesen Reiter direkt.

### Allgemein {#routing}

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Ein Name für Listen und Zielauswahl. | – |
| Beschreibung | Eine Notiz für Sie. | leer |
| Wenn geöffnet | Wohin Anrufe während der Öffnungszeiten gehen. | Auflegen |
| Wenn geschlossen | Wohin Anrufe außerhalb der Öffnungszeiten und an Feiertagen gehen. | Auflegen |
| Funktionscode | Optionaler Code, zum Beispiel `*31`, der [Abwesenheitstaste](#key). Ziffern, `*` und `#`; er darf nicht anderweitig als Nummer vergeben sein und nicht mit dem Code für die Gesprächsübernahme beginnen (standardmäßig `*8`). | leer |

Beide Ziele können ein Telefon, eine Rufgruppe, ein Konferenzraum, eine Anwendung, ein IVR-Menü, eine Mailbox oder *Auflegen* sein, aber keine anderen Geschäftszeiten (nur ein [Sonderzeitraum](#specials) kann zu anderen Geschäftszeiten führen). Siehe [Ziele]({{< relref "/dialplan/ivr.md#destinations" >}}).

### Wochenzeiten {#weekly}

Jeder Wochentag hat eigene Zeitbereiche. Mit **Zeitbereich hinzufügen** fügen Sie einen hinzu; ein Tag kann mehrere Bereiche haben, zum Beispiel `08:00`–`12:00` und `13:00`–`17:00` für eine Mittagspause. Ein Tag ohne Bereiche ist *Ganztägig geschlossen*. Die Schaltfläche **x** entfernt einen Bereich.

- Die Zeiten gelten in der Zeitzone des Systems, siehe [*System → Grundeinstellungen*]({{< relref "/system/general.md#time" >}}).
- Das Ende ist die erste Minute, in der geschlossen ist: `08:00`–`17:00` ist bis 16:59 geöffnet.
- Ein Ende von `23:59` bedeutet bis Mitternacht.
- Das Ende muss nach dem Beginn liegen. Einen Bereich über Mitternacht tragen Sie als zwei Bereiche an zwei Tagen ein.

Neue Geschäftszeiten beginnen mit Montag bis Freitag, 08:00–12:00 und 13:00–17:00. Die **Wochenübersicht** neben den Wochentagen zeigt die Öffnungszeiten als grüne Balken; bei einem gespeicherten Zeitplan markiert eine Linie die aktuelle Uhrzeit.

### Feiertage {#holidays}

An den hier eingetragenen Tagen ist ganztägig geschlossen, unabhängig vom Wochenplan. Klicken Sie auf **Tag hinzufügen** und geben Sie das **Datum** und optional einen **Namen** ein, zum Beispiel `1. Weihnachtstag`. Mit **jedes Jahr** wiederholt sich der Tag jedes Jahr am selben Datum. Bewegliche Feiertage wie Ostern tragen Sie für jedes Jahr einzeln ein. Es können bis zu 200 Tage eingetragen werden.

### Sonderzeiträume {#specials}

Sonderzeiträume leiten Anrufe für eine Weile ganz anders, ohne den Wochenplan anzutasten: Weihnachten und Neujahr, die Betriebsferien im Sommer oder eine Notfallumleitung, die Sie von Hand einschalten. Sie haben Vorrang vor Feiertagen und den wöchentlichen Öffnungszeiten. Klicken Sie auf **Sonderzeitraum hinzufügen** und füllen Sie je Zeitraum eine Zeile aus:

| Feld | Bedeutung |
|---|---|
| Name | Zum Beispiel `Weihnachten` oder `Notfall`. |
| Ziel | Wohin Anrufe gehen, solange der Zeitraum gilt: jedes Ziel von Geschäftszeiten und zusätzlich **andere Geschäftszeiten**, zum Beispiel kürzere Öffnungszeiten über Weihnachten. Diese entscheiden dann zwischen geöffnet und geschlossen. |
| ein | Nur bei einem neuen Zeitraum: ob er eingeschaltet beginnt. Gespeicherte Zeiträume werden oben auf der Seite ein- und ausgeschaltet. |
| Erster Tag, Letzter Tag | Optional. Der Zeitraum gilt nur vom ersten bis zum letzten Tag (ganze Tage, beide eingeschlossen). Geben Sie beide oder keinen an; ohne Tage gilt ein Zeitraum, solange er eingeschaltet ist, zum Beispiel für eine Notfallumleitung. |
| jedes Jahr | Erscheint, sobald beide Tage eingetragen sind. Wiederholt die Tage jedes Jahr. Der Zeitraum darf über den Jahreswechsel gehen, zum Beispiel vom 24. Dezember bis 2. Januar. |
| Funktionscode | Optional, zum Beispiel `*32`. An einem internen Telefon gewählt, schaltet er den Zeitraum ein oder aus; eine Telefontaste (BLF) mit diesem Code leuchtet, solange der Zeitraum eingeschaltet ist, siehe [Telefontasten](#key). |

Ein Zeitraum **gilt**, wenn er eingeschaltet ist und, falls er Tage hat, heute einer davon ist. Der **erste** geltende Zeitraum in der Liste gewinnt; überlappende Zeiträume sind also erlaubt: Setzen Sie den wichtigeren weiter nach oben. Die Reihenfolge ändern Sie mit den Pfeilen oder indem Sie die Zeile am Griff an ihrem Anfang ziehen. Die Schaltfläche **x** entfernt einen Zeitraum. Es können bis zu 50 Zeiträume eingetragen werden.

Geschäftszeiten, die Ziel eines Sonderzeitraums sind, dürfen selbst keine Sonderzeiträume haben, und Geschäftszeiten mit Sonderzeiträumen können kein solches Ziel sein.

### Jahresübersicht {#year}

Der Reiter **Jahresübersicht** zeigt die nächsten zwölf Monate, einen Kalender pro Monat; die Schaltflächen über den Kalendern zeigen stattdessen 24 oder 36 Monate, ein Link mit `?months=48#tab-year` bis zu 60 Monate. Jeder Tag ist danach eingefärbt, was laut Plan gilt: die Wochenzeiten (grün), ganztägig geschlossen, weil der Wochentag keine Öffnungszeiten hat (grau), ein Feiertag (orange) oder ein Sonderzeitraum (eigene Farbe, in der Legende benannt). Sonderzeiträume zählen, wenn sie eingeschaltet sind, in der Reihenfolge der Liste, wie bei Anrufen. Fahren Sie mit der Maus über einen Tag, um Datum und geltende Regel zu sehen. Der Kalender zeigt die Eingaben im Formular, auch bevor Sie sie speichern: Ändern Sie einen Feiertag oder die Tage eines Sonderzeitraums, öffnen Sie den Reiter und prüfen Sie das Ergebnis. Gespeichert wird erst mit **Speichern**. Gespeicherte Sonderzeiträume zählen so, wie sie gerade geschaltet sind; schalten Sie einen oben auf der Seite um, wird der Kalender sofort neu gezeichnet. Ist ein Datum oder eine Uhrzeit in einem anderen Reiter noch nicht gültig, zeigt der Reiter statt der Kalender einen Hinweis. Manuelle Modi und die [Abwesenheitstaste](#key) werden nicht angezeigt.

## Zwischen geöffnet und geschlossen umschalten {#mode}

Bei einem gespeicherten Zeitplan zeigt der Kasten oben, ob **Aktuell** geöffnet ist, und Sie können den **Modus** wählen:

| Modus | Verhalten |
|---|---|
| Automatisch | Folgt den Sonderzeiträumen, Feiertagen und Öffnungszeiten. |
| Geöffnet | Geöffnet, bis zurückgeschaltet wird, zum Beispiel für eine Sonderveranstaltung. |
| Geschlossen | Geschlossen, bis zurückgeschaltet wird, zum Beispiel wenn das Büro früher schließt. |

Mit **Jetzt umschalten** ändern Sie ihn. Der Modus **gilt sofort, ohne dass die Konfiguration übernommen werden muss**, und bleibt auch nach einem Neustart erhalten. Asterisk muss laufen; andernfalls ist der Modus unbekannt und lässt sich nicht ändern.

Das Umschalten des Modus beendet auch eine vorübergehende Umschaltung mit der [Abwesenheitstaste](#key).

Sind Sonderzeiträume eingerichtet, enthält der Kasten unter **Sonderzeiträume** zusätzlich einen Schalter je Zeitraum. Ein Klick schaltet den Zeitraum sofort ein oder aus, ohne dass die Konfiguration übernommen werden muss. Ein eingeschalteter Zeitraum gilt nur an seinen Tagen, sofern er welche hat; der Tooltip zeigt *Ein, gilt heute*, *Ein, aber nicht heute* oder *Aus*. Dieselben Schalter finden Sie in der Liste.

> Der Modus und die Abwesenheitstaste sind Laufzeitzustand und nicht Teil eines Backups. Das Wiederherstellen eines Backups (oder der Import einer Konfiguration) setzt alle Geschäftszeiten auf **Automatisch** zurück und beendet jeden Zustand der Abwesenheitstaste; Sonderzeiträume werden so ein- oder ausgeschaltet, wie sie im Backup gesichert wurden.

## Welche Regel gilt {#precedence}

Wenn ein Anruf eintrifft, und für das Lämpchen der Abwesenheitstaste, entscheidet die erste zutreffende Regel:

1. Der **Modus** *Geöffnet* oder *Geschlossen*, eingestellt auf dieser Seite, über die REST-API oder MCP.
2. Eine vorübergehende Umschaltung mit der **Abwesenheitstaste**.
3. Der erste **Sonderzeitraum** in der Liste, der eingeschaltet ist und dessen Tage den heutigen Tag umfassen: Anrufe gehen an sein Ziel.
4. Ein **Feiertag**: geschlossen.
5. Die **wöchentlichen Öffnungszeiten**: geöffnet oder geschlossen.

Die Regeln 3 bis 5 zusammen sind *Automatisch*. Gilt ein Sonderzeitraum, leitet *Geöffnet* (per Modus oder Taste) Anrufe wie an einem normalen Arbeitstag an das Ziel **Wenn geöffnet**, *Geschlossen* an **Wenn geschlossen**. Ein Sonderzeitraum, dessen Ziel keine Geschäftszeiten sind, zählt als geschlossen; einer, der zu anderen Geschäftszeiten führt, ist geöffnet oder geschlossen wie diese.

## Abwesenheitstaste {#key}

Mit dem **Funktionscode** der Geschäftszeiten erhält jedes Telefon eine Abwesenheitstaste: Ihr Lämpchen zeigt allen den Zustand, und ein Druck schaltet um.

- Das Lämpchen **leuchtet, solange geschlossen ist**, und ist bei geöffnet dunkel, egal aus welchem Grund: Öffnungszeiten, Feiertag, Sonderzeitraum, Taste oder Modus. Es folgt dem Zeitplan innerhalb etwa einer Minute und wechselt bei einem Tastendruck sofort.
- Ein Druck schaltet immer in den **jeweils anderen** Zustand, zum Beispiel um das Büro während der Betriebsferien zu öffnen oder früher zu schließen. Eine Ansage bestätigt den neuen Zustand: „enabled“ (jetzt geöffnet) oder „disabled“ (jetzt geschlossen).
- Diese Umschaltung ist **vorübergehend**: Sie endet von selbst bei der nächsten Änderung des automatischen Zustands, spätestens um Mitternacht. „Geschlossen“ um 15:00 gedrückt endet um 17:00, wenn das Büro ohnehin schließt; ein vergessener Tastendruck hält das Büro nie über ein Wochenende oder einen Feiertag offen.
- Erneut gedrückt, solange die Umschaltung aktiv ist, schaltet die Taste zurück auf *Automatisch* („cancelled“). Sie beendet auch einen auf dieser Seite eingestellten Modus; entspricht dieser Modus dem automatischen Zustand, schaltet die Taste stattdessen in den anderen Zustand, sodass das Lämpchen immer wechselt.

Der **Funktionscode** eines Sonderzeitraums funktioniert für diesen Zeitraum genauso: Ein Druck schaltet ihn ein („activated“) oder aus („de-activated“), und sein Lämpchen **leuchtet, solange der Zeitraum eingeschaltet ist**, zum Beispiel bei einer Notfallumleitung. Ein eingeschalteter Zeitraum, der heute nicht an der Reihe ist, lässt sein Lämpchen leuchten.

Die Lämpchen hält der Überwachungsdienst der Anlage aktuell; nach einem Neustart von Asterisk stimmen sie innerhalb einer Minute wieder.

### Tasten an Snom-Telefonen einrichten {#snom}

1. Öffnen Sie die Weboberfläche des Telefons und gehen Sie zu **Funktionstasten**.
2. Wählen Sie eine freie Taste, stellen Sie den **Typ** auf **BLF** und tragen Sie den Funktionscode als **Nummer** ein, zum Beispiel `*31` für die Abwesenheitstaste oder `*32` für einen Sonderzeitraum.
3. Wählen Sie als Kontext das Konto (die Identität), das bei PhonixPBX registriert ist, und speichern Sie.

Für Telefonbenutzer ist die Taste unter [Telefonieren mit PhonixPBX]({{< relref "/phone-users/_index.md#business-hours" >}}) beschrieben.

### Anrufe außerhalb der Bürozeiten umleiten {#example}

1. Legen Sie ein IVR-Menü an oder wählen Sie ein Telefon mit Mailbox für die Zeit, in der geschlossen ist.
2. Fügen Sie Geschäftszeiten hinzu, legen Sie die Wochenzeiten und Feiertage fest und wählen Sie **Wenn geöffnet** (zum Beispiel die Rufgruppe des Empfangs) und **Wenn geschlossen** (das Menü für außerhalb der Bürozeiten).
3. Klicken Sie auf **Erstellen** und übernehmen Sie die Änderungen.
4. Setzen Sie die Geschäftszeiten als Ziel der [eingehenden Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) Ihrer Nummer.

### Betriebsferien und Notfallumleitung {#example-specials}

1. Legen Sie die Ziele an, zum Beispiel ein IVR-Menü für die Ferien und Geschäftszeiten `Weihnachten`, die von 09:00 bis 12:00 geöffnet sind.
2. Fügen Sie in Ihren Haupt-Geschäftszeiten die Sonderzeiträume in dieser Reihenfolge hinzu:
   - `Notfall`: Ziel das Notfalltelefon, keine Tage, Funktionscode `*32`.
   - `Weihnachten`: Ziel die Geschäftszeiten `Weihnachten`, 24. Dezember bis 2. Januar, **jedes Jahr**, **ein**.
   - `Sommer 2027`: Ziel das Ferienmenü, mit seinen Tagen, **ein**.
3. Speichern und übernehmen Sie. Über Weihnachten folgen Anrufe den kürzeren Zeiten; ein Druck auf die Taste `*32` schaltet die Notfallumleitung ein, die Vorrang vor Weihnachten hat, weil sie in der Liste zuerst steht. Die Abwesenheitstaste wirkt weiterhin über beiden.
