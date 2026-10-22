---
title: "REST-API und MCP"
weight: 20
description: "Die Anlage automatisieren: Bearer-Tokens, die REST-API unter /api/v1, Click-to-Call, AskoziaPBX-Import, Prometheus-Metriken und der MCP-Server."
---
PhonixPBX lässt sich von Skripten und anderen Programmen steuern. Die **REST-API** unter `/api/v1` bietet dieselben Funktionen wie die Weboberfläche und folgt denselben Regeln für Prüfung, Geheimnisse und ausstehende Änderungen. Der **MCP-Server** unter `/api/mcp` stellt dieselben Funktionen KI-Assistenten zur Verfügung. Beide erreichen Sie per HTTPS unter der Adresse der Weboberfläche.

## Interaktive Dokumentation {#docs}

- `https://<anlage>/api/docs` – Swagger UI mit allen Endpunkten, ihren Parametern und Antwortformaten. Dort können Sie Anfragen ausprobieren: Klicken Sie auf *Authorize* und geben Sie ein Token ein. Die Fußzeile der Weboberfläche verlinkt hierher (*API*).
- `https://<anlage>/api/v1/openapi.json` – das OpenAPI-Schema, etwa um einen Client zu erzeugen.

## API-Tokens {#tokens}

Skripte melden sich mit einem **Bearer-Token** an. Tokens erstellen Sie unter [Erweitert → API-Tokens]({{< relref "/advanced/tokens.md" >}}) oder mit [`phonix token create`]({{< relref "/reference/cli.md#token" >}}). Ein Token beginnt mit `phx_` und wird nur einmal angezeigt, beim Erstellen; die Anlage speichert nur einen Hash davon.

| Eigenschaft | Bedeutung |
|---|---|
| Zugriff *Nur lesen* | Nur GET-Anfragen und nur die lesenden MCP-Werkzeuge. Mailbox- und Konferenz-PINs fehlen in den Antworten. |
| Zugriff *Lesen und Schreiben* | Alle Anfragen: anlegen, ändern, löschen, übernehmen. |
| *Darf Anrufe tätigen* | Erlaubt Click-to-Call (`POST /api/v1/calls`, MCP-Werkzeug `originate_call`), unabhängig vom Zugriff: Ein Nur-Lese-Token mit dieser Option kann Anrufe auslösen, aber die Konfiguration nicht ändern. Standardmäßig aus – Anrufe zu externen Nummern können Geld kosten. |
| Läuft ab in (Tagen) | Gültigkeit; leer bedeutet, dass das Token nie abläuft. |

Ein Token handelt mit den Rechten des Administrators, dem es gehört; seine Änderungen erscheinen unter diesem Namen im [Audit-Log]({{< relref "/status/audit.md" >}}). Deaktivierte und abgelaufene Tokens werden abgewiesen. Wiederholte Anfragen mit falschen Tokens werden – wie fehlgeschlagene Anmeldungen – für einige Minuten gesperrt.

Senden Sie das Token im Header `Authorization`:

```sh
curl -H "Authorization: Bearer phx_..." https://pbx.example.com/api/v1/status
```

Solange die Anlage ihr selbstsigniertes Zertifikat verwendet, ergänzen Sie bei `curl` die Option `-k` – oder installieren Sie besser ein richtiges Zertifikat.

## Objekte {#resources}

Jede Objektart hat dieselben fünf Endpunkte:

| Pfad | Objekte |
|---|---|
| `/api/v1/phones` | Telefone |
| `/api/v1/providers` | Provider |
| `/api/v1/callgroups` | Rufgruppen |
| `/api/v1/conferences` | Konferenzräume |
| `/api/v1/applications` | Wählplan-Anwendungen |
| `/api/v1/ivr-menus` | IVR-Menüs |
| `/api/v1/business-hours` | Geschäftszeiten |
| `/api/v1/ami-users` | Asterisk-Manager-Benutzer |

