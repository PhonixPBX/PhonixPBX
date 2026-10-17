---
title: "Certificate"
weight: 60
description: "The TLS certificate of the web interface and SIP over TLS: self-signed, uploaded, or from Let's Encrypt/ACME."
---
*Advanced → Certificate* manages the TLS certificate that the web interface (HTTPS) and SIP over TLS use. There are three ways to get one:

- a **self-signed certificate**, created automatically on first boot;
- an **uploaded certificate** from your own or a commercial CA;
- an **automatic certificate** from an ACME CA such as Let's Encrypt, renewed by PhonixPBX.

Changes on this page take effect immediately, without applying: the web server reloads the certificate, and Asterisk is restarted to load it once no call is active if SIP over TLS is in use.

## Current certificate {#current}

The card shows the certificate in use: **Subject**, **Names** (the DNS names it is valid for), **Issuer** (with the badge *self-signed* for a self-signed certificate), **Valid until** and the SHA-256 fingerprint. You can compare the fingerprint with the one your browser shows to make sure you are connected to your PBX.

## Self-signed certificate {#self-signed}

On first boot PhonixPBX creates a self-signed certificate for `<hostname>.<domain>` from [System → General Setup]({{< relref "/system/general.md#name" >}}). Browsers warn about such a certificate because no trusted CA has signed it; the connection is still encrypted.

**Create new self-signed certificate** replaces the current certificate with a new self-signed one, for example after changing the host name. This also turns off automatic certificates.

## Upload a certificate {#upload}

| Field | Meaning |
|---|---|
| Certificate (PEM, may include the chain) | The certificate in PEM format (`.pem`, `.crt`, `.cer`). Put intermediate certificates after the server certificate in the same file. |
| Private key (PEM, unencrypted) | The matching private key in PEM format (`.pem`, `.key`), without a passphrase. |

Click **Install**. PhonixPBX checks that the files are valid PEM and that the key matches the certificate, then installs them. Installing a certificate turns off automatic certificates. Each file may be up to 1 MB.

## Automatic certificate (ACME) {#acme}

PhonixPBX can obtain a certificate from an ACME CA with the `lego` client and renew it automatically. The card at the bottom of the page shows the result of the last request; while a request is running the status updates by itself.

| Field | Meaning | Default |
|---|---|---|
| Obtain and renew the certificate automatically | Turn automatic certificates on. | off |
| Certificate authority | **Let's Encrypt**; **Let's Encrypt staging (testing, untrusted)** for trying out the setup without hitting rate limits; **ZeroSSL**; or **Other ACME server**. | Let's Encrypt |
| ACME directory URL | Directory URL of the ACME server, must start with `https://`. Only with *Other ACME server*. | empty |
| EAB key ID, EAB HMAC key | External account binding. Required by ZeroSSL (from the ZeroSSL dashboard) and by some private CAs. The stored HMAC key is not shown; leave it empty to keep it. | empty |
| Account e-mail address | Contact address of the ACME account; the CA sends notices about expiring certificates there. Required. | empty |
| Domain names | The names the certificate is issued for, one per line. Must be public, fully qualified DNS names; wildcards (`*.example.com`) need DNS validation. Empty: `<hostname>.<domain>`. | empty |
| Validation | How the CA checks that you control the names: **HTTP (port 80)** or **DNS provider API**. | HTTP (port 80) |

**Save** stores the settings. **Save and request certificate now** stores them and starts a request at once. The request runs in the background; when it succeeds, the page reloads and shows the new certificate. If it fails, the error is shown, and **lego output** contains the full log of the client.

> Try a new setup with *Let's Encrypt staging* first: its certificates are not trusted by browsers, but its rate limits are much higher. Switch to *Let's Encrypt* once the request works.

### HTTP validation {#http-01}

The CA connects to `http://<name>/.well-known/acme-challenge/` for every name. This requires that:

- every name resolves in public DNS to the PBX, or to a router that forwards TCP port 80 to it;
- port 80 is reachable from the internet;
- *Networks allowed to manage the PBX* under [Advanced → Firewall]({{< relref "/advanced/firewall.md#networks" >}}) is empty. If it is restricted, the page shows a warning; use DNS validation instead.

### DNS validation {#dns-01}

The CA checks a TXT record that `lego` creates through the API of your DNS provider. This works for PBXs that are not reachable from the internet and is required for wildcard names.

| Field | Meaning |
|---|---|
| DNS provider | The provider that hosts the DNS zone of your domain. Built in are Azure DNS, Cloudflare, deSEC, DigitalOcean, DuckDNS, Gandi LiveDNS, GoDaddy, Hetzner, Hurricane Electric, Infomaniak, INWX, IONOS, Linode / Akamai, Namecheap, netcup, OVH, Porkbun, RFC 2136 dynamic update (BIND, Knot, ...) and Amazon Route 53. After choosing one, the page shows its credential fields. |
| Credential fields | API token, key or similar, depending on the provider. Fields marked *(optional)* may stay empty. Stored secrets are not shown; leave a field empty to keep it. |
| lego provider code | With *Other lego provider ...*: the code of any provider supported by lego, e.g. `powerdns`. See the lego DNS provider list. |
| Credentials | With *Other lego provider ...*: the environment variables for that provider, `NAME=value` per line, as documented by lego. Stored values are not shown; write `NAME=` to keep a stored value. |
| DNS resolvers for the propagation check (optional) | DNS servers that `lego` asks to check whether the TXT record is visible, e.g. `1.1.1.1:53`. Useful when the PBX resolves its own domain through an internal DNS server. |

> Give the API credentials as few rights as possible, for example a Cloudflare token limited to editing DNS of one zone.

## Renewal {#renewal}

Once automatic certificates are enabled, a daily job checks the certificate and requests a new one when it expires in less than 30 days, when the domain names were changed, or when a self-signed certificate is installed. A renewed certificate is installed and loaded automatically.

Uploading a certificate or creating a self-signed one turns automatic certificates off. Turn them on again to go back to ACME.

The certificate, its key and the ACME account are part of the [backup]({{< relref "/system/backup.md" >}}).
