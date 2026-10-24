---
title: "Audit-Log"
weight: 50
description: "Wer hat was wann geändert: jede Konfigurationsänderung und jede administrative Aktion."
---
*Status → Audit-Log* hält jede Änderung an der Konfiguration und jede administrative Aktion fest, mit Zeitpunkt und dem Administrator, der sie ausgeführt hat. So finden Sie heraus, wann eine Einstellung geändert wurde, von wem und welchen Wert sie vorher hatte.

## Spalten {#columns}

| Spalte | Bedeutung |
|---|---|
| Zeit (UTC) | Zeitpunkt der Aktion, in UTC, unabhängig von der Zeitzone der Anlage. |
| Benutzer | Wer es war: der Name eines Administrators. API-Anfragen erscheinen unter dem Besitzer des Tokens, MCP-Anfragen als `<name> (mcp)`. Aktionen über die Kommandozeile erscheinen als `cli`, über das Konsolenmenü als `console` und die Ersteinrichtung als `setup` bzw. `firstboot`. |
| Aktion | Was getan wurde, zum Beispiel `create`, `update`, `delete`, `enable`, `disable`, `apply`, `backup`, `restore`, `password`, `certificate`, `firmware`, `originate` (ein über die API ausgelöster Anruf) oder `legacy-import`. |
| Objekt | Art und Name des betroffenen Objekts, zum Beispiel ein Telefon mit seiner Nummer, ein Provider oder eine Gruppe von Einstellungen. |
| Details | Bei Änderungen: die geänderten Felder als `Feld: alt → neu`. Passwörter, PINs und andere Geheimnisse werden nie angezeigt; für sie steht nur *(geändert)*. |

## Blättern {#paging}

Die neuesten Einträge stehen oben, 50 pro Seite. Mit *Älter* und *Neuer* unter der Liste blättern Sie durch die Historie.

## Was aufgezeichnet wird {#recorded}

- Anlegen, Ändern, Aktivieren, Deaktivieren und Löschen von Telefonen, Providern, Rufgruppen, Anwendungen, IVR-Menüs, Geschäftszeiten, Konferenzräumen, Mediendateien und Manager-Benutzern.
- Änderungen auf Einstellungsseiten, über die Weboberfläche, die API oder MCP.
- Das Umschalten des Modus von Geschäftszeiten und das Ein- und Ausschalten von Sonderzeiträumen.
- Übernehmen der Konfiguration, Backups und Wiederherstellungen, Importe, Firmware-Updates, Zertifikate, Zurücksetzen auf Werkseinstellungen.
- Administratoren und API-Tokens: angelegt, gelöscht, Passwort und Sprache geändert.
- Über die API oder MCP ausgelöste Anrufe (Click-to-Call).

Anmeldungen werden im Audit-Log nicht festgehalten. Das Audit-Log bleibt auf der Anlage; es ist nicht Teil von Backups.
