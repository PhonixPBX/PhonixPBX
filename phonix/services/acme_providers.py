"""DNS providers offered in the ACME form, with the lego environment variables they need.

Variable names follow lego 4.35 (``providers/dns/<code>/<code>.toml``). Any other
lego provider can be used with "other" and free-form ``NAME=value`` lines.
"""

from __future__ import annotations

from dataclasses import dataclass

from phonix.i18n import N_, _


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
            Field("AZURE_CLIENT_ID", N_("Client ID")),
            Field("AZURE_CLIENT_SECRET", N_("Client secret"), secret=True),
            Field("AZURE_TENANT_ID", N_("Tenant ID")),
            Field("AZURE_SUBSCRIPTION_ID", N_("Subscription ID"), required=False),
            Field("AZURE_RESOURCE_GROUP", N_("Resource group"), required=False),
        ),
    ),
    DnsProvider(
        "cloudflare",
        "Cloudflare",
        (Field("CF_DNS_API_TOKEN", N_("API token (Zone.DNS edit)"), secret=True),),
    ),
    DnsProvider("desec", "deSEC", (Field("DESEC_TOKEN", N_("Token"), secret=True),)),
    DnsProvider("digitalocean", "DigitalOcean", (Field("DO_AUTH_TOKEN", N_("API token"), secret=True),)),
    DnsProvider("duckdns", "DuckDNS", (Field("DUCKDNS_TOKEN", N_("Token"), secret=True),)),
    DnsProvider(
        "gandiv5", "Gandi LiveDNS", (Field("GANDIV5_PERSONAL_ACCESS_TOKEN", N_("Personal access token"), secret=True),)
    ),
    DnsProvider(
        "godaddy",
        "GoDaddy",
        (Field("GODADDY_API_KEY", N_("API key")), Field("GODADDY_API_SECRET", N_("API secret"), secret=True)),
    ),
    DnsProvider("hetzner", "Hetzner", (Field("HETZNER_API_TOKEN", N_("Cloud API token"), secret=True),)),
    DnsProvider(
        "hurricane",
        "Hurricane Electric",
        (Field("HURRICANE_TOKENS", N_("Tokens (domain:token, comma separated)"), secret=True),),
    ),
    DnsProvider("infomaniak", "Infomaniak", (Field("INFOMANIAK_ACCESS_TOKEN", N_("Access token"), secret=True),)),
    DnsProvider(
        "inwx",
        "INWX",
        (
            Field("INWX_USERNAME", N_("Username")),
            Field("INWX_PASSWORD", N_("Password"), secret=True),
            Field("INWX_SHARED_SECRET", N_("2FA shared secret"), secret=True, required=False),
        ),
    ),
    DnsProvider("ionos", "IONOS", (Field("IONOS_API_KEY", N_("API key (prefix.secret)"), secret=True),)),
    DnsProvider("linode", "Linode / Akamai", (Field("LINODE_TOKEN", N_("API token"), secret=True),)),
    DnsProvider(
        "namecheap",
        "Namecheap",
        (Field("NAMECHEAP_API_USER", N_("API user")), Field("NAMECHEAP_API_KEY", N_("API key"), secret=True)),
    ),
    DnsProvider(
        "netcup",
        "netcup",
        (
            Field("NETCUP_CUSTOMER_NUMBER", N_("Customer number")),
            Field("NETCUP_API_KEY", N_("API key"), secret=True),
            Field("NETCUP_API_PASSWORD", N_("API password"), secret=True),
        ),
    ),
    DnsProvider(
        "ovh",
        "OVH",
        (
            Field("OVH_ENDPOINT", N_("Endpoint (ovh-eu, ovh-ca, ...)"), required=False),
            Field("OVH_APPLICATION_KEY", N_("Application key")),
            Field("OVH_APPLICATION_SECRET", N_("Application secret"), secret=True),
            Field("OVH_CONSUMER_KEY", N_("Consumer key"), secret=True),
        ),
    ),
    DnsProvider(
        "porkbun",
        "Porkbun",
        (Field("PORKBUN_API_KEY", N_("API key")), Field("PORKBUN_SECRET_API_KEY", N_("Secret API key"), secret=True)),
    ),
    DnsProvider(
        "rfc2136",
        N_("RFC 2136 dynamic update (BIND, Knot, ...)"),
        (
            Field("DNSUPDATE_NAMESERVER", N_("Name server (host or host:port)")),
            Field("DNSUPDATE_TSIG_KEY", N_("TSIG key name"), required=False),
            Field("DNSUPDATE_TSIG_SECRET", N_("TSIG secret"), secret=True, required=False),
            Field("DNSUPDATE_TSIG_ALGORITHM", N_("TSIG algorithm (e.g. hmac-sha256.)"), required=False),
        ),
    ),
    DnsProvider(
        "route53",
        "Amazon Route 53",
        (
            Field("AWS_ACCESS_KEY_ID", N_("Access key ID")),
            Field("AWS_SECRET_ACCESS_KEY", N_("Secret access key"), secret=True),
            Field("AWS_REGION", N_("Region")),
            Field("AWS_HOSTED_ZONE_ID", N_("Hosted zone ID"), required=False),
        ),
    ),
)

BY_CODE = {p.code: p for p in PROVIDERS}


def get(code: str) -> DnsProvider | None:
    return BY_CODE.get(code)


def choices() -> list[tuple[str, str]]:
    return [(p.code, p.label) for p in PROVIDERS] + [(OTHER, _("Other lego provider ..."))]


def missing(code: str, env: dict[str, str]) -> list[str]:
    """Labels of required fields without a value (translated)."""
    provider = get(code)
    if provider is None:
        return []
    return [_(f.label) for f in provider.fields if f.required and not env.get(f.env)]
