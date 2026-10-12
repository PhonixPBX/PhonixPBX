"""Console menu on tty1 (replaces the legacy rc.initial menu).

Deliberately plain ``input()`` based so it works on any serial or VGA console.
"""

from __future__ import annotations

import getpass
import sys

from phonix import __version__
from phonix.core import settings as st
from phonix.core.db import session_scope
from phonix.services import apply as apply_svc
from phonix.services import facts, firstboot, privileged, users
from phonix.services.common import ServiceError, mark_dirty
from phonix.services.ownership import fix_data_ownership


def _lan() -> tuple[st.NetworkSettings, str]:
    with session_scope() as session:
        net = st.load(session, st.NetworkSettings)
    found = facts.interface_ipv4(net.interface)
    if found:
        ip = found[0]
    elif net.mode == "static":
        ip = net.address
    else:
        # e.g. in the dev container where the host's interface has another name
        ip = facts.default_route_ipv4() or "no address"
    return net, ip


def banner() -> str:
    net, ip = _lan()
    lines = [
        "",
        f"  PhonixPBX {__version__}",
        "",
        f"  LAN ({net.interface}, {'DHCP' if net.mode == 'dhcp' else 'static'}): {ip}",
        f"  Web interface: https://{ip}/",
    ]
    password = firstboot.initial_password()
    if password:
        lines += ["", f"  Initial login: admin / {password}", "  (you must change the password at the first login)"]
    return "\n".join(lines) + "\n"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _confirm(prompt: str) -> bool:
    return _ask(f"{prompt} (y/N)").lower() in ("y", "yes")


def set_lan() -> None:
    with session_scope() as session:
        net = st.load(session, st.NetworkSettings)
        mode = _ask("Use DHCP? (y/n)", "y" if net.mode == "dhcp" else "n").lower()
        data = net.model_dump()
        if mode.startswith("y"):
            data["mode"] = "dhcp"
        else:
            data["mode"] = "static"
            data["address"] = _ask("IP address", net.address)
            data["prefix"] = int(_ask("Prefix length (e.g. 24)", str(net.prefix)))
            data["gateway"] = _ask("Gateway (empty for none)", net.gateway)
            dns = _ask("DNS servers (space separated)", " ".join(net.dns_servers))
            data["dns_servers"] = dns.split()
        try:
            new = st.NetworkSettings.model_validate(data)
        except ValueError as exc:
            print(f"Invalid input: {exc}")
            return
        st.save(session, new)
        mark_dirty(session, "network", "telephony")
        result = apply_svc.apply(session, user="console")
    print("Applied." if result.ok else "Errors: " + "; ".join(result.errors))


def reset_password() -> None:
    username = _ask("Administrator", "admin")
    password = getpass.getpass("New password (min. 8 characters): ")
    if password != getpass.getpass("Repeat: "):
        print("Passwords do not match.")
        return
    try:
        with session_scope() as session:
            if users.get_by_name(session, username) is None:
                users.create_user(session, username, password, actor="console")
            else:
                users.set_password(session, username, password, actor="console")
    except ServiceError as exc:
        print(f"Error: {exc}")
        return
    firstboot.forget_initial_password()
    print("Password changed.")


def _priv(action: str) -> bool:
    try:
        privileged.run(action)
    except privileged.PrivilegedError as exc:
        print(f"Error: {exc}")
        return False
    return True


MENU = [
    ("Show status", lambda: print(banner())),
    ("Set LAN IP address", set_lan),
    ("Reset administrator password", reset_password),
    ("Reboot", lambda: _confirm("Reboot now?") and _priv("reboot")),
    ("Shut down", lambda: _confirm("Shut down now?") and _priv("shutdown")),
    ("Reset to factory defaults", lambda: _confirm("ERASE all configuration and data?") and _priv("factory-reset")),
]


def main() -> int:
    print(banner())
    while True:
        print()
        for idx, (title, _fn) in enumerate(MENU, 1):
            print(f"  {idx}) {title}")
        try:
            choice = input("\nEnter a number: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            continue
        try:
            MENU[int(choice) - 1][1]()
            fix_data_ownership()
        except (EOFError, KeyboardInterrupt):
            print()
        except Exception as exc:  # the console menu must never die
            print(f"Error: {exc}", file=sys.stderr)
