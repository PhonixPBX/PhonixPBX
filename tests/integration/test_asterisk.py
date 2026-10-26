# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests against a real Asterisk 22 (run inside the dev container as root).

    dev/test-asterisk.sh            # builds/uses phonix-dev:3.24 and runs these

The tests generate the configuration through the normal apply path, start
Asterisk with it and use SIPp to register phones and place calls.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
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
                specials=[{"name": "Emergency", "feature_code": "*32", "dest_type": "hangup"}],
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


def db_value(family: str, key: int) -> str | None:
    out = cli(f"database get {family} {key}")
    return out.split("Value:", 1)[1].strip() if "Value:" in out else None


def hint_state(code: str) -> str:
    match = re.search(r"State:(\w+)", cli(f"core show hint {code}"))
    return match[1] if match else ""


def wait_until(check: Callable[[], bool], what: str, timeout: float = 10) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


def press(code: str) -> None:
    """Dial a feature code like a phone key and wait until the call is gone."""
    since = console_size()
    cli(f"channel originate Local/{code}@internal application Wait 1")
    wait_for(f"{code}@internal", since)
    wait_until(lambda: "Local/" + code not in cli("core show channels concise"), f"the {code} call to end")


def test_business_hours_mode_and_feature_code(pbx: Path) -> None:
    today = dt.date.today().isoformat()
    with db.session_scope() as session:
        office = hours.list_hours(session)[0]
        hid = office.id
        assert hours.get_mode(hid) == "auto"
        # open around the clock: calls go to the menu
        since = console_size()
        cli(f"channel originate Local/s@hours-{hid} application Wait 1")
        wait_for("Goto (ivr-1,s,1)", since)
        # the key sets a temporary override to the opposite of the automatic state, lamp lit
        press("*31")
        assert db_value("phonix-hours-tmp", hid) == f"closed:{today}"
        assert db_value("phonix-hours", hid) is None
        wait_until(lambda: hint_state("*31") == "InUse", "the out-of-office lamp")
        status = hours.live_status(session, hid)
        assert (status["open"], status["reason"]) == (False, "override")
        since = console_size()
        cli(f"channel originate Local/s@hours-{hid} application Wait 1")
        wait_for("closed-override-0", since)
        # pressing again removes it: back to automatic, lamp dark
        press("*31")
        assert db_value("phonix-hours-tmp", hid) is None
        wait_until(lambda: hint_state("*31") == "Idle", "the lamp to go dark")
        # a permanent mode equal to the automatic state: removed, and an override inverts the lamp
        hours.set_mode(session, hid, "open")
        assert db_value("phonix-hours", hid) == "open"
        assert hint_state("*31") == "Idle"
        press("*31")
        assert db_value("phonix-hours", hid) is None
        assert db_value("phonix-hours-tmp", hid) == f"closed:{today}"
        wait_until(lambda: hint_state("*31") == "InUse", "the out-of-office lamp")
        # a permanent mode replaces the override
        hours.set_mode(session, hid, "auto")
        assert hours.get_mode(hid) == "auto"
        assert db_value("phonix-hours-tmp", hid) is None
        wait_until(lambda: hint_state("*31") == "Idle", "the lamp to go dark")

        # a special period's key switches it on: its lamp and the out-of-office lamp are lit
        special = office.specials[0]
        assert db_value("phonix-special", special.id) is None
        press("*32")
        assert db_value("phonix-special", special.id) == "1"
        wait_until(lambda: hint_state("*32") == "InUse", "the special period lamp")
        wait_until(lambda: hint_state("*31") == "InUse", "the out-of-office lamp")
        since = console_size()
        cli(f"channel originate Local/s@hours-{hid} application Wait 1")
        wait_for("Special period Emergency", since)
        status = hours.live_status(session, hid)
        assert (status["open"], status["reason"], status["special_id"]) == (False, "special", special.id)
        # and off again
        press("*32")
        assert db_value("phonix-special", special.id) == "0"
        wait_until(lambda: hint_state("*32") == "Idle", "the special period lamp to go dark")
        wait_until(lambda: hint_state("*31") == "Idle", "the out-of-office lamp to go dark")


