# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
import pytest

from phonix.core import validation as v


@pytest.mark.parametrize("pattern", ["0|X.", "49+0|1XX.", "00X.", "[2-9]XXXXXX", "_X.".lstrip("_"), "*21X"])
def test_valid_dialpatterns(pattern):
    assert v.dialpattern(pattern)


@pytest.mark.parametrize(
    "pattern,msg",
    [
        ("0|1|X.", "only one"),
        ("X.|0", "Wildcards"),
        ("[1[2]]", "Nested"),
        ("1]", "Unmatched"),
        ("a+X.", "invalid character"),
        ("4a+X.", "invalid character"),
        ("", "invalid"),
    ],
)
def test_invalid_dialpatterns(pattern, msg):
    with pytest.raises(ValueError, match=msg):
        v.dialpattern(pattern)


def test_parse_dialpattern():
    assert v.parse_dialpattern("49+0|1XX.") == ("01XX.", "49", 1)
    assert v.parse_dialpattern("00X.") == ("00X.", "", 0)


@pytest.mark.parametrize("value", ['Bob"', "Bob<", "a;b", "line\nbreak", ""])
def test_callerid_rejects_injection(value):
    with pytest.raises(ValueError):
        v.callerid_name(value)


def test_manual_attributes():
    assert v.manual_attributes("; comment\nrtp_timeout=30\n\n") == "rtp_timeout=30"
    for bad in ("[section]", "no equals sign", "x=1\n[general]"):
        with pytest.raises(ValueError):
            v.manual_attributes(bad)


def test_application_logic():
    assert v.application_logic("1,Answer()\nn,Hangup()\ninclude => other") == "1,Answer()\nn,Hangup()\ninclude => other"
    with pytest.raises(ValueError):
        v.application_logic("exten => 1,1,Answer()")
    with pytest.raises(ValueError):
        v.application_logic("")


def test_misc():
    assert v.network("192.168.1.7/24") == "192.168.1.0/24"
    assert v.extension_or_pattern("_0XX") == "0XX"
    with pytest.raises(ValueError):
        v.secret("has space")
    with pytest.raises(ValueError):
        v.codecs(["mp3"])
    assert v.codecs(["ALAW", "alaw", "g722"]) == ["alaw", "g722"]


def test_sha512_crypt_reference_vectors():
    from phonix.core.shacrypt import HASH_RE, sha512_crypt

    # test vectors from the SHA-crypt specification
    assert sha512_crypt("Hello world!", "saltstring", 5000) == (
        "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1"
    )
    assert sha512_crypt("Hello world!", "saltstringsaltstring", 10000) == (
        "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v."
    )
    assert HASH_RE.match(sha512_crypt("secret-pw"))


def test_ssh_password_hash_rejects_garbage():
    from pydantic import ValidationError

    from phonix.core import settings as st

    with pytest.raises(ValidationError):
        st.SystemSettings(ssh_password_hash="$6$x$abc\nroot::0:")
