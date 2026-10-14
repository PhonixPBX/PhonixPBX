# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import base64
import datetime as dt
from email import policy
from email.parser import BytesParser

import pytest

from phonix import notify
from phonix.core import settings as st
from phonix.services import notifications
from phonix.services.common import ServiceError

WAV = b"RIFF$\x00\x00\x00WAVEfmt fake recording"

# what app_voicemail hands to the mailcmd with the voicemail.conf of PhonixPBX
ASTERISK_MAIL = (
    "Date: Sat, 14 Mar 2026 09:26:53 +0100\n"
    'From: "PhonixPBX Voicemail" <voicemail@phonix.local>\n'
    'To: "Alice" <alice@example.com>\n'
    "Subject: PHONIX-VM 101\n"
    "MIME-Version: 1.0\n"
    'Content-Type: multipart/mixed; boundary="----voicemail_1"\n'
    "\n"
    "This is a multi-part message in MIME format.\n"
    "\n"
    "------voicemail_1\n"
    "Content-Type: text/plain; charset=UTF-8\n"
    "Content-Transfer-Encoding: 8bit\n"
    "\n"
    "mailbox=101\n"
    "msgnum=1\n"
    "name=Alice\n"
    'callerid="Bob" <0441234567>\n'
    "dur=0:12\n"
    "date=2026-03-14T09:26:53+0100\n"
    "\n"
    "------voicemail_1\n"
    'Content-Type: audio/x-wav; name="msg0000.wav"\n'
    "Content-Transfer-Encoding: base64\n"
    'Content-Disposition: attachment; filename="msg0000.wav"\n'
    "\n" + base64.b64encode(WAV).decode() + "\n"
    "\n"
    "------voicemail_1--\n"
).encode()


def _config(lang="de", vm=None):
    vm = vm or st.VoicemailSettings()
    return {
        "targets": {
            "101": {"lang": lang, "name": "Alice", "extension": "101"},
            "group-3": {"lang": lang, "name": "Sales", "extension": "200"},
        },
        "languages": {lang: notifications.runtime_texts(vm, lang)},
    }


def test_voicemail_mail_in_the_mailbox_language():
    sent = []
    assert notify.voicemail(ASTERISK_MAIL, _config(), lambda data: sent.append(data) or 0) == 0
    msg = BytesParser(policy=policy.default).parsebytes(sent[0])
    assert msg["Subject"] == 'Neue Sprachnachricht von "Bob" <0441234567>'
    assert msg["To"].addresses[0].addr_spec == "alice@example.com"
    text, wav = list(msg.iter_parts())
    body = text.get_content()
    assert body.startswith("Hallo Alice,")
    assert "Nummer 1, Dauer 0:12" in body and "Mailbox 101" in body
    assert "14. März 2026" in body
    assert wav.get_filename() == "msg0000.wav" and wav.get_content() == WAV


def test_voicemail_override_and_unknown_mailbox():
    vm = st.VoicemailSettings(templates={"de": {"vm_subject": "VM ${VM_MAILBOX}: ${VM_UNKNOWN}"}})
    out = notify.rewrite_voicemail(ASTERISK_MAIL, _config(vm=vm))
    assert BytesParser(policy=policy.default).parsebytes(out)["Subject"] == "VM 101: ${VM_UNKNOWN}"
    # a mailbox without an entry gets the English built-in texts
    out = notify.rewrite_voicemail(ASTERISK_MAIL.replace(b"mailbox=101", b"mailbox=999"), _config())
    assert BytesParser(policy=policy.default).parsebytes(out)["Subject"] == 'New voicemail from "Bob" <0441234567>'


def test_voicemail_mail_that_cannot_be_rewritten_is_sent_unchanged():
    sent = []
    other = ASTERISK_MAIL.replace(b"Subject: PHONIX-VM 101", b"Subject: something else")
    notify.voicemail(other, _config(), sent.append)
    assert sent == [other]


def test_missed_call_mail():
    when = dt.datetime(2026, 3, 14, 9, 26, tzinfo=dt.timezone.utc)
    msg = notify.missed_call("alice@example.com", "101", "busy", '"Carol" <123>', _config(), now=when)
    assert msg["Subject"] == 'Verpasster Anruf von "Carol" <123>'
    assert msg["Auto-Submitted"] == "auto-generated"
    body = msg.get_content()
    assert "Anruf an 101 verpasst" in body and "Grund: Besetzt" in body and "März 2026" in body
    group = notify.missed_call("a@example.com", "group-3", "hung-up", "", _config("fr"), now=when)
    assert group["Subject"] == "Appel manqué de inconnu"
    assert "Motif : L'appelant a raccroché" in group.get_content()
    with pytest.raises(ValueError):
        notify.missed_call("not an address", "101", "busy", "", _config())
    # control characters in the caller id never reach the headers
    msg = notify.missed_call("a@example.com", "101", "busy", "Eve\r\nBcc: x@example.com", _config(), now=when)
    assert "Bcc" not in msg and "\n" not in msg["Subject"]


def test_save_texts_keeps_defaults_out(session):
    defaults = notifications.default_texts("de")
    notifications.save_texts(session, "de", {**defaults, "missed_subject": "Verpasst: ${CALLERID}"})
    vm = st.load(session, st.VoicemailSettings)
    assert vm.templates["de"].model_dump() == {
        "vm_subject": "",
        "vm_body": "",
        "missed_subject": "Verpasst: ${CALLERID}",
        "missed_body": "",
    }
    assert notifications.texts(vm, "de")["missed_subject"] == "Verpasst: ${CALLERID}"
    assert notifications.texts(vm, "de")["vm_subject"] == defaults["vm_subject"]
    with pytest.raises(ServiceError):
        notifications.save_texts(session, "de", {"vm_subject": "two\nlines"})
    notifications.reset_texts(session, "de")
    assert st.load(session, st.VoicemailSettings).templates == {}
    # only defaults: nothing is stored
    notifications.save_texts(session, "fr", notifications.default_texts("fr"))
    assert st.load(session, st.VoicemailSettings).templates == {}


def test_en_gb_uses_english_texts_and_british_dates():
    assert notifications.default_texts("en_GB") == notifications.default_texts("en")
    assert notify.format_date(dt.datetime(2026, 3, 14, 9, 26), "en_GB").startswith("Saturday, 14 March 2026")
