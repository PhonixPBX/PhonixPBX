"""End-to-end tests against a real Asterisk 22 (run inside the dev container as root).

    dev/test-asterisk.sh            # builds/uses askozia-dev:3.24 and runs these

The tests generate the configuration through the normal apply path, start
Asterisk with it and use SIPp to register phones and place calls.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from askozia import ami, config
from askozia.core import db
from askozia.services import apply, dialplan, phones, setup

pytestmark = [
    pytest.mark.asterisk,
    pytest.mark.skipif(shutil.which("asterisk") is None or os.geteuid() != 0, reason="needs Asterisk and root"),
]

SIPP = Path(__file__).parent / "sipp"
HOST = "127.0.0.1"
PHONES = {"101": "Alice-secret-101", "102": "Bob-secret-102"}


def sh(*cmd: str, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)


@pytest.fixture(autouse=True)
def runtime() -> Iterator[None]:
    """Override the per-test isolation of tests/conftest.py: one PBX for the module."""
    yield


@pytest.fixture(scope="module")
def pbx(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    # outside pytest's 0700 temp dirs: Asterisk runs as an unprivileged user
    base = Path("/srv/askozia-test")
    shutil.rmtree(base, ignore_errors=True)
    data = base / "data"
    data.mkdir(parents=True)
    # generate into a scratch root (the container's /etc/hostname etc. are bind
    # mounts) and link the Asterisk configuration into place
    root = base / "root"
    root.mkdir()
    os.environ.update(ASKOZIA_DATA_DIR=str(data), ASKOZIA_ROOT=str(root), ASKOZIA_PRIVILEGED="dry-run")
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
        dialplan.create_callgroup(session, dialplan.CallGroupIn(name="Both", extension="300", member_ids=[1, 2]))
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
        "-trace_err",
        "-bg" if False else "-nd",
        *args,
        timeout=timeout + 15,
        check=False,
    )


def register(ext: str, port: int) -> None:
    result = sipp("register.xml", port, "-s", ext, "-au", ext, "-ap", PHONES[ext])
    assert result.returncode == 0, result.stdout + result.stderr


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
    callee = subprocess.Popen(
        [
            "sipp",
            HOST,
            "-sf",
            str(SIPP / "answer.xml"),
            "-p",
            "5072",
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
    register("101", 5071)
    caller = sipp("call.xml", 5071, "-au", "101", "-ap", PHONES["101"], "-key", "from", "101", "-key", "to", "102")
    try:
        callee_out = callee.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        callee.kill()
        callee_out = callee.communicate()
    log = Path("/srv/askozia-test/asterisk-console.log").read_text()[-4000:]
    assert caller.returncode == 0, f"{caller.stdout[-1500:]}\nCALLEE:\n{callee_out[0][-2500:]!r}\nASTERISK:\n{log}"
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
