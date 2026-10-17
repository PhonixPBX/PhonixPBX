---
title: "Administratoren"
weight: 70
description: "Benutzerkonten für die Weboberfläche."
---
Unter *Erweitert → Administratoren* verwalten Sie die Konten, die sich an der Weboberfläche anmelden können. Jeder Administrator hat vollen Zugriff; Rollen mit weniger Rechten gibt es nicht. Für Skripte und Integrationen erstellen Sie statt eines gemeinsam genutzten Administratorkontos ein [API-Token]({{< relref "/advanced/tokens.md" >}}).

Änderungen auf dieser Seite wirken sofort, ohne Übernehmen. Sie werden im [Audit-Log]({{< relref "/status/audit.md" >}}) mit dem Namen des Administrators protokolliert, der sie vorgenommen hat – ein guter Grund, jeder Person ein eigenes Konto zu geben.

## Administratorliste {#list}

Die Tabelle zeigt jeden Administrator mit dem Zeitpunkt der **Letzten Anmeldung**. Die Markierung *muss Passwort ändern* kennzeichnet Konten, die bei der nächsten Anmeldung ein neues Passwort festlegen müssen.

Mit dem Papierkorbsymbol löschen Sie einen Administrator. Ihr eigenes Konto können Sie nicht löschen, und der letzte Administrator kann nicht gelöscht werden. API-Tokens gehören dem Administrator, der sie erstellt hat, und werden mit seinem Konto gelöscht.

## Administrator hinzufügen {#add}

| Feld | Bedeutung | Standard |
|---|---|---|
| Benutzername | Anmeldename: beginnt mit einem Kleinbuchstaben, danach bis zu 31 Kleinbuchstaben, Ziffern, `.`, `_` oder `-`. Großbuchstaben werden in Kleinbuchstaben umgewandelt. | — |
| Initiales Passwort | Das erste Passwort, mindestens 8 Zeichen. | — |
| Muss das Passwort bei der ersten Anmeldung ändern | Der neue Administrator muss nach der ersten Anmeldung ein neues Passwort wählen, sodass nur er es kennt. | ein |

Klicken Sie auf **Hinzufügen**. Geben Sie das initiale Passwort auf einem sicheren Weg an den neuen Administrator weiter.

## Passwörter {#passwords}

Jeder Administrator ändert sein eigenes Passwort und die Sprache der Oberfläche in seinem Kontomenü, siehe [Passwort ändern]({{< relref "/getting-started/_index.md#password" >}}).

Die Weboberfläche kann das Passwort eines anderen Administrators nicht setzen. Hat jemand sein Passwort vergessen, löschen Sie das Konto und legen es neu an, oder setzen Sie auf der Kommandozeile mit `phonix user passwd <Name>` ein neues Passwort (siehe [CLI]({{< relref "/reference/cli.md" >}})).

Der Webserver begrenzt die Anzahl der Anmeldeversuche pro Adresse, um das Erraten von Passwörtern zu bremsen.
