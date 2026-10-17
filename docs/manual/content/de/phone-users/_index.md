---
title: "Telefonieren mit PhonixPBX"
weight: 20
icon: phone-call
description: "Wählcodes für Telefonbenutzer: Vermitteln, Heranholen, Parken, Mailbox, Rufumleitung, Konferenzen und Testnummern."
---
Dieses Kapitel richtet sich an alle, die mit einem an PhonixPBX angeschlossenen Telefon telefonieren – ob Tischtelefon oder Softphone-App. Es zeigt, welche Codes Sie wählen können und was sie bewirken. Zugang zur Weboberfläche brauchen Sie dafür nicht.

> Die folgenden Codes sind die Voreinstellungen. Ihr Administrator kann sie unter *Wählplan → Vermittlung & Parken* und *Wählplan → Anwendungen* geändert oder einzelne abgeschaltet haben. Funktioniert ein Code nicht, fragen Sie Ihren Administrator.

Eine **interne Nummer** erreichen Sie, indem Sie einfach die Nummer des anderen Telefons wählen, zum Beispiel `21`. Wie Sie nach außen telefonieren (etwa mit vorangestellter `0`), hängt von der Einrichtung Ihrer Anlage ab.

## Alle Codes im Überblick {#codes}

| Code | Funktion | Wann |
|---|---|---|
| `**` + Nummer | Vermittlung mit Rückfrage: erst mit der anderen Person sprechen, dann das Gespräch übergeben | im Gespräch |
| `##` + Nummer | Vermittlung ohne Rückfrage: Gespräch sofort übergeben | im Gespräch |
| `*0` | Trennen: Gespräch beenden | im Gespräch |
| `*8` | Einen Anruf heranholen, der an einem anderen Telefon klingelt | Telefon frei |
| `*8` + Nummer | Einen Anruf heranholen, der an dieser Nummer klingelt | Telefon frei |
| `700` | Gespräch parken (dorthin vermitteln) | im Gespräch |
| `701` … `720` | Geparktes Gespräch zurückholen | Telefon frei |
| `000086` | Mailbox: Nachrichten abhören, Ansagen aufnehmen | Telefon frei |
| `000023` | Rufumleitung ein- oder ausschalten | Telefon frei |
| `2663` | Standard-Konferenzraum | Telefon frei |
| vom Administrator festgelegt | Geschäftszeiten zwischen *Automatisch* und *Geschlossen* umschalten | Telefon frei |
| `000063` | Eigene Nummer ansagen | Test |
| `000047` | IP-Adresse der Anlage ansagen | Test |
| `00003246` | Echotest | Test |
| `000064554` | Testton (1000 Hz) | Test |

Viele Codes ergeben auf der Telefontastatur ein (englisches) Wort: `000086` = 0000**VM** (Voicemail), `000023` = 0000**CF** (Call Forwarding), `2663` = **CONF**, `00003246` = 0000**ECHO**.

## Gespräche vermitteln {#transfer}

Sie können jedes Gespräch vermitteln, an dem Sie beteiligt sind. Anrufer von außen können diese Codes nicht verwenden, nur Sie am internen Telefon.

**Vermittlung mit Rückfrage (`**`)** – Sie sprechen vor der Übergabe mit der neuen Person:

1. Drücken Sie während des Gesprächs `**`. Der Anrufer wird gehalten.
2. Wählen Sie die Nummer, an die Sie vermitteln möchten. Die Anlage wählt etwa drei Sekunden nach Ihrer letzten Ziffer.
3. Sprechen Sie mit der Person, die abhebt.
4. Legen Sie auf. Die beiden sind nun verbunden.

Hebt die andere Person nicht innerhalb von 15 Sekunden ab, sind Sie wieder mit dem Anrufer verbunden.

**Vermittlung ohne Rückfrage (`##`)** – Sie übergeben das Gespräch, ohne mit der neuen Person zu sprechen:

1. Drücken Sie während des Gesprächs `##`.
2. Wählen Sie die Nummer. Etwa drei Sekunden nach Ihrer letzten Ziffer wird das Gespräch übergeben und Ihre Verbindung getrennt.

