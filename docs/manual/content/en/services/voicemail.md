---
title: "Voicemail"
weight: 20
description: "Voicemail-to-e-mail, missed call e-mails and their texts per language."
---
*Services → Voicemail* sets how voicemail messages are recorded and delivered by e-mail, and the texts of the voicemail and missed call e-mails. Voicemail itself is switched on per phone under [Accounts → Phones]({{< relref "/accounts/phones.md#edit" >}}) on the *Voicemail & notifications* tab, where you also enter the e-mail addresses. Phone users listen to their messages by dialing `000086`, see [Voicemail for phone users]({{< relref "/phone-users/_index.md#voicemail" >}}).

E-mails need a configured mail server under [Services → Notifications]({{< relref "/services/email.md" >}}). As long as there is none, the page shows a notice and messages stay in the mailbox on the PBX.

Changes on this page become active after you apply them, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}).

## Voicemail settings {#settings}

| Field | Meaning | Default |
|---|---|---|
| Sender address | `From` address of the voicemail e-mails. Empty: the sender address from *Services → Notifications*. | empty |
| Sender name | Display name of the sender. | `PhonixPBX Voicemail` |
| Max. message length (s) | Longest message a caller can record, 10–3600 seconds. | `180` |
| Attach the recording to the e-mail | Attach the recording as a WAV file. Without it the e-mail only announces the message. | on |
| Keep messages on the PBX after e-mailing | Keep a message in the mailbox after it was e-mailed, so it can still be played back by phone. When off, a message is deleted once it was sent to a phone's e-mail address; phones without an e-mail address always keep their messages. | on |

The greeting that callers hear before the beep can be replaced by your own recording under [Services → Media]({{< relref "/services/media.md#greeting" >}}).

## Who receives which e-mail {#recipients}

Per phone, on the *Voicemail & notifications* tab:

- **Send voicemail to e-mail**: every new voicemail message is sent to this address.
- **E-mail notification on missed calls** with a **Notification address**: an e-mail is sent for each call to the phone that was not answered, with the caller and the reason (busy, no answer, not reachable, or the caller hung up).
- **E-mail language**: the language of both e-mails. Empty means the language of the phone.

## E-mail texts {#texts}

The voicemail and missed call e-mails have built-in texts that are translated into every language of the web interface. You can replace them per language:

1. Choose the **Language** above the texts. The page shows the texts currently used for this language.
2. Edit **E-mail subject** and **E-mail text** under *New voicemail* and *Missed call*.
3. Click **Save**, then apply the changes.

A section that differs from the built-in text is marked *customised*. A text identical to the built-in one is not stored, so it keeps following future translation updates. **Reset to default** removes all custom texts of the selected language. A subject may have up to 200 characters, a text up to 4000; control characters are not allowed.

The texts of one language only affect phones whose e-mail language is that language. If you customise the texts, do so for every language your users have.

## Placeholders {#placeholders}

Write placeholders as `${NAME}`; they are replaced when the e-mail is sent. The help text below each text field lists the available names.

| Placeholder | Content |
|---|---|
| `${VM_NAME}` | Name of the mailbox owner (the caller ID name of the phone) |
| `${VM_MAILBOX}` | Mailbox number (the extension) |
| `${VM_MSGNUM}` | Number of the message in the mailbox |
| `${VM_DUR}` | Length of the message, e.g. `0:42` |
| `${VM_CALLERID}` | Caller, e.g. `"Bob" <0441234567>` |
| `${VM_DATE}` | Date and time of the message, formatted for the language |

The `VM_` placeholders are for the voicemail e-mail. The missed call e-mail uses:

| Placeholder | Content |
|---|---|
| `${NAME}` | Name of the called phone |
| `${EXTENSION}` | Called extension |
| `${CALLERID}` | Caller |
| `${REASON}` | Why the call was missed: busy, no answer, not reachable or the caller hung up |
| `${DATE}` | Date and time of the call, formatted for the language |

## Preview {#preview}

The *Preview* card at the bottom shows both e-mails of the selected language, filled in with sample values. It reflects the saved texts, so save before checking the result.