- `GET <pfad>` listet alle Objekte, `GET <pfad>/{id}` liefert eines.
- `POST <pfad>` legt ein Objekt an (Antwort `201`).
- `PUT <pfad>/{id}` ersetzt ein Objekt: Senden Sie alle Felder, wie beim Anlegen.
- `DELETE <pfad>/{id}` löscht es (Antwort `204`).

Passwörter und andere Geheimnisse werden nie zurückgegeben. Senden Sie ein leeres Geheimnis, bleibt der gespeicherte Wert unverändert.

Rufgruppen führen ihre Mitglieder in `members`, in der Klingelreihenfolge: `"phone:<id>"` für ein Telefon, `"callgroup:<id>"` für eine enthaltene Rufgruppe, zum Beispiel `{"name": "Support", "members": ["callgroup:2", "phone:5"]}`. Eine Gruppe, die sich selbst enthalten würde, wird mit `422` abgelehnt. Das ältere Feld `member_ids` (nur Telefon-IDs) wird weiterhin geliefert und angenommen.

## Einstellungen {#settings}

`GET /api/v1/settings/{group}` liefert eine Gruppe von Einstellungen, `PATCH /api/v1/settings/{group}` ändert nur die gesendeten Felder. Die Gruppen heißen `system`, `network`, `rtp`, `sip`, `iax`, `voicemail`, `email`, `features`, `media`, `firewall`, `acme`, `gui` und `update`.

## Änderungen übernehmen {#apply}

Änderungen über die API werden – wie in der Weboberfläche – zu ausstehenden Änderungen:

- `GET /api/v1/pending` listet die Bereiche mit noch nicht übernommenen Änderungen.
- `POST /api/v1/apply` übernimmt sie und liefert die geänderten Dateien, die neu geladenen Komponenten und gegebenenfalls Fehler.

## Geschäftszeiten {#business-hours}

- `GET /api/v1/business-hours/{id}/status` – ob gerade geöffnet ist, und der aktuelle Modus.
- `PUT /api/v1/business-hours/{id}/mode` mit `{"mode": "auto"}`, `"open"` oder `"closed"` – schaltet den Modus sofort um, ohne Übernehmen.

## Click-to-Call {#calls}

`POST /api/v1/calls` mit `{"extension": "21", "number": "0441234567"}` lässt das SIP- oder IAX-Telefon mit dieser Nummer klingeln. Sobald dort abgehoben wird, wählt die Anlage die Rufnummer von diesem Telefon aus, mit dessen eigenen Regeln für ausgehende Anrufe und dessen Rufnummer. Die Antwort ist `202` mit `"status": "ringing"`. Die Rufnummer darf Ziffern, `*`, `#` und `+` enthalten. Das Token braucht *Darf Anrufe tätigen*.

```sh
curl -H "Authorization: Bearer phx_..." -H "Content-Type: application/json" \
     -d '{"extension": "21", "number": "0441234567"}' https://pbx.example.com/api/v1/calls
```

## AskoziaPBX-config.xml {#legacy}

- `POST /api/v1/legacy/import` importiert eine AskoziaPBX-`config.xml`, die als Body der Anfrage gesendet wird (höchstens 10 MB). Standardmäßig (`dry_run=true`) liefert der Endpunkt nur die Vorschau; mit `dry_run=false` wird importiert. `mode=replace` (Standard, vorher wird ein Backup erstellt) oder `mode=merge` wählt den [Modus]({{< relref "/reference/askozia.md#modes" >}}). Die Antwort ist der Importbericht als JSON (`ok`, `dry_run`, `mode`, `source_version`, `counts`, `dropped_sections`, `items`, `summary`); `422`, wenn die Datei Fehler enthält – dann wird nichts importiert. Übernehmen Sie die Änderungen anschließend.
- `GET /api/v1/legacy/export` liefert die Konfiguration als `config.xml` (`application/xml`). Die Datei enthält alle Passwörter im Klartext; Nur-Lese-Tokens erhalten deshalb `403`, obwohl es eine GET-Anfrage ist. Jeder Export wird im Audit-Log festgehalten.

```sh
curl -k -H "Authorization: Bearer phx_..." --data-binary @config.xml \
     "https://pbx.example.com/api/v1/legacy/import?dry_run=false&mode=merge"
```

