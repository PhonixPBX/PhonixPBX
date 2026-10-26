---
title: "Medien"
weight: 40
description: "Wartemusik, die Mailbox-Ansage, IVR-Ansagen, Aufnahmen per Telefon und die Sprache der Ansagen."
---
Unter *Dienste → Medien* verwalten Sie eigene Audiodateien: Wartemusik, eine eigene Mailbox-Ansage und die Ansagen von IVR-Menüs. Außerdem zeigt die Seite, in welcher Sprache die Systemansagen abgespielt werden.

Das Hochladen oder Löschen von Wartemusik und Mailbox-Ansage muss übernommen werden, bevor Anrufer die Änderung hören, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Wartemusik {#moh}

Anrufer hören Wartemusik, während sie gehalten oder geparkt werden oder allein in einer Konferenz sind. Ohne eigene Dateien spielt PhonixPBX die mitgelieferte Musik.

Ziehen Sie eine oder mehrere Audiodateien auf das Feld *Wartemusik* oder klicken Sie darauf, um Dateien auszuwählen. Alle hochgeladenen Musikdateien bilden eine Playlist, die in zufälliger Reihenfolge abgespielt wird. Sobald eine Datei hochgeladen ist, wird die mitgelieferte Musik nicht mehr verwendet; wenn Sie die letzte eigene Datei löschen, wird sie wieder verwendet.

> Verwenden Sie nur Musik, die Sie Anrufern vorspielen dürfen. Viele Musiklizenzen decken die öffentliche Wiedergabe in einer Telefonanlage nicht ab.

## Mailbox-Ansage {#greeting}

Die Mailbox-Ansage ersetzt die Standardansage „nicht erreichbar“, die Anrufer hören, bevor sie eine Nachricht hinterlassen. Sie gilt für alle Mailboxen. Es gibt nur eine Ansage: Eine neu hochgeladene Datei ersetzt die alte. Löschen Sie sie in der Dateiliste, um zur Standardansage zurückzukehren.

Sprechen Sie einen neutralen Text auf, der zu jeder Mailbox passt, zum Beispiel „Der gewünschte Gesprächspartner ist nicht erreichbar. Bitte hinterlassen Sie eine Nachricht nach dem Signalton.“

## IVR-Ansagen {#ivr}

Die Ansagen von IVR-Menüs laden Sie im Menü-Editor unter [Wählplan → IVR-Menüs]({{< relref "/dialplan/ivr.md" >}}) hoch. Sie erscheinen hier in der Dateiliste mit dem Typ *IVR-Ansage*. Wenn Sie eine Ansage löschen, die ein Menü noch verwendet, bleibt dieses Menü stumm, bis Sie eine andere Ansage wählen; übernehmen Sie die Änderung anschließend.

## Per Telefon aufnehmen {#record}

Statt eine Datei hochzuladen, können Sie eine IVR-Ansage oder die Mailbox-Ansage auch in ein Telefon sprechen. Wählen Sie unter **Per Telefon aufnehmen**, was Sie **Aufnehmen** (bei einer IVR-Ansage auch ihren **Namen**), und unter **Telefon klingeln lassen** das Telefon, und klicken Sie auf **Mich anrufen**:

1. Die Anlage ruft das Telefon an. Nehmen Sie ab und sprechen Sie den Text nach dem Signalton.
2. Beenden Sie die Aufnahme mit `#`. Das Telefon spielt sie ab.
3. Drücken Sie `1` zum Speichern, `2` zum erneuten Anhören oder `3` für eine neue Aufnahme.

Die Seite zeigt jeden Schritt an und, sobald Sie `1` gedrückt haben, die neue Datei in der Liste. Legen Sie vor der `1` auf, wird die Aufnahme verworfen, ebenso wenn Sie den Anruf nicht annehmen. Eine Aufnahme wird wie eine hochgeladene Datei gespeichert: Eine IVR-Ansage steht im Menü-Editor zur Auswahl, eine neue Mailbox-Ansage ersetzt die alte und muss übernommen werden.

Anrufen kann die Anlage nur SIP- und IAX-Telefone. Die Hinweise am Telefon kommen in der Sprache der Ansagen dieses Telefons.

## Hochgeladene Dateien {#files}

Die Tabelle listet alle hochgeladenen Dateien mit Typ, Name, Größe und Zeitpunkt des Hochladens. Mit dem Download-Symbol hören Sie die konvertierte Datei (WAV) an, mit dem Papierkorbsymbol löschen Sie sie.

Das Suchfeld über der Liste findet Dateien nach Name oder Typ; wie Suchen und Blättern funktionieren, steht unter [Listen]({{< relref "/getting-started/_index.md#lists" >}}).

## Dateiformate {#formats}

- Für Wartemusik werden WAV-, MP3-, OGG- und FLAC-Dateien bis je 64 MB angenommen, für die Mailbox-Ansage WAV, MP3 und OGG bis 16 MB.
- Jede Datei wird in 8 kHz, 16 Bit Mono-WAV konvertiert, das Format, das Asterisk ohne weitere Umwandlung abspielt. Telefonaudio ist ohnehin auf diese Qualität begrenzt, hochwertige Quellen bringen also keinen Vorteil.
- Am besten eignen sich Aufnahmen ohne lange Stille am Anfang und mit gemäßigter Lautstärke.
- Skripte können Dateien auch über die [REST-API]({{< relref "/reference/api.md#media" >}}) hochladen.

## Sprache der Ansagen {#prompt-language}

Die Systemansagen (Mailbox-Menüs, Konferenzansagen, „die Nummer ist nicht erreichbar“ usw.) werden in der Standardsprache der Ansagen abgespielt. Die Karte *Sprachansagen* zeigt die aktuelle Sprache; ändern können Sie sie unter [System → Grundeinstellungen]({{< relref "/system/general.md#tones-language" >}}). Jedes Telefon kann zusätzlich eine eigene Sprache haben.

Die Firmware enthält englische Ansagen. Für andere Sprachen werden die englischen Aufnahmen abgespielt, solange keine Aufnahmen für diese Sprache installiert sind.
