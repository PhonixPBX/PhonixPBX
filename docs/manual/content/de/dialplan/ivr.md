---
title: "IVR-Menüs"
weight: 30
description: "Sprachmenüs (Auto Attendant): eine Ansage, dann ein Ziel pro Taste."
---
Ein IVR-Menü (Auto Attendant) nimmt einen Anruf an, spielt eine Ansage wie „Für den Vertrieb drücken Sie die 1. Für den Support drücken Sie die 2.“ und leitet den Anrufer dorthin, wohin die gedrückte Taste führt. Menüs können auf andere Menüs führen, so entsteht ein Menübaum. IVR-Menüs verwalten Sie unter *Wählplan → IVR-Menüs*.

Ein Menü erreicht man über seine interne Nummer, als Ziel einer [eingehenden Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) eines Providers, über eine IVR-Taste eines anderen Menüs oder über [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}). Änderungen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## IVR-Menüliste {#list}

Klicken Sie über der Liste auf **IVR-Menü**, um eines hinzuzufügen. Die Liste zeigt:

| Spalte | Bedeutung |
|---|---|
| Nummer | Die interne Nummer, oder `–` bei Menüs, die nur als Ziel verwendet werden. |
| Name | Der Name, *öffentlich*, wenn das Menü von außen erreichbar ist, und die Beschreibung. |
| Tasten | Die Tasten, die eine Option haben. Zeigen Sie auf eine Taste, um ihre Bezeichnung oder ihr Ziel zu sehen. |
| Keine Taste gedrückt | Wohin der Anruf geht, wenn der Anrufer nichts drückt. |
| Status | Aktiviert oder deaktiviert. |

Das Suchfeld über der Liste findet IVR-Menüs nach Nummer, Name oder Beschreibung; wie Suchen und Blättern funktionieren, steht unter [Listen]({{< relref "/getting-started/_index.md#lists" >}}).

Mit den Schaltflächen am Ende jeder Zeile bearbeiten, deaktivieren/aktivieren und löschen Sie das Menü. Ein deaktiviertes Menü wird nicht in die Konfiguration übernommen; Anrufe, die es erreichen würden, enden. Beim Löschen eines Menüs werden die eingehenden Routen und IVR-Tasten entfernt, die zu ihm führten; andere Menüs und Geschäftszeiten, die es für *keine Taste* oder *geschlossen* verwendeten, fallen auf *Auflegen* zurück.

## IVR-Menü anlegen oder bearbeiten {#edit}

Die Bearbeitungsseite hat die Reiter **Allgemein**, **Ansage** und **Tasten**; der Reiter **Tasten** zeigt die Anzahl der Optionen. Ein gespeichertes Menü hat zusätzlich den Reiter **Anrufablauf & Test**. Ein neues Menü öffnet sich auf *Allgemein*, ein gespeichertes auf *Tasten*. Ist beim Speichern eine Eingabe ungültig, öffnet sich der Reiter mit dem Fehler und ist mit einem roten Symbol markiert. **Speichern** (bzw. **Erstellen**) führt zurück zur Liste; **Speichern und weiter bearbeiten** (**Erstellen und weiter bearbeiten**) lässt die Seite auf demselben Reiter offen.

### Allgemein {#general}

Der Reiter **Allgemein** enthält den Namen und wie das Menü erreicht wird.

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Ein Name für Listen und Zielauswahl. | – |
| Nummer | Optionale interne Nummer (1–20 Ziffern), um das Menü direkt anzurufen. Menüs können auch nur als Ziel verwendet werden. | leer |
| Beschreibung | Eine Notiz für Sie. | leer |
| Von außen erreichbar | Anrufer über Provider dürfen das Menü direkt unter seiner Nummer erreichen. | aus |
| Öffentlicher Name | Bei *Von außen erreichbar*: eine andere Nummer oder ein Name für Anrufer von außen. | leer |
| Aktiviert | Deaktivierte Menüs werden nicht in die Konfiguration übernommen. | an |

### Ansage {#announcement}

Die Ansage wird abgespielt, wenn der Anruf das Menü erreicht. Anrufer können schon während der Ansage eine Taste drücken. Wählen Sie die **Quelle**:

