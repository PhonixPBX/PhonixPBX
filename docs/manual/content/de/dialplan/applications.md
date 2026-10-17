---
title: "Anwendungen"
weight: 10
description: "Kleine Wählplan-Programme unter einer Nummer, darunter die mitgelieferten Test- und Dienstnummern."
---
Eine Anwendung ist ein kurzes Stück Asterisk-Wählplan, das ausgeführt wird, wenn jemand ihre Nummer wählt. PhonixPBX bringt einige Anwendungen für Tests und Telefonfunktionen mit, und Sie können eigene hinzufügen, zum Beispiel eine Ansage oder eine Zeitansage. Anwendungen verwalten Sie unter *Wählplan → Anwendungen*.

Änderungen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Anwendungsliste {#list}

Klicken Sie über der Liste auf **Anwendung**, um eine hinzuzufügen. Die Liste zeigt **Nummer**, **Name**, **Beschreibung** und **Status** (aktiviert oder deaktiviert, und *öffentlich*, wenn die Anwendung von außen erreichbar ist). Mit den Schaltflächen am Ende jeder Zeile bearbeiten und löschen Sie die Anwendung. Beim Löschen werden auch die eingehenden Routen und IVR-Tasten entfernt, die zu ihr führten.

Neue Installationen enthalten diese Anwendungen:

| Nummer | Name | Funktion |
|---|---|---|
| `000063` | Read extension number | Liest die Nummer des anrufenden Telefons vor (0000**ME**). |
| `000047` | Read IP | Liest die IP-Adresse der Anlage vor (0000**IP**). |
| `00003246` | Echo | Spielt das Gesprochene zurück, um Ton und Verzögerung zu testen (0000**ECHO**). |
| `000064554` | Milliwatt | Ein Dauerton mit 1000 Hz, um die Leitungsqualität zu testen (0000**MILLI**). |
| `000086` | Voicemail system | Öffnet die Mailbox des anrufenden Telefons (0000**VM**). |
| `000023` | Call forwarding | Schaltet die Rufumleitung des anrufenden Telefons ein und aus (0000**CF**). |
| `00009327357` | Weasels | Eine Testansage (0000**WEASELS**). |

Die Nummern buchstabieren den Namen auf der Telefontastatur. Sie lassen sich wie eigene Anwendungen ändern oder löschen. Wie Telefonbenutzer sie verwenden, ist unter [Telefonieren mit PhonixPBX]({{< relref "/phone-users/_index.md#codes" >}}) beschrieben.

## Anwendung anlegen oder bearbeiten {#edit}

| Feld | Bedeutung | Standard |
|---|---|---|
| Nummer | Die Nummer, die die Anwendung startet: Ziffern oder ein Asterisk-Muster wie `_0XX.` (`X`, `N`, `Z`, `[]`, `.`, `!`). Sie darf nicht anderweitig vergeben sein. | – |
| Name | Ein Name für Listen und Zielauswahl. | – |
| Beschreibung | Eine Notiz, angezeigt in der Liste und in der Druckübersicht. | leer |
| Anwendungslogik | Der Wählplan, ein Schritt pro Zeile (siehe unten). | – |
| Aktiviert | Deaktivierte Anwendungen werden nicht in die Konfiguration übernommen. | an |
| Von außen erreichbar | Anrufer über Provider dürfen die Anwendung direkt unter ihrer Nummer erreichen. | aus |
| Öffentlicher Name | Bei *Von außen erreichbar*: eine andere Nummer oder ein Name für Anrufer von außen. | leer |

### Anwendungslogik {#logic}

Jede Zeile ist ein Wählplan-Schritt in der Form `Priorität,Anwendung(Argumente)`:

- Die Priorität ist eine Zahl (`1`, `2`, …) oder `n` für „die nächste“. Danach kann in Klammern ein Label folgen, zum Beispiel `3(retry),Playback(beep)`; `Goto(retry)` springt dorthin.
- Der erste Schritt braucht die Priorität `1`, sonst findet Asterisk die Nummer nicht.
- Zeilen `include => context` binden einen anderen Wählplan-Kontext ein.
- Zeilen, die mit `;` beginnen, sind Kommentare und werden ignoriert.

Beispiel – eine Ansage abspielen und auflegen:

```
1,Answer()
n,Playback(hello-world)
n,Hangup()
```

Die gewählte Nummer steht in `${EXTEN}`. Wird die Anwendung als Ziel einer eingehenden Route, einer IVR-Taste oder von Geschäftszeiten erreicht, ist `${EXTEN}` gleich `s`. Die [Asterisk-Dokumentation](https://docs.asterisk.org/) beschreibt die verfügbaren Wählplan-Anwendungen und -Funktionen.

> PhonixPBX prüft nur die Form jeder Zeile; die Anwendungslogik wird unverändert an Asterisk übergeben. Testen Sie die Nummer nach dem Übernehmen.
