---
title: "Benachrichtigungen"
weight: 10
description: "Der Postausgangsserver (SMTP) für Mailbox- und Anrufbenachrichtigungen und eine Testnachricht."
---
Unter *Dienste → Benachrichtigungen* richten Sie den Mailserver ein, über den PhonixPBX E-Mails verschickt. Die TK-Anlage stellt E-Mails nicht selbst zu, sondern übergibt jede Nachricht an einen SMTP-Server, typischerweise den Ihres E-Mail-Anbieters oder Ihren Firmen-Mailserver. Mailbox-Nachrichten per E-Mail und Benachrichtigungen über verpasste Anrufe funktionieren erst, wenn diese Seite ausgefüllt ist.

Klicken Sie auf **Speichern** und übernehmen Sie anschließend die Änderungen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}). Welche E-Mails ein Telefon erhält, legen Sie pro Telefon unter [Konten → Telefone]({{< relref "/accounts/phones.md#edit" >}}) im Reiter *Mailbox & Benachrichtigungen* fest; die Texte der E-Mails unter [Dienste → Mailbox]({{< relref "/services/voicemail.md#texts" >}}).

## Postausgangsserver (SMTP) {#smtp}

| Feld | Bedeutung | Standard |
|---|---|---|
| SMTP-Server | Hostname oder IP-Adresse des Mailservers, z. B. `smtp.example.com`. E-Mails werden nur verschickt, wenn dieses Feld und die *Absenderadresse* ausgefüllt sind. | leer |
| Port | TCP-Port des Mailservers, 1–65535. Verwenden Sie den Port, der zur Verschlüsselung passt. | `587` |
| Verschlüsselung | **STARTTLS (Port 587)**: unverschlüsselte Verbindung, die auf TLS umgeschaltet wird (Submission). **TLS / SMTPS (Port 465)**: TLS von Anfang an. **keine (Port 25)**: unverschlüsselt, nur für ein Relay im eigenen Netzwerk. | STARTTLS (Port 587) |
| Absenderadresse | Die `From`-Adresse der E-Mails, z. B. `pbx@example.com`. Viele Mailserver akzeptieren nur eine Absenderadresse, die zum Konto gehört. | leer |
| Server erfordert Authentifizierung | Mit dem Benutzernamen und Passwort unten am Mailserver anmelden. | ein |
| Benutzername | Anmeldename am Mailserver. Nur mit Authentifizierung sichtbar. | leer |
| Passwort | Passwort für die Anmeldung. Das gespeicherte Passwort wird nie angezeigt; lassen Sie das Feld leer, um es beizubehalten. Nur mit Authentifizierung sichtbar. | leer |
| Serverzertifikat überprüfen | Das TLS-Zertifikat des Mailservers prüfen. Schalten Sie das nur bei einem internen Server mit selbstsigniertem Zertifikat aus. | ein |

> Manche Anbieter (zum Beispiel Gmail oder Microsoft 365) akzeptieren für SMTP nicht das normale Kontopasswort. Erstellen Sie in den Kontoeinstellungen des Anbieters ein App-Passwort oder SMTP-spezifische Zugangsdaten.

## Testnachricht senden {#test}

Geben Sie unter **Empfänger** eine Adresse ein und klicken Sie auf **Test senden**. PhonixPBX verschickt eine kurze Nachricht mit dem Betreff „PhonixPBX test message“ und zeigt an, ob der Mailserver sie angenommen hat, oder die Fehlermeldung des Mailprogramms.

Der Test verwendet die *übernommene* Konfiguration, nicht die Werte im Formular. Speichern und übernehmen Sie geänderte Einstellungen zuerst und senden Sie dann den Test.

Häufige Fehler:

- **Authentifizierung fehlgeschlagen**: Benutzername oder Passwort sind falsch, oder der Anbieter verlangt ein App-Passwort.
- **Verbindung abgelehnt oder Zeitüberschreitung**: falscher Host oder Port, oder das Netzwerk sperrt ausgehendes SMTP. Viele Internetanbieter sperren Port 25.
- **Zertifikatsfehler**: Der Hostname passt nicht zum Zertifikat des Servers, oder der Server verwendet ein selbstsigniertes Zertifikat. Verwenden Sie genau den Hostnamen aus dem Zertifikat oder schalten Sie *Serverzertifikat überprüfen* aus.