- **Hochgeladene Audiodatei**: Wählen Sie unter **Ansage** eine Datei aus oder ziehen Sie eine Audiodatei (WAV, MP3, OGG oder FLAC, bis 16 MB) auf das Upload-Feld. Die Datei wird in 8 kHz Mono umgewandelt, das Format für Telefonie, und lässt sich im Browser anhören. Hochgeladene Ansagen erscheinen auch unter [*Dienste → Medien*]({{< relref "/services/media.md" >}}).
- **Integrierter Sound**: ein Asterisk-Sound in der Ansagesprache des Systems, zum Beispiel `welcome`. Sie können auch den Namen eines anderen installierten Sounds eingeben.

> Kann das System andere Formate nicht umwandeln, werden nur PCM-WAV-Dateien angenommen; die Fehlermeldung zeigt, wie Sie eine Datei mit `sox` umwandeln.

Mit **Per Telefon aufnehmen** sprechen Sie die Ansage stattdessen in ein Telefon: Geben Sie einen **Namen** ein, wählen Sie unter **Telefon klingeln lassen** das Telefon und klicken Sie auf **Mich anrufen**. Nehmen Sie den Anruf an, sprechen Sie nach dem Signalton, drücken Sie `#` und dann `1` zum Speichern; die neue Aufnahme ist sofort unter **Ansage** ausgewählt. Die Schritte sind unter [*Dienste → Medien*]({{< relref "/services/media.md#record" >}}) beschrieben.

Der **Aufnahmetext** hilft Ihnen, eine passende Ansage aufzunehmen. **Aus Optionen erstellen** füllt ihn aus den Tastenoptionen in ihrer Reihenfolge, in der Ansagesprache des Systems, etwa „Für Vertrieb drücken Sie 1. Für Support drücken Sie 2.“. Passen Sie den Text bei Bedarf an, **kopieren** Sie ihn, nehmen Sie ihn mit einer beliebigen Aufnahme-App auf und laden Sie die Datei hoch. Der Text selbst wird nie abgespielt.

### Tasten {#keys}

Klicken Sie für jede Taste, die der Anrufer drücken darf, auf **Option hinzufügen**. Jede Option hat:

