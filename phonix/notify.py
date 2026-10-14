# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""Voicemail and missed call e-mails in the language of the phone.

Runs as user ``asterisk`` (``/usr/libexec/phonix/notify``):

- ``notify voicemail``: Asterisk's ``mailcmd``. Asterisk composes the mail (with the
  recording attached); its subject and body only carry the message details as
  ``key=value`` lines (see ``voicemail.conf.j2``). They are replaced by the texts of the
  mailbox's language before the mail goes to msmtp. If that fails, the mail is sent as is.
- ``notify missed <email> <target> <cause> <callerid>``: called by the ``sub-missed-call``
  hangup handler.

The texts per language and the target (mailbox) languages come from the generated
``/etc/asterisk/phonix-notify.json``; nothing here touches the database. Keep the imports
light: this runs for every voicemail and missed call.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from phonix.i18n import N_

CONFIG = Path("/etc/asterisk/phonix-notify.json")
MSMTP = ["/usr/bin/msmtp", "-C", "/etc/phonix/msmtprc", "-t"]
VM_MARKER = "PHONIX-VM"

# built-in texts, translated through the catalogs (services.notifications); ${NAME}
# placeholders are filled in by render()
DEFAULTS = {
    "vm_subject": N_("New voicemail from ${VM_CALLERID}"),
    "vm_body": N_(
        "Hello ${VM_NAME},\n\n"
        "you have a new voicemail message (number ${VM_MSGNUM}, ${VM_DUR} long) in mailbox ${VM_MAILBOX} "
        "from ${VM_CALLERID}, received on ${VM_DATE}.\n\n"
        "-- \nPhonixPBX\n"
    ),
    "missed_subject": N_("Missed call from ${CALLERID}"),
    "missed_body": N_(
        "Hello ${NAME},\n\n"
        "you missed a call to ${EXTENSION}.\n\n"
        "Caller: ${CALLERID}\n"
        "Reason: ${REASON}\n"
        "Time: ${DATE}\n\n"
        "-- \nPhonixPBX\n"
    ),
}
VARIABLES = {
    "vm": ("VM_NAME", "VM_DUR", "VM_MSGNUM", "VM_MAILBOX", "VM_CALLERID", "VM_DATE"),
    "missed": ("NAME", "EXTENSION", "CALLERID", "REASON", "DATE"),
}
# MISSEDCAUSE values set by the dialplan (sub-dial)
REASONS = {
    "busy": N_("Busy"),
    "no-answer": N_("No answer"),
    "unavailable": N_("Not reachable"),
    "hung-up": N_("The caller hung up"),
}
UNKNOWN = N_("unknown")

_PLACEHOLDER = re.compile(r"\$\{([A-Z_]+)\}")
_ADDRESS = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def render(template: str, values: Mapping[str, str]) -> str:
    """Replace the known ``${NAME}`` placeholders; anything else stays as written."""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def clean(value: str, limit: int = 200) -> str:
    return _CONTROL.sub("", value)[:limit]


def format_date(when: dt.datetime, lang: str) -> str:
    """Full date and short time in the locale's own order, e.g. "Samstag, 14. März 2026 um 09:26"."""
    try:
        from babel import dates

        locale = lang or "en"
        pattern = str(dates.get_datetime_format("full", locale=locale))
        date = dates.format_date(when, "full", locale=locale)
        time = dates.format_time(when, "short", locale=locale)
        return pattern.replace("'", "").replace("{0}", time).replace("{1}", date)
    except Exception:  # unknown locale or no babel: still send the mail
        return when.strftime("%Y-%m-%d %H:%M")


def load_config(path: Path = CONFIG) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def language_texts(config: Mapping[str, Any], lang: str) -> dict[str, Any]:
    texts: dict[str, Any] = dict(DEFAULTS)
    texts["reasons"] = dict(REASONS)
    texts["unknown"] = UNKNOWN
    texts.update(config.get("languages", {}).get(lang, {}))
    return texts


def target(config: Mapping[str, Any], key: str) -> dict[str, str]:
    found = config.get("targets", {}).get(key, {})
    return found if isinstance(found, dict) else {}


# --- voicemail ------------------------------------------------------------------


