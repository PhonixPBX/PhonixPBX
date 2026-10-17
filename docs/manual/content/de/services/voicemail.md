---
title: "Mailbox"
weight: 20
description: "Mailbox-Nachrichten per E-Mail, Benachrichtigungen über verpasste Anrufe und ihre Texte pro Sprache."
---
Unter *Dienste → Mailbox* legen Sie fest, wie Mailbox-Nachrichten aufgezeichnet und per E-Mail zugestellt werden, und bearbeiten die Texte der Mailbox- und Anrufbenachrichtigungen. Die Mailbox selbst wird pro Telefon unter [Konten → Telefone]({{< relref "/accounts/phones.md#edit" >}}) im Reiter *Mailbox & Benachrichtigungen* aktiviert; dort tragen Sie auch die E-Mail-Adressen ein. Telefonbenutzer hören ihre Nachrichten durch Wählen von `000086` ab, siehe [Mailbox für Telefonbenutzer]({{< relref "/phone-users/_index.md#voicemail" >}}).

Für E-Mails muss unter [Dienste → Benachrichtigungen]({{< relref "/services/email.md" >}}) ein Mailserver eingerichtet sein. Solange keiner eingerichtet ist, zeigt die Seite einen Hinweis, und Nachrichten bleiben in der Mailbox auf der TK-Anlage.

Änderungen auf dieser Seite werden wirksam, wenn Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Mailbox-Einstellungen {#settings}

| Feld | Bedeutung | Standard |
|---|---|---|
| Absenderadresse | `From`-Adresse der Mailbox-E-Mails. Leer: die Absenderadresse aus *Dienste → Benachrichtigungen*. | leer |
| Absendername | Anzeigename des Absenders. | `PhonixPBX Voicemail` |
| Max. Nachrichtenlänge (s) | Längste Nachricht, die ein Anrufer aufsprechen kann, 10–3600 Sekunden. | `180` |
| Aufnahme an die E-Mail anhängen | Die Aufnahme als WAV-Datei anhängen. Ohne Anhang kündigt die E-Mail die Nachricht nur an. | ein |
| Nachrichten nach dem E-Mail-Versand auf der TK-Anlage behalten | Eine Nachricht bleibt nach dem Versand in der Mailbox und kann weiterhin am Telefon abgehört werden. Wenn aus, wird eine Nachricht gelöscht, sobald sie an die E-Mail-Adresse eines Telefons verschickt wurde; Telefone ohne E-Mail-Adresse behalten ihre Nachrichten immer. | ein |

Die Ansage, die Anrufer vor dem Signalton hören, können Sie unter [Dienste → Medien]({{< relref "/services/media.md#greeting" >}}) durch eine eigene Aufnahme ersetzen.

## Wer welche E-Mail erhält {#recipients}

Pro Telefon im Reiter *Mailbox & Benachrichtigungen*:

- **Mailbox-Nachrichten per E-Mail senden**: Jede neue Mailbox-Nachricht wird an diese Adresse geschickt.
- **E-Mail-Benachrichtigung bei verpassten Anrufen** mit einer **Benachrichtigungsadresse**: Für jeden nicht angenommenen Anruf auf dem Telefon wird eine E-Mail mit dem Anrufer und dem Grund verschickt (besetzt, keine Antwort, nicht erreichbar oder der Anrufer hat aufgelegt).
- **E-Mail-Sprache**: die Sprache beider E-Mails. Leer bedeutet die Sprache des Telefons.

## E-Mail-Texte {#texts}

Die Mailbox- und Anrufbenachrichtigungen haben eingebaute Texte, die in jede Sprache der Weboberfläche übersetzt sind. Sie können sie pro Sprache ersetzen:

1. Wählen Sie über den Texten die **Sprache**. Die Seite zeigt die Texte, die derzeit für diese Sprache verwendet werden.
2. Bearbeiten Sie **E-Mail-Betreff** und **E-Mail-Text** unter *Neue Sprachnachricht* und *Verpasster Anruf*.
3. Klicken Sie auf **Speichern** und übernehmen Sie die Änderungen.

Ein Abschnitt, der vom eingebauten Text abweicht, ist mit *angepasst* markiert. Ein Text, der dem eingebauten entspricht, wird nicht gespeichert und folgt so auch künftigen Übersetzungen. **Auf Standard zurücksetzen** entfernt alle eigenen Texte der gewählten Sprache. Ein Betreff darf bis zu 200 Zeichen lang sein, ein Text bis zu 4000; Steuerzeichen sind nicht erlaubt.

Die Texte einer Sprache wirken nur auf Telefone, deren E-Mail-Sprache diese Sprache ist. Wenn Sie die Texte anpassen, tun Sie das für jede Sprache, die Ihre Benutzer verwenden.

## Platzhalter {#placeholders}

Platzhalter schreiben Sie als `${NAME}`; sie werden beim Versand ersetzt. Der Hilfetext unter jedem Textfeld nennt die verfügbaren Namen.

| Platzhalter | Inhalt |
|---|---|
| `${VM_NAME}` | Name des Mailbox-Inhabers (der Caller-ID-Name des Telefons) |
| `${VM_MAILBOX}` | Mailbox-Nummer (die Nebenstelle) |
| `${VM_MSGNUM}` | Nummer der Nachricht in der Mailbox |
| `${VM_DUR}` | Länge der Nachricht, z. B. `0:42` |
| `${VM_CALLERID}` | Anrufer, z. B. `"Bob" <0441234567>` |
| `${VM_DATE}` | Datum und Uhrzeit der Nachricht, passend zur Sprache formatiert |

Die `VM_`-Platzhalter gelten für die Mailbox-E-Mail. Die Benachrichtigung über verpasste Anrufe verwendet:

| Platzhalter | Inhalt |
|---|---|
| `${NAME}` | Name des angerufenen Telefons |
| `${EXTENSION}` | Angerufene Nebenstelle |
| `${CALLERID}` | Anrufer |
| `${REASON}` | Warum der Anruf verpasst wurde: besetzt, keine Antwort, nicht erreichbar oder der Anrufer hat aufgelegt |
| `${DATE}` | Datum und Uhrzeit des Anrufs, passend zur Sprache formatiert |

## Vorschau {#preview}

Die Karte *Vorschau* unten zeigt beide E-Mails der gewählten Sprache, gefüllt mit Beispielwerten. Sie zeigt die gespeicherten Texte; speichern Sie also, bevor Sie das Ergebnis prüfen.