- **Taste**: `0`–`9`, `*` oder `#`. Jede Taste kann pro Menü nur einmal vergeben werden.
- **Bezeichnung**: optional, zum Beispiel `Vertrieb`. Sie wird im Aufnahmetext und im Anrufablauf verwendet.
- **Ziel**: wohin die Taste führt, siehe [Ziele](#destinations). Außer zu Telefonen, Gruppen usw. kann eine Taste auch zu einer Mailbox, zu *Menü wiederholen* oder zu *Auflegen* führen.

Ziehen Sie eine Option an ihrem Griff oder verwenden Sie die Pfeil-Schaltflächen, um die Reihenfolge zu ändern. Die Reihenfolge ist die, in der die Optionen angesagt werden sollen; **Aus Optionen erstellen** verwendet sie. Die Schaltfläche **x** entfernt eine Option.

#### Keine oder ungültige Eingabe {#no-input}

Der Abschnitt **Keine oder ungültige Eingabe** unten im Reiter **Tasten** legt fest, was geschieht, wenn der Anrufer nichts oder eine Taste ohne Option drückt.

| Feld | Bedeutung | Standard |
|---|---|---|
| Auf Taste warten (s) | Wie lange das Menü nach der Ansage auf eine Taste wartet (1–60). | 5 |
| Menü wiederholen | Wie oft die Ansage wiederholt wird, wenn keine Taste gedrückt wird (0–9). | 2 |
| Wenn keine Taste gedrückt wird | Wohin der Anruf nach der letzten Wiederholung ohne Taste geht. Jedes [Ziel](#destinations) außer *Menü wiederholen* und außer dem Menü selbst. | Auflegen |
| Bei einer ungültigen Taste | Wohin der Anruf geht, wenn der Anrufer eine Taste ohne Option drückt. *Menü wiederholen* sagt, dass die Auswahl ungültig ist, und spielt das Menü erneut; das zählt als eine der Wiederholungen. | Menü wiederholen |
| Anrufer dürfen Nummern direkt wählen | Anrufer können während der Ansage statt einer Taste eine interne Nummer wählen. Anrufer von außen erreichen nur Nummern, die von außen erreichbar sind. | aus |

Mit den Standardwerten hört ein Anrufer, der nichts drückt, die Ansage dreimal (einmal plus zwei Wiederholungen), jeweils mit 5 Sekunden Wartezeit, danach wird aufgelegt.

> Anrufer von außen erhalten in Gesprächen, die über ein Menü kommen, nie die Funktionscodes zur Vermittlung, und beim Direktwählen erreichen sie nur öffentliche Nummern. Interne Anrufer können jede interne Nummer wählen.

### Anrufablauf & Test {#flow}

Den Reiter **Anrufablauf & Test** gibt es erst, wenn das Menü gespeichert ist.

#### Anrufablauf {#call-flow}

**Anrufablauf** zeigt das Menü im gespeicherten Zustand als Baum: jede Taste mit Bezeichnung und Ziel. Untermenüs werden bis zu drei Ebenen tief aufgeklappt, mit einem Link **Bearbeiten**; eine Taste, die zu einem Menü zurückführt, das schon auf dem Weg liegt, erscheint als „zurück zu …“.

#### Testanruf {#test-call}

**Testanruf** lässt ein Telefon klingeln und verbindet es nach dem Abheben mit dem Menü, als hätte das Telefon das Menü gewählt. Wählen Sie das Telefon unter **Telefon klingeln lassen** und klicken Sie auf **Mich anrufen**. Zur Auswahl stehen nur aktivierte SIP- und IAX-Telefone.

Der Testanruf verwendet das Menü **in der zuletzt übernommenen Fassung**: Übernehmen Sie Ihre Änderungen vorher.

### Ein einfaches Menü bauen {#example}

1. Laden Sie eine Ansage hoch oder wählen Sie eine aus (oder legen Sie zuerst die Optionen an, verwenden Sie **Aus Optionen erstellen** und nehmen Sie den Text auf).
2. Fügen Sie Option `1` → Rufgruppe *Vertrieb*, Option `2` → Rufgruppe *Support* und Option `0` → das Telefon am Empfang hinzu.
3. Setzen Sie **Wenn keine Taste gedrückt wird** auf das Telefon am Empfang, damit auch Anrufer, die keine Taste drücken, angenommen werden.
4. Klicken Sie auf **Erstellen**, übernehmen Sie die Änderungen und hören Sie sich das Menü mit **Testanruf** an.
5. Leiten Sie Ihre Nummer mit einer [eingehenden Route]({{< relref "/accounts/providers.md#route-to-ivr" >}}) auf das Menü.

## Ziele {#destinations}

Eingehende Routen, IVR-Tasten und Geschäftszeiten wählen ihr Ziel alle aus derselben Auswahl. Welche Typen verfügbar sind, hängt davon ab, wo Sie wählen:

| Ziel | Was geschieht | Eingehende Route | IVR-Taste / ungültige Taste | Keine Taste gedrückt | Geschäftszeiten |
|---|---|---|---|---|---|
| Telefone | Lässt das Telefon klingeln, mit seiner Klingeldauer, Mailbox und Rufumleitung. | ja | ja | ja | ja |
| Rufgruppen | Lässt die [Rufgruppe]({{< relref "/dialplan/callgroups.md" >}}) klingeln. | ja | ja | ja | ja |
| Konferenzräume | Verbindet mit dem [Konferenzraum]({{< relref "/services/conferencing.md" >}}) und fragt nach der PIN, falls er eine hat. | ja | ja | ja | ja |
| Anwendungen | Führt die [Anwendung]({{< relref "/dialplan/applications.md" >}}) aus. | ja | ja | ja | ja |
| IVR-Menüs | Spielt ein anderes Menü. | ja | ja | ja | ja |
| Geschäftszeiten | Geht nach den [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}) weiter. | ja | ja | ja | nur für [Sonderzeiträume]({{< relref "/dialplan/hours.md#specials" >}}) |
| Mailbox | Führt den Anrufer direkt zur Mailbox eines Telefons, ohne es klingeln zu lassen. Es werden nur Telefone mit Mailbox angeboten. | nein | ja | ja | ja |
| Menü wiederholen | Spielt das Menü erneut. | nein | ja | nein | nein |
| Auflegen | Beendet den Anruf. | nein | ja | ja | ja |

Deaktivierte Telefone, Anwendungen und Menüs werden nicht erreicht: Ein Anruf zu ihnen endet. Wird ein Objekt gelöscht, werden Routen und Tasten entfernt, die zu ihm führten, und feste Ziele fallen auf *Auflegen* zurück (*Menü wiederholen* bei einer ungültigen Taste).