def _fields(body: str) -> dict[str, str]:
    """``key=value`` lines of the marker body; the first occurrence of a key counts."""
    out: dict[str, str] = {}
    for line in body.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.isidentifier() and key not in out:
            out[key] = value.strip()
    return out


def _text_part(msg: EmailMessage) -> EmailMessage | None:
    if not msg.is_multipart():
        return msg if msg.get_content_type() == "text/plain" else None
    for part in msg.iter_parts():
        if part.get_content_type() == "text/plain" and not part.is_attachment():
            return part  # type: ignore[return-value]
    return None


def rewrite_voicemail(raw: bytes, config: Mapping[str, Any]) -> bytes:
    """The mail Asterisk built, with subject and text in the mailbox's language.

    Raises ``ValueError`` if it is not a PhonixPBX voicemail mail."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    if not str(msg.get("Subject", "")).startswith(VM_MARKER):
        raise ValueError("not a PhonixPBX voicemail mail")
    part = _text_part(msg)  # type: ignore[arg-type]
    if part is None:
        raise ValueError("no text part")
    fields = _fields(part.get_content())
    info = target(config, fields.get("mailbox", ""))
    lang = info.get("lang", "en")
    texts = language_texts(config, lang)
    try:
        when = dt.datetime.strptime(fields.get("date", ""), "%Y-%m-%dT%H:%M:%S%z")
        date = format_date(when, lang)
    except ValueError:
        date = fields.get("date", "")
    values = {
        "VM_NAME": fields.get("name", ""),
        "VM_DUR": fields.get("dur", ""),
        "VM_MSGNUM": fields.get("msgnum", ""),
        "VM_MAILBOX": fields.get("mailbox", ""),
        "VM_CALLERID": fields.get("callerid", "") or texts["unknown"],
        "VM_DATE": date,
    }
    del msg["Subject"]
    msg["Subject"] = clean(render(texts["vm_subject"], values), 250)
    part.set_content(render(texts["vm_body"], values), charset="utf-8")
    return msg.as_bytes()


def voicemail(raw: bytes, config: Mapping[str, Any], send: Callable[[bytes], int]) -> int:
    try:
        out = rewrite_voicemail(raw, config)
    except Exception as exc:  # never lose the message
        print(f"notify: voicemail mail sent unchanged: {exc}", file=sys.stderr)
        out = raw
    return send(out)


# --- missed calls ---------------------------------------------------------------


def missed_call(
    to: str, key: str, cause: str, callerid: str, config: Mapping[str, Any], now: dt.datetime | None = None
) -> EmailMessage:
    to, key, cause, callerid = clean(to), clean(key, 64), clean(cause, 32), clean(callerid)
    if not _ADDRESS.match(to):
        raise ValueError("invalid address")
    info = target(config, key)
    lang = info.get("lang", "en")
    texts = language_texts(config, lang)
    when = now or dt.datetime.now().astimezone()
    values = {
        "NAME": info.get("name", ""),
        "EXTENSION": info.get("extension", "") or info.get("name", ""),
        "CALLERID": callerid or texts["unknown"],
        "REASON": texts["reasons"].get(cause, cause),
        "DATE": format_date(when, lang),
    }
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = clean(render(texts["missed_subject"], values), 250)
    msg["Date"] = email.utils.format_datetime(when)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(render(texts["missed_body"], values), charset="utf-8")
    return msg


# --- command line ---------------------------------------------------------------


def _sendmail(data: bytes) -> int:
    return subprocess.run(MSMTP, input=data, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    config = load_config()
    if args == ["voicemail"]:
        return voicemail(sys.stdin.buffer.read(), config, _sendmail)
    if len(args) == 5 and args[0] == "missed":
        if not Path(MSMTP[2]).exists():
            print("notify: e-mail is not configured", file=sys.stderr)
            return 69
        try:
            msg = missed_call(args[1], args[2], args[3], args[4], config)
        except ValueError as exc:
            print(f"notify: {exc}", file=sys.stderr)
            return 65
        return _sendmail(msg.as_bytes())
    print("usage: notify voicemail | notify missed <email> <target> <cause> <callerid>", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
