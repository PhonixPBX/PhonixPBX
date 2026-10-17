---
title: "Provider"
weight: 20
description: "SIP- und IAX-Trunks: Registrierung, Wählmuster für ausgehende Anrufe, eingehende Routen, Anruferkennung und Ersatzprovider."
---
Ein Provider ist ein Konto bei einem VoIP-Anbieter oder ein SIP-Trunk, oder eine andere Telefonanlage, die über SIP oder IAX erreichbar ist. Über ihn laufen die Gespräche zwischen der Anlage und der Außenwelt. Provider verwalten Sie unter *Konten → Provider*.

Ausgehende Anrufe werden über die [Wählmuster](#dial-patterns) des Providers geleitet, eingehende über seine [eingehenden Routen](#incoming-routes). Änderungen werden wirksam, sobald Sie sie übernehmen, siehe [Änderungen übernehmen]({{< relref "/getting-started/_index.md#apply" >}}).

## Providerliste {#list}

Klicken Sie über der Liste auf **SIP-Provider** oder **IAX-Provider**, um einen Provider hinzuzufügen. Die Liste zeigt:

| Spalte | Bedeutung |
|---|---|
| Name | Ihr Name für den Provider. Ein Klick darauf öffnet ihn zum Bearbeiten. Deaktivierte Provider sind mit *deaktiviert* gekennzeichnet. |
| Typ | SIP oder IAX. |
| Host | Hostname oder Adresse, mit Port, falls einer gesetzt ist. |
| Benutzername | Der Benutzername des Kontos. |
| Wählmuster | Die Muster für ausgehende Anrufe, oder *keine* (dann wird der Provider für ausgehende Anrufe nicht verwendet). |
| Eingehend | Die Anzahl der eingehenden Routen. |

Mit den Schaltflächen am Ende jeder Zeile bearbeiten, deaktivieren/aktivieren und löschen Sie den Provider. Ein deaktivierter Provider registriert sich nicht und wird für keine Gespräche verwendet. Beim Löschen eines Providers werden auch die [externen Telefone]({{< relref "/accounts/phones.md#types" >}}) deaktiviert, die über ihn gewählt haben.

Ob ein Provider gerade registriert ist, sehen Sie unter [*Status → Gespräche & Registrierungen*]({{< relref "/status/calls.md" >}}).

## Provider anlegen oder bearbeiten {#edit}

Die benötigten Werte finden Sie in der Dokumentation oder im Kundenportal Ihres Providers: den Server (Host), Ihren Benutzernamen und Ihr Passwort, manchmal auch einen eigenen Authentifizierungsbenutzer oder eine vorgeschriebene *From*-Domain. Das Formular hat vier Reiter.

### Konto {#account}

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Ihr Name für den Provider, angezeigt in Listen und Auswahlfeldern. | – |
| Host | Hostname oder IP-Adresse des Servers des Providers, zum Beispiel `sip.provider.example`. | – |
| Port | Port des Servers. Leer verwendet den Standard: Bei SIP wird der Hostname zuerst per DNS-SRV aufgelöst, wenn unter [Erweitert → SIP]({{< relref "/advanced/sip.md#timers" >}}) *DNS-SRV-Abfragen verwenden* eingeschaltet ist, sonst 5060 (5061 bei TLS); 4569 für IAX. | leer |
| Transport | Nur SIP: UDP, TCP oder TLS. Mit TCP oder TLS wird dieser Transport auch auf der Anlage eingeschaltet. | UDP |
| Benutzername | Ihr Benutzername beim Provider. | – |
| Passwort | Das Passwort des Kontos. Beim Bearbeiten lassen Sie es leer, um das gespeicherte zu behalten. | – |
| Beim Provider registrieren | Die Anlage registriert sich beim Provider, damit eingehende Anrufe sie erreichen. Schalten Sie die Option bei Providern aus, die anhand der IP-Adresse authentifizieren. | an |
| Authentifizierungsbenutzer | Nur SIP. Nur nötig, wenn der Provider Ihnen einen Authentifizierungsnamen gibt, der sich vom Benutzernamen unterscheidet. | der Benutzername |
| From-Benutzer | Nur SIP. Der Benutzerteil des *From*-Headers ausgehender Anrufe. | der Benutzername |
| From-Domain | Nur SIP. Die Domain des *From*-Headers. | der Host |
| Authentifizierung | Nur IAX: MD5, Klartext oder RSA. | MD5 |

### Ausgehende Anrufe {#outgoing}

| Feld | Bedeutung | Standard |
|---|---|---|
| Wählmuster | Ein Muster pro Zeile. Wählt ein Telefon eine Nummer, die zu einem Muster passt, geht der Anruf über diesen Provider. Siehe [Wählmuster](#dial-patterns). | leer |
| Ersatzprovider | Ein anderer Provider, der den Anruf übernimmt, wenn dieser nicht erreichbar oder überlastet ist. Siehe [Ersatzprovider](#failover). | keiner |
| Ausgehende Anruferkennung | *Anruferkennung des Telefons verwenden* oder *feste Anruferkennung*. | Anruferkennung des Telefons verwenden |
| Feste Anruferkennung | Bei *feste Anruferkennung*: die Anruferkennung, die bei jedem Anruf über diesen Provider gesendet wird, zum Beispiel `Firma <4930123456>`. | – |

Ein Telefon kann die Anruferkennung pro Provider überschreiben und für einen Provider gesperrt werden, siehe [Ausgehende Anrufe]({{< relref "/accounts/phones.md#outgoing" >}}) in den Telefoneinstellungen. Viele Provider akzeptieren oder zeigen nur Anruferkennungen, die zu Ihrem Konto gehören.

### Eingehende Anrufe {#incoming}

| Feld | Bedeutung | Standard |
|---|---|---|
| Routen | Paare aus einem Muster für die angerufene Nummer und einem Ziel. Siehe [Eingehende Routen](#incoming-routes). | keine |
| Öffentliche Nummer | Ihre Hauptnummer bei diesem Provider. Nur zur Information. | leer |
| Eingehende Anruferkennung | Ändert die Anruferkennung eingehender Anrufe: *unverändert*, *Name durch Nummer ersetzen*, *durch Text ersetzen* oder *Text vor den Namen setzen* (zum Beispiel `Hotline`, um zu sehen, welche Leitung angerufen wurde). | unverändert |
| Text der Anruferkennung | Der Text für *durch Text ersetzen* und *Text vor den Namen setzen*. | – |

### Codecs & Erweitert {#advanced}

| Feld | Bedeutung | Standard |
|---|---|---|
| Codecs | Codecs, die dem Provider angeboten werden, in der Reihenfolge der Bevorzugung. Verwenden Sie, was der Provider unterstützt; G.711 (alaw in Europa, ulaw in Nordamerika) funktioniert fast überall. | alaw, ulaw, g722 |
| Sprache | Sprache der Ansagen, die Anrufer über diesen Provider hören. | Englisch |
| DTMF-Modus | *RFC 4733 (RFC 2833)*, *In-Band*, *SIP INFO* oder *Auto*. | RFC 4733 |
| Qualify-Intervall (s) | Wie oft die Anlage prüft, ob der Provider erreichbar ist (0–3600, 0 = aus). | 60 |
| Provider wird über NAT erreicht (symmetrisches RTP) | Sendet Audio an die Adresse zurück, von der es kam. | an |
| Zusätzliche Optionen | Für Fortgeschrittene: ein `key=value` pro Zeile, an den erzeugten Endpoint (SIP) bzw. Peer (IAX) angehängt. | leer |

## Wählmuster {#dial-patterns}

Ein Wählmuster legt fest, welche an einem Telefon gewählten Nummern die Anlage über diesen Provider verlassen und wie die Nummer vor dem Wählen verändert wird. Die Syntax lautet:

```
[voranzustellendes Präfix+][zu entfernendes Präfix|]Muster
```

Das Muster selbst verwendet die Musterzeichen von Asterisk:

| Zeichen | Passt auf |
|---|---|
| `0`–`9`, `*`, `#` | Genau dieses Zeichen |
| `X` | Eine beliebige Ziffer 0–9 |
| `Z` | Eine beliebige Ziffer 1–9 |
| `N` | Eine beliebige Ziffer 2–9 |
| `[1-5]`, `[13]` | Eine Ziffer aus dem Bereich bzw. der Liste |
| `.` | Ein oder mehrere weitere Zeichen |
| `!` | Null oder mehr weitere Zeichen |

Die Ziffern vor `|` gehören zum Muster, werden aber vor dem Wählen entfernt. Die Ziffern vor `+` werden der Nummer vorangestellt. `|` und `+` dürfen jeweils nur einmal vorkommen.

| Muster | Das Telefon wählt | An den Provider gesendet |
|---|---|---|
| `X.` | `0301234567` | `0301234567` (unverändert) |
| `0\|X.` | `0 0301234567` | `0301234567` (Amtsholung `0` entfernt) |
| `49+0\|X.` | `0301234567` | `49301234567` (führende `0` durch `49` ersetzt) |
| `112` | `112` | `112` (nur die Notrufnummer) |
| `0\|[1-9]XXX.` | `0 1701234567` | `1701234567` |
| `0\|00X.` | `0 0041441234567` | `0041441234567` (internationale Anrufe) |

Tipps:

- Üblich ist eine Amtsholung: `0|X.` beim Hauptprovider schickt alles, was mit `0` beginnt, dorthin.
- Passen mehrere Muster (eines oder mehrerer Provider) auf eine Nummer, gewinnt das spezifischste. So hat `0|00X.` für internationale Anrufe Vorrang vor `0|X.`.
- Dasselbe Muster kann nicht von zwei Providern verwendet werden; das Formular meldet, welcher Provider es bereits hat. Für einen Ausweichweg verwenden Sie stattdessen den [Ersatzprovider](#failover).
- Tragen Sie immer die Notrufnummern ein (zum Beispiel `112`, `110`), wenn sie an den Telefonen ohne Amtsholung gewählt werden.
- Muster dürfen nicht mit internen Nummern kollidieren, die intern bleiben sollen. Wählt ein Telefon, werden zuerst die internen Nummern geprüft.

## Eingehende Routen {#incoming-routes}

Eingehende Routen legen fest, wohin ein Anruf über diesen Provider geht, abhängig von der angerufenen Nummer (der Durchwahl bzw. DID). Mit **Route hinzufügen** fügen Sie eine Zeile mit Muster und Ziel hinzu:

| Muster | Passt auf |
|---|---|
| leer (*alle Nummern*) | Jeden eingehenden Anruf. Verwenden Sie es, wenn Sie nur eine Nummer haben, oder als Auffangroute. |
| `4930123456` | Genau diese Nummer. |
| `49301234XX` | Ein Muster mit denselben Zeichen wie bei Wählmustern (ohne `\|` und ohne `+`). |

Ziel kann ein Telefon, eine [Rufgruppe]({{< relref "/dialplan/callgroups.md" >}}), ein Konferenzraum, eine [Anwendung]({{< relref "/dialplan/applications.md" >}}), ein [IVR-Menü]({{< relref "/dialplan/ivr.md" >}}) oder [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}) sein, siehe [Ziele]({{< relref "/dialplan/ivr.md#destinations" >}}).

- Mehrere Routen mit demselben Muster und Telefonen als Ziel lassen diese Telefone gleichzeitig klingeln.
- Passt keine Route, wird die angerufene Nummer unter den Objekten gesucht, die *von außen erreichbar* sind (öffentliche Direktwahl): Stimmt sie mit der Nummer oder dem öffentlichen Namen eines solchen Telefons, einer Rufgruppe, Anwendung, eines Konferenzraums oder IVR-Menüs überein, geht der Anruf dorthin.
- Manche Provider senden statt der gewählten Nummer immer Ihren Kontobenutzernamen. Eine Route mit leerem Muster fängt auch diese Anrufe auf.

### Eingehende Nummer auf ein IVR-Menü leiten {#route-to-ivr}

1. Legen Sie das Menü unter [*Wählplan → IVR-Menüs*]({{< relref "/dialplan/ivr.md#edit" >}}) an.
2. Öffnen Sie den Provider, Reiter *Eingehende Anrufe*, und klicken Sie auf **Route hinzufügen**.
3. Geben Sie die Nummer ein (oder lassen Sie das Muster für alle Nummern leer) und wählen Sie das Menü als Ziel.
4. Speichern Sie und übernehmen Sie die Änderungen.

Soll außerhalb der Geschäftszeiten ein anderes Menü antworten, leiten Sie die Nummer stattdessen auf [Geschäftszeiten]({{< relref "/dialplan/hours.md" >}}), mit einem Menü als *Wenn geöffnet* und einem anderen als *Wenn geschlossen*.

## Ersatzprovider {#failover}

Scheitert ein Anruf über diesen Provider, weil der Provider nicht erreichbar oder überlastet ist, versucht die Anlage es über den **Ersatzprovider**. Der Ersatzprovider muss aktiviert sein und ein Wählmuster haben, das auf die gewählte Nummer passt; dabei gelten seine eigenen Musterregeln (Präfixe entfernen und voranstellen). Besetzt oder nicht angenommen wird nicht erneut versucht.

## Mehrere Konten bei einem Provider {#multiple-accounts}

Sie können mehrere SIP-Konten mit demselben Host anlegen, zum Beispiel eines pro Rufnummer. Die Anlage unterscheidet eingehende Anrufe anhand des Kontobenutzernamens, sodass für jedes Konto seine eigenen eingehenden Routen gelten.
