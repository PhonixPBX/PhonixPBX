"""DNS providers offered in the ACME form, with the lego environment variables they need.

Variable names follow lego 4.35 (``providers/dns/<code>/<code>.toml``). Any other
lego provider can be used with "other" and free-form ``NAME=value`` lines.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    env: str
    label: str
    secret: bool = False
    required: bool = True


@dataclass(frozen=True)
class DnsProvider:
    code: str
    label: str
    fields: tuple[Field, ...]


OTHER = "other"

PROVIDERS: tuple[DnsProvider, ...] = (
    DnsProvider(
        "azuredns",
        "Azure DNS",
        (
            Field("AZURE_CLIENT_ID", "Client ID"),
            Field("AZURE_CLIENT_SECRET", "Client secret", secret=True),
            Field("AZURE_TENANT_ID", "Tenant ID"),
            Field("AZURE_SUBSCRIPTION_ID", "Subscription ID", required=False),
            Field("AZURE_RESOURCE_GROUP", "Resource group", required=False),
        ),
    ),
    DnsProvider(
        "cloudflare",
        "Cloudflare",
        (Field("CF_DNS_API_TOKEN", "API token (Zone.DNS edit)", secret=True),),
    ),
    DnsProvider("desec", "deSEC", (Field("DESEC_TOKEN", "Token", secret=True),)),
    DnsProvider("digitalocean", "DigitalOcean", (Field("DO_AUTH_TOKEN", "API token", secret=True),)),
    DnsProvider("duckdns", "DuckDNS", (Field("DUCKDNS_TOKEN", "Token", secret=True),)),
    DnsProvider(
        "gandiv5", "Gandi LiveDNS", (Field("GANDIV5_PERSONAL_ACCESS_TOKEN", "Personal access token", secret=True),)
    ),
    DnsProvider(
        "godaddy",
        "GoDaddy",
        (Field("GODADDY_API_KEY", "API key"), Field("GODADDY_API_SECRET", "API secret", secret=True)),
    ),
    DnsProvider("hetzner", "Hetzner", (Field("HETZNER_API_TOKEN", "Cloud API token", secret=True),)),
    DnsProvider(
        "hurricane",
        "Hurricane Electric",
        (Field("HURRICANE_TOKENS", "Tokens (domain:token, comma separated)", secret=True),),
    ),
    DnsProvider("infomaniak", "Infomaniak", (Field("INFOMANIAK_ACCESS_TOKEN", "Access token", secret=True),)),
    DnsProvider(
        "inwx",
        "INWX",
        (
            Field("INWX_USERNAME", "Username"),
            Field("INWX_PASSWORD", "Password", secret=True),
            Field("INWX_SHARED_SECRET", "2FA shared secret", secret=True, required=False),
        ),
    ),
    DnsProvider("ionos", "IONOS", (Field("IONOS_API_KEY", "API key (prefix.secret)", secret=True),)),
    DnsProvider("linode", "Linode / Akamai", (Field("LINODE_TOKEN", "API token", secret=True),)),
    DnsProvider(
        "namecheap",
        "Namecheap",
        (Field("NAMECHEAP_API_USER", "API user"), Field("NAMECHEAP_API_KEY", "API key", secret=True)),
    ),
    DnsProvider(
        "netcup",
        "netcup",
        (
            Field("NETCUP_CUSTOMER_NUMBER", "Customer number"),
            Field("NETCUP_API_KEY", "API key", secret=True),
            Field("NETCUP_API_PASSWORD", "API password", secret=True),
        ),
    ),
    DnsProvider(
        "ovh",
        "OVH",
        (
            Field("OVH_ENDPOINT", "Endpoint (ovh-eu, ovh-ca, ...)", required=False),
            Field("OVH_APPLICATION_KEY", "Application key"),
            Field("OVH_APPLICATION_SECRET", "Application secret", secret=True),
            Field("OVH_CONSUMER_KEY", "Consumer key", secret=True),
        ),
    ),
    DnsProvider(
        "porkbun",
        "Porkbun",
        (Field("PORKBUN_API_KEY", "API key"), Field("PORKBUN_SECRET_API_KEY", "Secret API key", secret=True)),
    ),
    DnsProvider(
        "rfc2136",
        "RFC 2136 dynamic update (BIND, Knot, ...)",
        (
            Field("DNSUPDATE_NAMESERVER", "Name server (host or host:port)"),
            Field("DNSUPDATE_TSIG_KEY", "TSIG key name", required=False),
            Field("DNSUPDATE_TSIG_SECRET", "TSIG secret", secret=True, required=False),
            Field("DNSUPDATE_TSIG_ALGORITHM", "TSIG algorithm (e.g. hmac-sha256.)", required=False),
        ),
    ),
    DnsProvider(
        "route53",
        "Amazon Route 53",
        (
            Field("AWS_ACCESS_KEY_ID", "Access key ID"),
            Field("AWS_SECRET_ACCESS_KEY", "Secret access key", secret=True),
            Field("AWS_REGION", "Region"),
            Field("AWS_HOSTED_ZONE_ID", "Hosted zone ID", required=False),
        ),
    ),
)

BY_CODE = {p.code: p for p in PROVIDERS}


def get(code: str) -> DnsProvider | None:
    return BY_CODE.get(code)


def choices() -> list[tuple[str, str]]:
    return [(p.code, p.label) for p in PROVIDERS] + [(OTHER, "Other lego provider ...")]


def missing(code: str, env: dict[str, str]) -> list[str]:
    """Labels of required fields without a value."""
    provider = get(code)
    if provider is None:
        return []
    return [f.label for f in provider.fields if f.required and not env.get(f.env)]
