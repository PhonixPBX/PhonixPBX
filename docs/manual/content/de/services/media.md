---
title: "Medien"
weight: 40
description: "Wartemusik, die Mailbox-Ansage, IVR-Ansagen, Aufnahmen per Telefon, Sprachausgabe aus Text und die Sprache der Ansagen."
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

## Aus Text erzeugen {#tts}

Ein Text-to-Speech-Server kann eine IVR-Ansage oder die Mailbox-Ansage für Sie sprechen. Richten Sie den Server zuerst unter [Text-to-Speech-Server](#tts-server) ein.

Wählen Sie unter **Aus Text erzeugen**, was Sie **Erstellen** (bei einer IVR-Ansage auch ihren **Namen**), eine **Stimme** und das **Tempo**, und geben Sie den **Text** ein (bis 2000 Zeichen). **Anhören** spielt das Ergebnis im Browser ab, ohne es zu speichern; **Erstellen** speichert es wie eine hochgeladene Datei. Eine neue Mailbox-Ansage ersetzt die alte und muss übernommen werden.

> Der Text wird an den Text-to-Speech-Server gesendet. Verwenden Sie einen Server, dem Sie vertrauen, am besten einen in Ihrem eigenen Netz.

## Text-to-Speech-Server {#tts-server}

PhonixPBX verwendet einen Server mit der RestfulTTS-API. Eine eigene Sprachausgabe bringt die Anlage nicht mit.

| Feld | Bedeutung | Standard |
|---|---|---|
| Serveradresse | Basis-URL des Servers, zum Beispiel `http://tts.example.com:8000`. Leer schaltet die Funktion aus. | leer |
| Access-Token | Nur wenn der Server eines verlangt; es wird als Bearer-Token gesendet. Lassen Sie das Feld leer, um das gespeicherte Token zu behalten; wenn Sie die Serveradresse ohne neues Token ändern, wird es entfernt. | leer |
| Standardstimme | Die Stimme, wenn Sie keine wählen. Leer: die Stimme des Servers für die [Sprache der Ansagen](#prompt-language) des Systems. | leer |
| Tempo | 0,5 (langsam) bis 2 (schnell). | 1 |
| Zeitlimit (Sekunden) | Wie lange auf den Server gewartet wird. | 60 |

Die Audiodaten werden in Telefonqualität angefordert (8 kHz Mono-WAV). Skripte können Ansagen über die [REST-API]({{< relref "/reference/api.md#media" >}}) aus Text erzeugen.

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
