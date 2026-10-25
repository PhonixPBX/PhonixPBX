---
title: "Telefonkonferenzen"
weight: 30
description: "Konferenzräume mit optionaler PIN und Admin-PIN, intern und von außen erreichbar."
---
Unter *Dienste → Telefonkonferenzen* verwalten Sie die Konferenzräume. Ein Konferenzraum ist eine Nummer, die mehrere Anrufer wählen, um miteinander zu sprechen. Räume lassen sich mit einer PIN schützen, und mit einer Admin-PIN tritt ein Moderator mit zusätzlichen Rechten bei. Eine neue Installation hat einen Raum mit der Nummer `2663` („CONF“ auf der Tastatur).

Änderungen an Räumen werden wirksam, wenn Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}). Wie Anrufer eine Konferenz nutzen, ist für Telefonbenutzer unter [Konferenzen]({{< relref "/phone-users/_index.md#conference" >}}) beschrieben.

## Raumliste {#list}

Die Liste zeigt jeden Raum mit **Nummer**, **Name** und **Schutz**:

- **PIN**: Anrufer müssen eine PIN eingeben.
- **Admin-PIN**: Eine Moderator-PIN ist gesetzt.
- **offen**: Jeder, der die Nummer wählt, tritt direkt bei.
- Die Markierung **öffentlich** neben dem Namen bedeutet, dass der Raum von außen erreichbar ist.

Das Suchfeld über der Liste findet Konferenzräume nach Nummer oder Name; wie Suchen und Blättern funktionieren, steht unter [Listen]({{< relref "/getting-started/_index.md#lists" >}}).

Klicken Sie über der Liste auf **Konferenzraum**, um einen Raum anzulegen, auf die Nummer oder das Stiftsymbol, um einen Raum zu bearbeiten, und auf das Papierkorbsymbol, um ihn zu löschen. Beim Löschen eines Raums werden auch eingehende Routen und IVR-Tasten entfernt, die zu ihm führten.

## Raumeinstellungen {#edit}

| Feld | Bedeutung | Standard |
|---|---|---|
| Nummer | Die interne Nummer, die Anrufer wählen, 1–20 Ziffern. Sie darf nicht von einem Telefon, einer Rufgruppe oder einem anderen Objekt belegt sein. | — |
| Name | Name des Raums, angezeigt in Listen und bei der Auswahl von Zielen. | — |
| PIN | Optional, nur Ziffern (bis zu 16). Anrufer müssen sie zum Beitreten eingeben. | leer |
| Admin-PIN | Optional, nur Ziffern (bis zu 16). Wer sie statt der PIN eingibt, tritt als Moderator bei. | leer |
| Von außen erreichbar | Anrufer über Provider erreichen den Raum direkt über seine Nummer oder seinen öffentlichen Namen (zum Beispiel über eine Durchwahl). Ohne diese Option erreichen externe Anrufer den Raum nur über eine eingehende Route oder ein IVR-Menü, das auf ihn zeigt. | aus |
| Öffentlicher Name | Optionaler Alias, der von außen statt der Nummer verwendet wird, z. B. `meeting` für `sip:meeting@pbx`. Buchstaben, Ziffern und `. _ + -`. Nur sichtbar mit *Von außen erreichbar*. Leer: die Raumnummer. | leer |

So wirken die PINs beim Beitreten:

- **Keine PIN gesetzt**: Der Anrufer tritt sofort bei.
- **PIN gesetzt**: Der Anrufer wird nach einer PIN gefragt und schließt mit `#` ab. Die PIN führt in den Raum als Teilnehmer, die Admin-PIN als Moderator.
- **Nur die Admin-PIN gesetzt**: Teilnehmer drücken nur `#` ohne PIN; die Admin-PIN führt in den Raum als Moderator.

Nach drei falschen Eingaben wird der Anruf beendet.

> Ein Raum ohne PIN, der von außen erreichbar ist, kann von jedem benutzt werden, der die Nummer kennt. Setzen Sie für öffentliche Räume eine PIN.

## Menü während der Konferenz {#in-call-menu}

Während einer Konferenz bedienen Anrufer die Tastatur:

| Taste | Funktion |
|---|---|
| `*` | Menüansage abspielen |
| `1` | Eigenes Mikrofon stumm schalten / wieder einschalten |
| `4` / `6` | Leiser / lauter hören |
| `7` / `9` | Leiser / lauter sprechen |
| `8` | Konferenz verlassen |
| `2` | Nur Moderatoren: Raum sperren / entsperren |
| `3` | Nur Moderatoren: den zuletzt beigetretenen Anrufer entfernen |

Wer allein in einem Raum ist, hört Wartemusik; beim Beitreten wird die Anzahl der Teilnehmer angesagt. Ein Raum fasst bis zu 50 Teilnehmer.
