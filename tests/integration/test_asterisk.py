# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests against a real Asterisk 22 (run inside the dev container as root).

    dev/test-asterisk.sh            # builds/uses phonix-dev:3.24 and runs these

The tests generate the configuration through the normal apply path, start
Asterisk with it and use SIPp to register phones and place calls.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from phonix import ami, config
from phonix.core import db
from phonix.services import apply, dialplan, hours, ivr, phones, setup

pytestmark = [
    pytest.mark.asterisk,
    pytest.mark.skipif(shutil.which("asterisk") is None or os.geteuid() != 0, reason="needs Asterisk and root"),
]

SIPP = Path(__file__).parent / "sipp"
HOST = "127.0.0.1"
PHONES = {"101": "Alice-secret-101", "102": "Bob-secret-102", "104": "Dave-secret-104"}


def sh(*cmd: str, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)


@pytest.fixture(autouse=True)
def runtime() -> Iterator[None]:
    """Override the per-test isolation of tests/conftest.py: one PBX for the module."""
    yield


@pytest.fixture(scope="module")
def pbx(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    # outside pytest's 0700 temp dirs: Asterisk runs as an unprivileged user
    base = Path("/srv/phonix-test")
    shutil.rmtree(base, ignore_errors=True)
    data = base / "data"
    data.mkdir(parents=True)
    # generate into a scratch root (the container's /etc/hostname etc. are bind
    # mounts) and link the Asterisk configuration into place
    root = base / "root"
    root.mkdir()
    os.environ.update(PHONIX_DATA_DIR=str(data), PHONIX_ROOT=str(root), PHONIX_PRIVILEGED="dry-run")
    config.reset_cache()
    db.dispose()
    setup.initialize()
    with db.session_scope() as session:
        for ext, secret in PHONES.items():
            phones.create_phone(
                session,
                phones.parse_phone(
                    {
                        "extension": ext,
                        "callerid": f"Phone {ext}",
                        "secret": secret,
                        "qualify": 0,
                        "nat": False,
                        "codecs": ["alaw", "ulaw"],
                    }
                ),
            )
        both = dialplan.create_callgroup(session, dialplan.CallGroupIn(name="Both", extension="300", member_ids=[1, 2]))
        dialplan.create_callgroup(
            session,
            dialplan.CallGroupIn(name="Nested", extension="301", members=[f"callgroup:{both.id}"], strategy="linear"),
        )
        menu = ivr.create_menu(
            session,
            ivr.IvrMenuIn(
                name="Main",
                extension="600",
                prompt_mode="sound",
                prompt_sound="beep",
                timeout=2,
                repeats=0,
                options=[
                    ivr.IvrOptionIn(key="1", label="Bob", dest_type="phone", dest_id=2),
                    ivr.IvrOptionIn(key="#", label="Again", dest_type="repeat"),
                ],
            ),
        )
        hours.create_hours(
            session,
            hours.BusinessHoursIn(
                name="Office",
                feature_code="*31",
                open_dest_type="ivr",
                open_dest_id=menu.id,
                closed_dest_type="hangup",
                ranges=[{"weekday": d, "start": "00:00", "end": "24:00"} for d in range(7)],
                holidays=[{"date": "2026-12-25", "name": "Christmas", "yearly": True}],
            ),
        )
        result = apply.apply(session, boot=True)
        assert result.ok
    shutil.rmtree("/etc/asterisk", ignore_errors=True)
    Path("/etc/asterisk").symlink_to(root / "etc/asterisk")
    for path in ("/var/lib/asterisk/keys", "/var/log/asterisk", "/var/run/asterisk", "/var/spool/asterisk"):
        Path(path).mkdir(parents=True, exist_ok=True)
    (data / "asterisk").mkdir(exist_ok=True)
    sh(
        "chown",
        "-R",
        "asterisk:asterisk",
        str(data / "asterisk"),
        "/var/log/asterisk",
        "/var/run/asterisk",
        "/var/spool/asterisk",
        str(root / "etc/asterisk"),
    )
    sh("chmod", "-R", "o+rX", str(root))
    sh("chmod", "755", str(data))
    logfile = (base / "asterisk-console.log").open("w")
    proc = subprocess.Popen(
        ["asterisk", "-U", "asterisk", "-G", "asterisk", "-f", "-vvv"],
        stdout=logfile,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(60):
        if sh("asterisk", "-rx", "core waitfullybooted", check=False, timeout=10).returncode == 0 and ami.is_running():
            break
        time.sleep(1)
    else:
        proc.kill()
        pytest.fail("Asterisk did not start: " + (base / "asterisk-console.log").read_text()[-3000:])
    yield data
    sh("asterisk", "-rx", "core stop now", check=False)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    logfile.close()
    output = (base / "asterisk-console.log").read_text()
    errors = [line for line in output.splitlines() if "ERROR" in line and "nameservers" not in line]
    Path("/tmp/asterisk-output.log").write_text(output)
    assert not errors, "Asterisk logged errors:\n" + "\n".join(errors[:30])


def cli(command: str) -> str:
    return ami.run_commands([command])[command]


def sipp(scenario: str, port: int, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return sh(
        "sipp",
        HOST,
        "-sf",
        str(SIPP / scenario),
        "-p",
        str(port),
        "-i",
        HOST,
        "-m",
        "1",
        "-timeout",
        f"{timeout}s",
        "-nostdin",
        "-nd",
        *args,
        timeout=timeout + 15,
        check=False,
    )


def register(ext: str, port: int) -> None:
    result = sipp("register.xml", port, "-s", ext, "-au", ext, "-ap", PHONES[ext])
    assert result.returncode == 0, result.stdout + result.stderr


def answer_call(port: int) -> subprocess.Popen[bytes]:
    """A SIPp UAS on ``port`` that answers one call (register the phone on that port first)."""
    callee = subprocess.Popen(
        [
            "sipp",
            HOST,
            "-sf",
            str(SIPP / "answer.xml"),
            "-p",
            str(port),
            "-i",
            HOST,
            "-m",
            "1",
            "-timeout",
            "30s",
            "-nostdin",
            "-nd",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(1)
    return callee


def finish(callee: subprocess.Popen[bytes]) -> bytes:
    try:
        return callee.communicate(timeout=30)[0]
    except subprocess.TimeoutExpired:
        callee.kill()
        return callee.communicate()[0]


def test_endpoints_loaded(pbx: Path) -> None:
    out = cli("pjsip show endpoints")
    assert "101/101" in out and "102/102" in out
    dp = cli("dialplan show internal")
    assert "'00003246'" in dp and "'2663'" in dp


def test_register_and_echo_call(pbx: Path) -> None:
    register("101", 5071)
    assert "sip:101@127.0.0.1:5071" in cli("pjsip show contacts")
    result = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "00003246")
    assert result.returncode == 0, result.stdout + result.stderr


def test_wrong_password_is_rejected(pbx: Path) -> None:
    result = sipp("register.xml", 5079, "-s", "101", "-au", "101", "-ap", "wrong")
    assert result.returncode != 0


def test_phone_to_phone_call(pbx: Path) -> None:
    register("102", 5072)
    callee = answer_call(5072)
    register("101", 5071)
    caller = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "102")
    callee_out = finish(callee)
    log = Path("/srv/phonix-test/asterisk-console.log").read_text()[-4000:]
    assert caller.returncode == 0, f"{caller.stdout[-1500:]}\nCALLEE:\n{callee_out[-2500:]!r}\nASTERISK:\n{log}"
    assert callee.returncode == 0


def test_conference_room(pbx: Path) -> None:
    register("101", 5071)
    result = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "2663")
    assert result.returncode == 0, result.stdout + result.stderr


def test_reload_after_change(pbx: Path) -> None:
    with db.session_scope() as session:
        phones.create_phone(
            session, phones.parse_phone({"extension": "103", "callerid": "New", "secret": "Secret-103"})
        )
        result = apply.apply(session)
    assert result.ok, result.errors
    assert "asterisk:pjsip" in result.components and "dialplan reload" in result.actions
    assert "103/103" in cli("pjsip show endpoints")
    assert "'103'" in cli("dialplan show 103@internal")


def console(since: int) -> str:
    """The Asterisk output since ``since``, without colours."""
    return re.sub(r"\x1b\[[0-9;]*m", "", Path("/srv/phonix-test/asterisk-console.log").read_text()[since:])


def console_size() -> int:
    return len(Path("/srv/phonix-test/asterisk-console.log").read_text())


def wait_for(text: str, since: int, timeout: float = 10) -> str:
    end = time.time() + timeout
    while time.time() < end:
        out = console(since)
        if text in out:
            return out
        time.sleep(0.3)
    raise AssertionError(f"{text!r} not in the Asterisk output:\n{console(since)[-3000:]}")


def test_ivr_and_hours_loaded(pbx: Path) -> None:
    out = cli("dialplan show ivr-1")
    for exten in ("'s'", "'1'", "'#'", "'i'", "'t'"):
        assert exten in out, out
    assert "'s'" in cli("dialplan show hours-1-pub")
    assert "'600'" in cli("dialplan show 600@internal")
    assert "'*31'" in cli("dialplan show *31@internal")


def test_nested_callgroup_loaded(pbx: Path) -> None:
    out = cli("dialplan show 301@internal")
    assert "PJSIP/101&PJSIP/102" in out, out


def test_nested_callgroup_call(pbx: Path) -> None:
    # 301 rings "Both" (101 and 102) as one step; 102 answers, 101 is not listening
    register("102", 5072)
    callee = answer_call(5072)
    register("104", 5074)
    since = console_size()
    caller = sipp("call.xml", 5074, "-au", "104", "-ap", PHONES["104"], "-key", "from", "104", "-key", "to", "301")
    callee_out = finish(callee)
    log = Path("/srv/phonix-test/asterisk-console.log").read_text()[since:]
    assert caller.returncode == 0, f"{caller.stdout[-1500:]}\nCALLEE:\n{callee_out[-2500:]!r}\nASTERISK:\n{log[-4000:]}"
    assert callee.returncode == 0
    assert "call group Nested" in log and "PJSIP/101&PJSIP/102" in log, log[-4000:]


def test_leading_plus_is_replaced(pbx: Path) -> None:
    # +41... becomes 0041... and runs through the phone's context again (no provider here: it ends there)
    since = console_size()
    cli("channel originate Local/+41441234567@phone-101 application Wait 1")
    wait_for('"phone-101,0041441234567,1"', since)


def test_ivr_call_is_answered(pbx: Path) -> None:
    register("101", 5071)
    since = console_size()
    result = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "600")
    assert result.returncode == 0, result.stdout + result.stderr
    out = wait_for("WaitExten", since)
    assert 'BackGround("PJSIP/101' in out and "IVR menu Main" in out


def test_ivr_keys_and_timeout(pbx: Path) -> None:
    # a key: the option's destination runs (Bob is not registered, the call ends)
    since = console_size()
    cli("channel originate Local/1@ivr-1 application Wait 1")
    wait_for("1@ivr-1:2", since)
    # no key: after the announcement and the wait the timeout path hangs up
    since = console_size()
    cli("channel originate Local/s@ivr-1 application Wait 8")
    out = wait_for("t@ivr-1:3", since, timeout=20)
    assert "Hangup" in out


def test_business_hours_mode_and_feature_code(pbx: Path) -> None:
    with db.session_scope() as session:
        office = hours.list_hours(session)[0]
        assert hours.get_mode(office.id) == "auto"
        # open around the clock: calls go to the menu
        since = console_size()
        cli(f"channel originate Local/s@hours-{office.id} application Wait 1")
        wait_for("Goto (ivr-1,s,1)", since)
        # the feature code closes, dialling it again switches back to automatic
        register("101", 5071)
        result = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "*31")
        assert result.returncode == 0, result.stdout + result.stderr
        assert hours.get_mode(office.id) == "closed"
        assert hours.live_status(session, office.id)["open"] is False
        result = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "*31")
        assert result.returncode == 0, result.stdout + result.stderr
        assert hours.get_mode(office.id) == "auto"
        hours.set_mode(session, office.id, "open")
        assert "open" in cli(f"database get phonix-hours {office.id}")
        hours.set_mode(session, office.id, "auto")
        assert hours.get_mode(office.id) == "auto"