Ein kurzer Piepton bestätigt die Vermittlung; ein Fehlerton bedeutet, dass sie nicht geklappt hat, etwa weil es die Nummer nicht gibt.

**Trennen (`*0`)** – drücken Sie während eines Gesprächs `*0`, um es zu beenden, genau wie beim Auflegen. In einem Gespräch zwischen zwei internen Telefonen kann das jede Seite; in einem Gespräch mit einem externen Teilnehmer nur Sie am internen Telefon.

Die meisten Tischtelefone und Softphones haben außerdem eine eigene Taste *Transfer* bzw. *Übergabe*. Sie funktioniert mit PhonixPBX ebenfalls und ist oft bequemer.

## Anrufe heranholen {#pickup}

Klingelt das Telefon einer Kollegin und niemand hebt ab, können Sie den Anruf an Ihrem eigenen Telefon annehmen:

- Wählen Sie `*8`, um einen Anruf heranzuholen, der an irgendeinem Telefon klingelt.
- Wählen Sie `*8` und dahinter eine Nummer, um einen Anruf genau an diesem Telefon heranzuholen, zum Beispiel `*821` für die Nummer 21.

## Gespräche parken {#parking}

Ein geparktes Gespräch wartet „für alle“: Jeder kann es von jedem Telefon aus zurückholen. Das ist praktisch, wenn die gewünschte Person gerade woanders im Haus ist.

1. Vermitteln Sie das Gespräch an `700` – am besten mit Rückfrage, also `**700`. Die Anlage sagt die Nummer des Parkplatzes an, zum Beispiel „701“. Legen Sie auf.
2. Teilen Sie der Kollegin die Parkplatznummer mit (zum Beispiel per Durchsage).
3. Sie wählt die Parkplatznummer, `701` bis `720`, an einem beliebigen Telefon und ist mit dem Anrufer verbunden.

Der Anrufer hört Wartemusik. Holt niemand das Gespräch innerhalb von 45 Sekunden zurück, klingelt es wieder an dem Telefon, das es geparkt hat.

## Mailbox {#voicemail}

Hat Ihr Administrator die Mailbox für Ihr Telefon aktiviert, können Anrufer eine Nachricht hinterlassen, wenn Sie nicht abheben, besetzt sind oder Ihr Telefon nicht erreichbar ist.

**Nachrichten abhören:** Wählen Sie an Ihrem eigenen Telefon `000086` und geben Sie Ihre **Mailbox-PIN** ein, gefolgt von `#`. Die PIN erhalten Sie von Ihrem Administrator. Danach führt Sie ein Sprachmenü; die wichtigsten Tasten sind:

| Taste | Funktion |
|---|---|
| `1` | Neue Nachrichten abhören |
| `5` / `4` / `6` | Nachricht wiederholen / vorherige / nächste Nachricht |
| `7` | Nachricht löschen |
| `9` | Nachricht in einem Ordner speichern |
| `0` | Mailbox-Optionen: Ansagen aufnehmen, PIN ändern |
| `*` | Hilfe |
| `#` | Beenden |

**Ansagen:** In den Mailbox-Optionen (`0`) nehmen Sie Ihre eigenen Ansagen auf:

- `1` – die Ansage für **nicht erreichbar**, wenn Sie nicht abheben oder Ihr Telefon nicht erreichbar ist,
- `2` – die Ansage für **besetzt**, wenn Sie gerade telefonieren,
- `3` – Ihren Namen,
- `5` – PIN ändern.

Ohne eigene Aufnahme hören Anrufer eine Standardansage mit Ihrer Nummer. Hat Ihr Administrator eine gemeinsame Ansage für das ganze Unternehmen hochgeladen, ersetzt diese Ihre Ansage für „nicht erreichbar“.

**Mailbox per E-Mail:** Ihr Administrator kann jede neue Nachricht an Ihre E-Mail-Adresse senden lassen, meist mit der Aufnahme im Anhang. Je nach Einrichtung bleiben per E-Mail verschickte Nachrichten zusätzlich auf der Anlage oder werden dort gelöscht. Auch für verpasste Anrufe können Sie eine E-Mail erhalten.

