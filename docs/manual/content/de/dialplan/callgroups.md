---
title: "Rufgruppen"
weight: 20
description: "Mehrere Telefone unter einer Nummer gleichzeitig oder nacheinander klingeln lassen."
---
Eine Rufgruppe lässt bei einem Anruf mehrere Telefone klingeln, entweder alle gleichzeitig oder eines nach dem anderen. Verwenden Sie sie für eine Teamnummer, eine Hotline oder einen Empfang, an dem mehrere Personen abheben. Rufgruppen verwalten Sie unter *Wählplan → Rufgruppen*.

Änderungen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Rufgruppenliste {#list}

Klicken Sie über der Liste auf **Rufgruppe**, um eine hinzuzufügen. Die Liste zeigt die **Nummer** (oder `–` bei Gruppen ohne Nummer), den **Namen** (mit *öffentlich*, wenn die Gruppe von außen erreichbar ist), die **Mitglieder** und die **Strategie** (*alle klingeln* oder *nacheinander*). Mit den Schaltflächen am Ende jeder Zeile bearbeiten und löschen Sie die Gruppe. Beim Löschen werden auch die eingehenden Routen und IVR-Tasten entfernt, die zu ihr führten.

## Rufgruppe anlegen oder bearbeiten {#edit}

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Ein Name für Listen und Zielauswahl, zum Beispiel `Vertrieb`. | – |
| Nummer | Die interne Nummer der Gruppe (1–20 Ziffern). Optional: Auch eine Gruppe ohne Nummer kann Ziel einer eingehenden Route oder einer IVR-Taste sein. | leer |
| Mitglieder | Die Telefone und anderen Rufgruppen der Gruppe, mindestens ein Mitglied. Bei *Nacheinander* klingeln die Mitglieder in der hier angezeigten Reihenfolge; ziehen Sie ein Mitglied an eine andere Stelle, um die Reihenfolge zu ändern. Siehe [Rufgruppen in Rufgruppen](#nested). | – |
| Klingelstrategie | *Alle gleichzeitig klingeln lassen*: Alle Mitglieder klingeln zusammen, wer zuerst abhebt, übernimmt den Anruf. *Nacheinander*: Die Mitglieder klingeln der Reihe nach. | Alle gleichzeitig klingeln lassen |
| Klingeldauer (Sekunden) | *Alle gleichzeitig*: wie lange die Gruppe klingelt (5–600); leer klingelt, bis der Anrufer auflegt. *Nacheinander*: wie lange jedes Mitglied klingelt, bevor das nächste an der Reihe ist; leer verwendet die Klingeldauer des Mitglieds (des Telefons oder der enthaltenen Rufgruppe) oder 20 Sekunden, wenn es keine hat. | leer |
| Beschreibung | Eine Notiz für Sie. | leer |
| Von außen erreichbar | Anrufer über Provider dürfen die Gruppe direkt unter ihrer Nummer erreichen. | aus |
| Öffentlicher Name | Bei *Von außen erreichbar*: eine andere Nummer oder ein Name für Anrufer von außen. | leer |

Anrufe, die niemand annimmt, gehen zur Mailbox des **ersten Mitglieds** (bei einer enthaltenen Rufgruppe deren erstes Telefon), sofern dieses Telefon eine Mailbox hat; andernfalls endet der Anruf. Auch die E-Mail zu verpassten Anrufen des ersten Mitglieds gilt für die Gruppe. Deaktivierte Telefone werden übersprungen.

### Rufgruppen in Rufgruppen {#nested}

Ein Mitglied kann auch eine andere Rufgruppe sein. Sie steht für alle ihre Telefone. So pflegen Sie jedes Team in einer Gruppe und bauen daraus größere Gruppen, zum Beispiel *Support* = *Support L1* + *Support L2*. Eine Änderung an *Support L1* gilt dann auch für *Support*.

- Bei *Alle gleichzeitig klingeln lassen* klingeln die Telefone aller enthaltenen Gruppen zusammen.
- Bei *Nacheinander* ist eine enthaltene Gruppe ein Schritt: Alle ihre Telefone klingeln gleichzeitig, danach folgt das nächste Mitglied. Ihre eigene Klingelstrategie spielt dabei keine Rolle.
- Ein Telefon, das in mehreren der Gruppen ist, klingelt nur einmal, an seiner ersten Stelle.
- Eine Gruppe kann sich nicht selbst enthalten, weder direkt noch über eine andere Gruppe. Solche Gruppen werden unter **Mitglieder** nicht angeboten, und das Speichern wird abgelehnt.
- Beim Löschen einer Rufgruppe wird sie auch aus den Gruppen entfernt, die sie enthalten.

### Teamnummer einrichten {#team-number}

1. Stellen Sie sicher, dass jedes Teammitglied ein [Telefon]({{< relref "/accounts/phones.md" >}}) hat.
2. Klicken Sie auf **Rufgruppe**, geben Sie **Name** und **Nummer** ein und wählen Sie die **Mitglieder**.
3. Damit unbeantwortete Anrufe aufgezeichnet werden, setzen Sie ein Telefon mit Mailbox an die erste Stelle und legen eine **Klingeldauer** fest, damit der Anruf die Mailbox erreicht.
4. Klicken Sie auf **Erstellen** und übernehmen Sie die Änderungen.
5. Um eine externe Nummer auf das Team zu leiten, fügen Sie eine [eingehende Route]({{< relref "/accounts/providers.md#incoming-routes" >}}) mit der Gruppe als Ziel hinzu.

> Statt einer Rufgruppe können Sie bei einem Provider auch mehrere eingehende Routen mit derselben Nummer und verschiedenen Telefonen anlegen; diese Telefone klingeln dann gleichzeitig.
