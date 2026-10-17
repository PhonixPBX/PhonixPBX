---
title: "Notifications"
weight: 10
description: "The outgoing mail server (SMTP) for voicemail and missed call e-mails, and a test message."
---
*Services → Notifications* configures the mail server that PhonixPBX uses to send e-mails. The PBX does not deliver mail itself: it hands every message to an SMTP server, typically the one of your mail provider or your company mail server. Voicemail-to-e-mail and missed call notifications only work once this page is filled in.

Click **Save** and then apply the changes, see [Applying changes]({{< relref "/getting-started/_index.md#apply" >}}). Which e-mails a phone receives is set per phone under [Accounts → Phones]({{< relref "/accounts/phones.md#edit" >}}) on the *Voicemail & notifications* tab; the texts of the e-mails are set under [Services → Voicemail]({{< relref "/services/voicemail.md#texts" >}}).

## Outgoing mail server (SMTP) {#smtp}

| Field | Meaning | Default |
|---|---|---|
| SMTP server | Host name or IP address of the mail server, e.g. `smtp.example.com`. E-mail is only sent when this field and *Sender address* are set. | empty |
| Port | TCP port of the mail server, 1–65535. Use the port that matches the encryption. | `587` |
| Encryption | **STARTTLS (port 587)**: plain connection that is upgraded to TLS (submission). **TLS / SMTPS (port 465)**: TLS from the start. **none (port 25)**: unencrypted, only for a relay in your own network. | STARTTLS (port 587) |
| Sender address | The `From` address of the e-mails, e.g. `pbx@example.com`. Many mail servers only accept a sender address that belongs to the account. | empty |
| Server requires authentication | Log in to the mail server with the user name and password below. | on |
| Username | Login name at the mail server. Only shown with authentication. | empty |
| Password | Password for the login. The stored password is never shown; leave the field empty to keep it. Only shown with authentication. | empty |
| Verify the server certificate | Check the TLS certificate of the mail server. Turn this off only for an internal server with a self-signed certificate. | on |

> Some providers (for example Gmail or Microsoft 365) do not accept the normal account password for SMTP. Create an app password or an SMTP-specific credential in the account settings of the provider.

## Send a test message {#test}

Enter an address under **Recipient** and click **Send test**. PhonixPBX sends a short message with the subject "PhonixPBX test message" and shows whether the mail server accepted it, or the error message of the mail client.

The test uses the *applied* configuration, not the values in the form. After changing the settings, save and apply them first, then send the test.

Common errors:

- **Authentication failed**: user name or password are wrong, or the provider requires an app password.
- **Connection refused or timeout**: wrong host or port, or the network blocks outgoing SMTP. Many internet providers block port 25.
- **Certificate errors**: the host name does not match the certificate of the server, or the server uses a self-signed certificate. Use the exact host name from the certificate, or turn off *Verify the server certificate*.
