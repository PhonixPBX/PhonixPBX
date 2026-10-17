---
title: "Vermittlung & Parken"
weight: 50
description: "Funktionscodes zum Vermitteln, Übernehmen und Beenden von Gesprächen sowie die Nummern zum Parken."
---
Unter *Wählplan → Vermittlung & Parken* legen Sie die Funktionscodes fest, die Telefonbenutzer während eines Gesprächs wählen, um es zu vermitteln oder zu beenden, den Code zur Übernahme eines klingelnden Telefons und die Nummern zum Parken von Gesprächen. Die Codes werden auf der Telefontastatur eingegeben und funktionieren daher an jedem Telefon, unabhängig von dessen eigenen Vermittlungstasten.

Mit **Speichern** sichern Sie die Einstellungen. Sie werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}). Wie Benutzer die Codes wählen, ist unter [Telefonieren mit PhonixPBX]({{< relref "/phone-users/_index.md#transfer" >}}) beschrieben.

## Funktionscodes {#feature-codes}

Funktionscodes bestehen aus 1–8 Zeichen: Ziffern, `*` und `#`.

| Feld | Bedeutung | Standard |
|---|---|---|
| Vermittlung mit Rückfrage | Während eines Gesprächs gewählt: hält den Gesprächspartner, Sie wählen eine Nummer, sprechen mit der angerufenen Person und legen dann auf, um das Gespräch zu übergeben. | `**` |
| Vermittlung ohne Rückfrage | Während eines Gesprächs gewählt: Sie wählen eine Nummer, und das Gespräch wird sofort übergeben, ohne vorher zu sprechen. | `##` |
| Gesprächsübernahme | Allein gewählt, übernimmt den Anruf eines beliebigen klingelnden Telefons. Mit einer Nummer dahinter, zum Beispiel `*8101`, übernimmt den Anruf, der an diesem Telefon klingelt. | `*8` |
| Trennen | Während eines Gesprächs gewählt: beendet das Gespräch. | `*0` |
| Timeout für Funktionsziffern (ms) | Wie lange die Anlage zwischen den Ziffern eines Funktionscodes wartet. | 1000 |
| Timeout für Vermittlungsziffern (s) | Wie lange die Anlage auf die nächste Ziffer des Vermittlungsziels wartet, bevor sie wählt. | 3 |
| Timeout ohne Antwort bei Vermittlung mit Rückfrage (s) | Wie lange das Vermittlungsziel bei einer Vermittlung mit Rückfrage klingelt, bevor der Anruf zurückkommt. | 15 |

Wer einen Anruf angenommen hat, kann ihn immer vermitteln. Der Anrufer kann nur vermitteln, wenn er ein internes Telefon ist; Anrufer von außen können die Funktionscodes nicht verwenden. Dasselbe gilt für *Trennen*: Zwischen zwei internen Telefonen kann jede Seite das Gespräch beenden, bei Gesprächen mit externen Teilnehmern nur das interne Telefon.

> Funktionscodes werden während des Gesprächs als Tastendrücke übertragen. Funktionieren sie nicht, prüfen Sie den *DTMF-Modus* des [Telefons]({{< relref "/accounts/phones.md#advanced" >}}).

## Gespräche parken {#parking}

Beim Parken wird ein Gespräch auf einem nummerierten Parkplatz gehalten, sodass es von jedem Telefon aus übernommen werden kann.

| Feld | Bedeutung | Standard |
|---|---|---|
| Parknummer | Vermitteln Sie ein Gespräch an diese Nummer, um es zu parken. Die Anlage sagt den Parkplatz an, auf dem das Gespräch geparkt wurde. | `700` |
| Erster Platz | Die Nummer des ersten Parkplatzes. | `701` |
| Letzter Platz | Die Nummer des letzten Parkplatzes. | `720` |
| Parkdauer (s) | Wie lange ein Gespräch geparkt bleibt (5–3600). Danach klingelt es wieder an dem Telefon, das es geparkt hat. | 45 |

Um ein Gespräch zu parken, vermitteln Sie es an die Parknummer (zum Beispiel mit **Vermittlung ohne Rückfrage**, `##700`) und merken sich den angesagten Parkplatz. Um es zu übernehmen, wählen Sie die Nummer des Parkplatzes an einem beliebigen Telefon. Der geparkte Anrufer hört Wartemusik.

Die Parknummer und die Parkplätze sind reserviert: Telefone, Rufgruppen und andere Objekte können diese Nummern nicht verwenden.