## Status und Prometheus-Metriken {#metrics}

- `GET /api/v1/status` liefert Systeminformationen und den Asterisk-Zustand (Registrierungen, Kanäle) als JSON.
- `GET /api/v1/metrics` liefert Metriken im Prometheus-Textformat; jedes gültige Token funktioniert, empfohlen ist ein Nur-Lese-Token.

Die Metriken umfassen das System (Betriebszeit, Last, Arbeitsspeicher, Datenpartition, Netzwerkverkehr), Asterisk (läuft, Startzeit, aktive Gespräche und Kanäle), die Registrierung jedes Telefons (`phonix_phone_registered`) und Providers (`phonix_provider_up`), Mailbox-Nachrichten pro Mailbox, den Ablauf des TLS-Zertifikats und die letzte ACME-Anfrage, ausstehende Änderungen und Backups. Ein Scrape-Job:

```yaml
scrape_configs:
  - job_name: phonix
    scheme: https
    metrics_path: /api/v1/metrics
    authorization:
      credentials: phx_...            # Nur-Lese-API-Token
    tls_config:
      insecure_skip_verify: true      # nur solange die Anlage ihr selbstsigniertes Zertifikat verwendet
    static_configs:
      - targets: ["pbx.example.com"]
```

Sinnvolle Alarme: `phonix_provider_up == 0`, `phonix_asterisk_up == 0`, `phonix_tls_certificate_expiry_seconds - time() < 14 * 86400`.

## Fehler {#errors}

| Status | Bedeutung |
|---|---|
| `401` | Kein Token, oder das Token ist ungültig, deaktiviert oder abgelaufen. |
| `403` | Das Token darf nur lesen (gilt auch für den `config.xml`-Export) bzw. keine Anrufe tätigen. |
| `404` | Das Objekt existiert nicht. |
| `422` | Ungültige Eingabe. Der Body enthält `detail.message` und pro Feld `detail.fields`. |
| `429` | Zu viele fehlgeschlagene Anmeldeversuche; warten Sie einige Minuten. |

Fehlermeldungen der API sind immer englisch.

## MCP für KI-Assistenten {#mcp}

`POST /api/mcp` ist ein Server für das Model Context Protocol (MCP, Transport „streamable HTTP“). Darüber kann ein KI-Assistent wie Claude in Ihrem Auftrag die Konfiguration der Anlage lesen und ändern. Er akzeptiert nur Bearer-Tokens. Beispiel für Claude Code:

```sh
claude mcp add --transport http phonix https://pbx.example.com/api/mcp \
  --header "Authorization: Bearer phx_..."
```

Die Werkzeuge:

- `list_*`, `get_*`, `create_*`, `update_*` und `delete_*` für Telefone, Provider, Rufgruppen, Konferenzräume, Anwendungen, IVR-Menüs, Geschäftszeiten und AMI-Benutzer. `update_*` ändert nur die angegebenen Felder.
- `set_phone_enabled`, `set_provider_enabled`, `set_ivr_menu_enabled`.
- `get_business_hours_status`, `set_business_hours_mode` (wirkt sofort).
- `list_settings_groups`, `get_settings`, `update_settings`.
- `get_status`, `get_pending_changes`, `preview_apply` (welche Dateien und Komponenten sich ändern würden), `apply_changes`.
- `tail_log` – die letzten Zeilen des Logs `asterisk`, `system`, `web` oder `monitor` (bis zu 1000). In einem OCI-Container gibt es keine Logdateien, und das Werkzeug meldet einen Fehler.
- `originate_call` – Click-to-Call; nur für Tokens mit *Darf Anrufe tätigen* verfügbar.

Ein Nur-Lese-Token sieht nur die lesenden Werkzeuge. Geheimnisse werden nie zurückgegeben. Änderungen erscheinen im Audit-Log als `<name> (mcp)`. Geben Sie einem Assistenten nur den Zugriff, den er braucht – für Fragen zur Konfiguration oder die Auswertung von Logs reicht ein Nur-Lese-Token.