## Rufumleitung {#forwarding}

Die Rufumleitung leitet alle Anrufe für Ihre Nummer an eine andere Nummer weiter, zum Beispiel auf Ihr Handy.

**Einschalten:** Wählen Sie `000023`. Wählen Sie nach der Ansage und dem Piepton die Zielnummer – intern oder extern, genau so, wie Sie sie an Ihrem Telefon wählen würden. Die Anlage sagt die Nummer zur Bestätigung an. Anrufe für Ihre Nummer gehen nun direkt an das Ziel.

**Ausschalten:** Wählen Sie erneut `000023`. Drei kurze Töne bestätigen, dass die Umleitung aus ist.

Wählen Sie nach dem Piepton nichts, hören Sie die Ansage „ungültig“, und es ändert sich nichts.

## Telefonkonferenzen {#conference}

In einem Konferenzraum sprechen mehrere Personen miteinander. Alle Teilnehmer wählen die Nummer des Raums; auch Anrufer von außen können teilnehmen, wenn Ihr Administrator den Raum von außen erreichbar gemacht hat.

- Der Standardraum ist `2663`. Ihr Administrator kann weitere Räume mit anderen Nummern eingerichtet haben.
- Hat der Raum eine **PIN**, werden Sie beim Betreten danach gefragt. Geben Sie sie ein und drücken Sie `#`. Nach drei falschen Versuchen wird die Verbindung beendet.
- Manche Räume haben eine **Admin-PIN**. Damit treten Sie als Moderator bei und haben zusätzliche Tasten.
- Solange Sie allein im Raum sind, hören Sie Musik. Beim Betreten sagt die Anlage an, wie viele Personen im Raum sind.

Tasten während der Konferenz (drücken Sie zuerst `*`, um das Menü zu hören, oder direkt die Taste):

| Taste | Funktion | Wer |
|---|---|---|
| `1` | Eigenes Mikrofon stumm schalten / wieder einschalten | alle |
| `4` / `6` | Leiser / lauter hören | alle |
| `7` / `9` | Leiser / lauter sprechen | alle |
| `8` | Konferenz verlassen | alle |
| `2` | Raum sperren / entsperren (niemand kann mehr beitreten) | Moderator |
| `3` | Den zuletzt beigetretenen Teilnehmer entfernen | Moderator |

## Geschäftszeiten {#business-hours}

Ihr Administrator kann Geschäftszeiten festlegen: Während der Öffnungszeiten gehen Anrufe zum Beispiel an den Empfang, außerhalb an eine Ansage oder die Mailbox. Für jede Geschäftszeit kann er zusätzlich einen **Funktionscode** festlegen, mit dem Sie an einem internen Telefon von Hand umschalten:

- Code einmal wählen: Die Geschäftszeit steht auf **Geschlossen** – etwa wenn das Büro früher schließt. Sie hören die Ansage „aktiviert“.
- Code noch einmal wählen: Sie steht wieder auf **Automatisch** und folgt dem Zeitplan. Sie hören die Ansage „deaktiviert“.

Die Umschaltung gilt sofort für alle Anrufer. Den Code erfahren Sie von Ihrem Administrator.

## Testnummern {#tests}

Mit diesen Nummern prüfen Sie ein Telefon und die Verbindung:

| Nummer | Was Sie hören |
|---|---|
| `000063` | Ihre eigene Nummer, immer wieder angesagt. Zeigt, dass das Telefon mit dem richtigen Konto angemeldet ist. |
| `000047` | Die IP-Adresse der Anlage, Zahlengruppe für Zahlengruppe. |
| `00003246` | Echotest: Alles, was Sie sagen, wird Ihnen wieder vorgespielt. So beurteilen Sie Verzögerung und Sprachqualität. |
| `000064554` | Einen gleichbleibenden Ton von 1000 Hz. So prüfen Sie den Sprachweg auf Aussetzer. |

Legen Sie auf, um den Test zu beenden.
