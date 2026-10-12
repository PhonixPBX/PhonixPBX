"""SHA-512 crypt ("$6$", Ulrich Drepper's SHA-crypt) for /etc/shadow.

The ``crypt`` module is gone since Python 3.13; this is the reference
algorithm, used for the root password that SSH (dropbear) checks.
"""

from __future__ import annotations

import hashlib
import re
import secrets

_B64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ROUNDS_DEFAULT = 5000
ROUNDS = 50000
HASH_RE = re.compile(r"^\$6\$(rounds=[0-9]{4,9}\$)?[./0-9A-Za-z]{1,16}\$[./0-9A-Za-z]{86}$")

# byte order of the final encoding (groups of three bytes)
_ORDER = [(k * 22 % 63, (k * 22 + 21) % 63, (k * 22 + 42) % 63) for k in range(21)]


def _b64(b2: int, b1: int, b0: int, n: int) -> str:
    w = (b2 << 16) | (b1 << 8) | b0
    out = []
    for _ in range(n):
        out.append(_B64[w & 0x3F])
        w >>= 6
    return "".join(out)


def _repeat(digest: bytes, length: int) -> bytes:
    return digest * (length // 64) + digest[: length % 64]


def sha512_crypt(password: str, salt: str | None = None, rounds: int = ROUNDS) -> str:
    key = password.encode()
    salt = (salt if salt is not None else "".join(secrets.choice(_B64) for _ in range(16)))[:16]
    rounds = min(max(rounds, 1000), 999_999_999)
    s = salt.encode()

    b = hashlib.sha512(key + s + key).digest()
    a = hashlib.sha512(key + s + _repeat(b, len(key)))
    n = len(key)
    while n:
        a.update(b if n & 1 else key)
        n >>= 1
    da = a.digest()

    p = _repeat(hashlib.sha512(key * len(key)).digest(), len(key))
    st = _repeat(hashlib.sha512(s * (16 + da[0])).digest(), len(s))

    c = da
    for i in range(rounds):
        h = hashlib.sha512(p if i & 1 else c)
        if i % 3:
            h.update(st)
        if i % 7:
            h.update(p)
        h.update(c if i & 1 else p)
        c = h.digest()

    enc = "".join(_b64(c[x], c[y], c[z], 4) for x, y, z in _ORDER) + _b64(0, 0, c[63], 2)
    prefix = "$6$" if rounds == ROUNDS_DEFAULT else f"$6$rounds={rounds}$"
    return f"{prefix}{salt}${enc}"
