---
title: "API-Tokens"
weight: 80
description: "Bearer-Tokens für REST-API und MCP: nur lesen oder lesen und schreiben, Ablauf, Berechtigung für Anrufe."
---
Unter *Erweitert → API-Tokens* erstellen Sie die Tokens, mit denen Skripte, Monitoring-Systeme und KI-Assistenten über die [REST-API]({{< relref "/reference/api.md" >}}) (`/api/v1`) und das Model Context Protocol (MCP, `/api/mcp`) auf PhonixPBX zugreifen. Ein Token ersetzt Benutzername und Passwort: Wer es besitzt, erhält den Zugriff, den es gewährt, ohne sich anzumelden.

Tokens wirken sofort, ohne Übernehmen.

## Token erstellen {#create}

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Ein Name, der sagt, wo das Token verwendet wird, z. B. `monitoring`. Bis zu 64 Zeichen. | — |
| Zugriff | **Nur lesen**: nur GET-Anfragen und die lesenden MCP-Werkzeuge; Mailbox- und Konferenz-PINs sind in den Antworten nicht enthalten. **Lesen und Schreiben**: darf zusätzlich Objekte anlegen, ändern und löschen, Einstellungen ändern und die Konfiguration übernehmen. | Nur lesen |
| Darf Anrufe tätigen | Erlaubt Click-to-Call: ein Telefon klingeln lassen und von dort eine Nummer wählen (`POST /api/v1/calls`, MCP-Tool `originate_call`). Das funktioniert auch mit Nur-Lese-Tokens; es ist die einzige schreibende Aktion, die sie erhalten. | aus |
| Läuft ab in (Tagen) | Gültigkeit in Tagen, 1–3653. Leer: Das Token läuft nicht ab. | leer |

Klicken Sie auf **Erstellen**. Das Token wird **einmalig** in einem grünen Kasten angezeigt, zusammen mit Beispielbefehlen. Kopieren Sie es sofort mit **Kopieren** und bewahren Sie es sicher auf, zum Beispiel im Geheimnisspeicher des Werkzeugs, das es verwendet. PhonixPBX speichert nur einen Hash und kann das Token nicht erneut anzeigen; geht es verloren, erstellen Sie ein neues.

> Anrufe über ein Token mit *Darf Anrufe tätigen* können Kosten verursachen, wenn sie zu externen Nummern gehen. Vergeben Sie die Berechtigung nur an Werkzeuge, die sie brauchen.

## Tokens verwalten {#manage}

Die Tabelle listet alle Tokens:

| Spalte | Inhalt |
|---|---|
| Name | Der Name und darunter die ersten Zeichen des Tokens, die es kennzeichnen, ohne es preiszugeben. |
| Zugriff | *nur lesen* oder *lesen/schreiben*, und *Anrufe*, wenn das Token Anrufe tätigen darf. |
| Status | *aktiv*, *deaktiviert* oder *abgelaufen*. |
| Besitzer | Der Administrator, der das Token erstellt hat. Wird der Administrator gelöscht, wird auch das Token gelöscht. |
| Erstellt, Zuletzt verwendet, Gültig bis | Wann das Token erstellt und zuletzt verwendet wurde und bis wann es gültig ist (*unbegrenzt* ohne Ablauf). |

Das Suchfeld über der Liste findet Tokens nach Name, Präfix oder Besitzer; wie Suchen und Blättern funktionieren, steht unter [Listen]({{< relref "/getting-started/_index.md#lists" >}}).

Mit dem Schalter deaktivieren Sie ein Token vorübergehend und aktivieren es wieder. Mit dem Papierkorbsymbol löschen Sie es endgültig. Löschen Sie nicht mehr verwendete Tokens; die Spalte *Zuletzt verwendet* hilft, sie zu finden.

Bewährte Praxis:

- Ein Token pro Werkzeug oder Skript, damit Sie eines widerrufen können, ohne die anderen zu beeinträchtigen.
- Nur lesen, wann immer das Werkzeug nur lesen muss, z. B. beim Monitoring.
- Ein Ablaufdatum für Tokens, die Dritte erhalten oder die nur zeitweise gebraucht werden.

## Ein Token verwenden {#using}

Senden Sie das Token bei jeder Anfrage im Header `Authorization`:

```sh
curl -H "Authorization: Bearer phx_..." https://pbx.example.com/api/v1/status
```

KI-Assistenten und andere MCP-Clients verbinden sich mit demselben Header mit `https://<Ihre TK-Anlage>/api/mcp`, zum Beispiel:

```sh
claude mcp add --transport http phonix https://pbx.example.com/api/mcp --header "Authorization: Bearer phx_..."
```

Die interaktive API-Dokumentation finden Sie unter `/api/docs` auf Ihrer TK-Anlage. Endpunkte, MCP-Werkzeuge und Beispiele beschreibt die [API-Referenz]({{< relref "/reference/api.md" >}}). Auf der Kommandozeile verwalten Sie Tokens mit `phonix token` (siehe [CLI]({{< relref "/reference/cli.md" >}})).