def test_special_period_parity(pbx: Path) -> None:
    """Dated and yearly periods and one leading to other business hours: dialplan and Python agree."""
    today = dt.date.today()
    day = dt.timedelta(days=1)
    with db.session_scope() as session:
        menu = ivr.list_menus(session)[0]
        late = hours.create_hours(
            session,
            hours.BusinessHoursIn(
                name="Late shift",
                open_dest_type="ivr",
                open_dest_id=menu.id,
                closed_dest_type="hangup",
                ranges=[{"weekday": d, "start": "00:00", "end": "24:00"} for d in range(7)],
            ),
        )
        shop = hours.create_hours(
            session,
            hours.BusinessHoursIn(
                name="Shop",
                open_dest_type="hangup",
                closed_dest_type="hangup",
                specials=[
                    # last year only: never applies
                    {
                        "name": "Old",
                        "start": today - 400 * day,
                        "end": today - 370 * day,
                        "dest_type": "hangup",
                    },
                    # every year, but not today
                    {
                        "name": "Soon",
                        "start": today + 2 * day,
                        "end": today + 3 * day,
                        "yearly": True,
                        "dest_type": "hangup",
                    },
                    # every year across the new year (from today to yesterday), to other business hours
                    {
                        "name": "Season",
                        "start": today,
                        "end": today - day,
                        "yearly": True,
                        "dest_type": "hours",
                        "dest_id": late.id,
                    },
                ],
            ),
        )
        result = apply.apply(session)
        assert result.ok, result.errors
        sid, old, soon, season = shop.id, *(sp.id for sp in shop.specials)
        assert [hours.special_matches(sp, today) for sp in shop.specials] == [False, False, True]

        def routed(expected: str) -> None:
            since = console_size()
            cli(f"channel originate Local/s@hours-{sid} application Wait 1")
            wait_for(f"Business hours Shop: {expected}", since)

        # everything off: closed by the (empty) weekly hours
        routed("closed-auto-0")
        status = hours.live_status(session, sid)
        assert (status["open"], status["reason"]) == (False, "schedule")

        # all on: the old and the future period do not apply, the season leads to the open late shift
        for key in (old, soon, season):
            cli(f"database put phonix-special {key} 1")
        routed(f"open-auto-{season}")
        status = hours.live_status(session, sid)
        assert (status["open"], status["reason"], status["special_id"]) == (True, "special", season)
        since = console_size()
        cli(f"channel originate Local/s@hours-{sid} application Wait 1")
        wait_for(f"Goto (hours-{late.id},s,1)", since)

        # the late shift closed for good: the season follows it
        hours.set_mode(session, late.id, "closed")
        routed(f"closed-auto-{season}")
        status = hours.live_status(session, sid)
        assert (status["open"], status["reason"], status["special_id"]) == (False, "special", season)

        # as after a restore: modes are cleared and the switches written as configured
        hours.reset_runtime(session)
        assert db_value("phonix-hours", late.id) is None
        assert [db_value("phonix-special", key) for key in (old, soon, season)] == ["0", "0", "0"]
        routed("closed-auto-0")


def test_record_announcement_by_phone(pbx: Path) -> None:
    """phonix-record end to end: record, end with #, listen, 1 saves; then it becomes a media file."""
    from phonix.services import media, recording

    # the layout of phonix-firstboot: media is setgid with group asterisk, incoming inherits the group
    media_dir = config.get().media_dir
    media_dir.mkdir(exist_ok=True)
    sh("chgrp", "asterisk", str(media_dir))
    sh("chmod", "2750", str(media_dir))
    incoming = recording.incoming_dir()
    token = "0123456789abcdef0123456789abcdef"
    meta = {"kind": "ivr_prompt", "name": "Recorded", "user": "test", "started": time.time()}
    (config.get().state_dir / "recordings").mkdir(parents=True, exist_ok=True)
    (config.get().state_dir / "recordings" / f"{token}.json").write_text(__import__("json").dumps(meta))
    # the other side of the Local channel is "the phone": wait, # ends the recording, 1 saves it
    # while vm-review plays (w = 0.5 s)
    with ami.AmiClient() as client:
        resp = client.action(
            "Originate",
            Channel="Local/s@phonix-record",
            Application="SendDTMF",
            Data="wwww#" + "w" * 10 + "1",
            Variable=f"PHX_REC={token}",
            Async="true",
        )
    assert resp.get("Response") == "Success", resp
    wait_until(lambda: db_value("phonix-rec", token) == "saved", "the recording to be saved", timeout=30)  # type: ignore[arg-type]
    # SendDTMF sends no audio: the WAV is only a header, but it is there and readable for the web user's group
    wav = incoming / f"{token}.wav"
    assert wav.stat().st_size >= 44 and wav.stat().st_mode & 0o040
    with db.session_scope() as session:
        status = recording.poll(session, token)
        assert status.state == "saved" and status.media is not None, status
        assert media.media_path(status.media).exists()
    assert not wav.exists()
