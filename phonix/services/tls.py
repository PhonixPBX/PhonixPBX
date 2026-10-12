"""HTTPS / SIP-TLS certificate handling (self-signed on first boot, uploadable)."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from phonix import config
from phonix.i18n import _
from phonix.services.common import ServiceError


def _write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def generate_self_signed(hostname: str, ips: list[str] | None = None, days: int = 3650) -> None:
    cfg = config.get()
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PhonixPBX"),
        ]
    )
    alt: list[x509.GeneralName] = [x509.DNSName(hostname), x509.DNSName("localhost")]
    for ip in ips or []:
        alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write(
        cfg.tls_key_path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        0o640,
    )
    _write(cfg.tls_cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)


def ensure_certificate(hostname: str) -> bool:
    cfg = config.get()
    if cfg.tls_cert_path.exists() and cfg.tls_key_path.exists():
        return False
    generate_self_signed(hostname)
    return True


def current_certificate() -> x509.Certificate | None:
    try:
        return x509.load_pem_x509_certificate(config.get().tls_cert_path.read_bytes())
    except (FileNotFoundError, ValueError):
        return None


def dns_names(cert: x509.Certificate) -> list[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return []
    return san.get_values_for_type(x509.DNSName)


def certificate_info() -> dict[str, str] | None:
    cert = current_certificate()
    if cert is None:
        return None
    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "names": ", ".join(dns_names(cert)),
        "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
        "self_signed": str(cert.subject == cert.issuer),
        "sha256": cert.fingerprint(hashes.SHA256()).hex(":"),
    }


def install_certificate(cert_pem: bytes, key_pem: bytes) -> None:
    """Validate and install an uploaded certificate + matching private key."""
    try:
        certs = x509.load_pem_x509_certificates(cert_pem)
        key = serialization.load_pem_private_key(key_pem, password=None)
    except ValueError as exc:
        raise ServiceError(fields={"certificate": _("Invalid PEM data: %(error)s", error=exc)}) from exc
    if not certs:
        raise ServiceError(fields={"certificate": _("No certificate found")})
    pub = (
        certs[0].public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    if (
        key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        != pub
    ):
        raise ServiceError(fields={"private_key": _("Private key does not match the certificate")})
    cfg = config.get()
    _write(cfg.tls_key_path, key_pem, 0o640)
    _write(cfg.tls_cert_path, cert_pem, 0o644)
