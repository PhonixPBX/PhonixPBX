# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""``phonix`` command line interface (used by init scripts, the console and admins)."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING

from phonix import __version__, config

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _session() -> AbstractContextManager[Session]:
    from phonix.core.db import session_scope

    return session_scope()


def cmd_migrate(args: argparse.Namespace) -> int:
    from phonix.services import setup

    setup.initialize()
    print("database is up to date")
    return 0


def cmd_firstboot(args: argparse.Namespace) -> int:
    from phonix.services import firstboot

    result = firstboot.run()
    for msg in result.messages:
        print(msg)
    if result.admin_password:
        print(f"initial admin password: {result.admin_password}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    from phonix.services import apply as apply_mod

    with _session() as session:
        result = apply_mod.apply(session, user="cli", boot=args.boot, force=args.force)
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        for path in result.changed_files:
            print(f"wrote {path}")
        for action in result.actions:
            print(f"ran   {action}")
        for err in result.errors:
            print(f"ERROR {err}", file=sys.stderr)
    return 0 if result.ok else 1


def cmd_generate(args: argparse.Namespace) -> int:
    """Render all generated files into a directory (no side effects)."""
    from phonix.generators import Facts, Secrets, build_snapshot, generate_all
    from phonix.services import platform

    out = Path(args.output)
    with _session() as session:
        snap = build_snapshot(
            session,
            Facts(lan_ip=args.lan_ip, lan_prefix=24, data_dir=str(config.get().data_dir), platform=platform.kind()),
            Secrets(ami_internal="generated-preview"),
        )
        for f in generate_all(snap):
            target = out / f.path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content)
            print(target)
    return 0


def cmd_user(args: argparse.Namespace) -> int:
    from phonix.services import users
    from phonix.services.common import ServiceError

    try:
        with _session() as session:
            if args.action == "list":
                for user in users.list_users(session):
                    print(f"{user.username}\t{user.role}\tlast login: {user.last_login or '-'}")
                return 0
            if args.action == "delete":
                users.delete_user(session, args.username, actor="cli")
                return 0
            password = args.password or getpass.getpass("Password: ")
            if args.action == "add":
                users.create_user(session, args.username, password, must_change=args.must_change, actor="cli")
            else:
                users.set_password(session, args.username, password, must_change=args.must_change, actor="cli")
    except ServiceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_legacy(args: argparse.Namespace) -> int:
    from phonix.legacy import exporter, importer

    if args.action == "import":
        data = Path(args.file).read_bytes()
        report = importer.import_bytes(
            data, mode="merge" if args.merge else "replace", dry_run=args.dry_run, user="cli"
        )
        print(report.to_text())
        return 0 if report.ok else 1
    with _session() as session:
        xml, export_report = exporter.export(session, user="cli")
    Path(args.file).write_bytes(xml)
    print(export_report.to_text())
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    from phonix.services import backup
    from phonix.services.common import ServiceError

    try:
        if args.action == "create":
            print(backup.create(Path(args.file) if args.file else None))
            return 0
        if not args.file:
            print("error: the backup file is required", file=sys.stderr)
            return 2
        path = Path(args.file)
        keep = [
            part
            for part, wanted in (
                ("network", not args.restore_network),
                ("users", args.keep_users),
                ("certificate", args.keep_certificate),
            )
            if wanted
        ]
        preview = backup.inspect(path) if args.dry_run else backup.restore(path, user="cli", keep=keep)
    except ServiceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"backup from {preview.manifest.get('created')} (PhonixPBX {preview.manifest.get('version')})")
    for section, count in preview.counts.items():
        print(f"  {section:<14}{count:>5}")
    if preview.files:
        print(f"  files: {', '.join(preview.files)}")
    if args.dry_run:
        print("dry run: nothing was changed")
        return 0
    errors = preview.apply_errors if isinstance(preview, backup.RestoreResult) else []
    if isinstance(preview, backup.RestoreResult) and preview.kept:
        print(f"kept the current: {', '.join(preview.kept)}")
    for err in errors:
        print(f"ERROR {err}", file=sys.stderr)
    print("restored and applied" if not errors else "restored; applying failed - run 'phonix apply'")
    return 1 if errors else 0


def cmd_config(args: argparse.Namespace) -> int:
    from phonix.services import configdoc
    from phonix.services.common import ServiceError

    if args.action == "schema":
        print(json.dumps(configdoc.json_schema(), indent=2, sort_keys=True))
        return 0
    if args.action == "export":
        with _session() as session:
            text = json.dumps(configdoc.export(session), indent=2, ensure_ascii=False) + "\n"
        if args.file and args.file != "-":
            path = Path(args.file)
            path.touch(mode=0o600)
            path.write_text(text)
        else:
            sys.stdout.write(text)
        return 0
    if not args.file:
        print("error: the configuration file is required", file=sys.stderr)
        return 2
    try:
        data = json.loads(sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8"))
        doc = configdoc.parse_document(data)
        with _session() as session:
            counts = configdoc.import_document(session, doc, config.get().media_dir, user="cli")
            if args.dry_run:
                session.rollback()
    except ValueError as exc:
        print(f"error: not a JSON file: {exc}", file=sys.stderr)
        return 1
    except ServiceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for section, count in counts.items():
        print(f"  {section:<14}{count:>5}")
    print("dry run: nothing was changed" if args.dry_run else "configuration imported - run 'phonix apply'")
    return 0


def cmd_token(args: argparse.Namespace) -> int:
    from phonix.services import tokens, users
    from phonix.services.common import ServiceError

    try:
        with _session() as session:
            if args.action == "create":
                if not args.name:
                    print("ERROR a token name is required", file=sys.stderr)
                    return 2
                user = users.get_by_name(session, args.user)
                if user is None:
                    print(f"ERROR no administrator {args.user!r}", file=sys.stderr)
                    return 1
                _token, plain = tokens.create(
                    session,
                    user,
                    args.name,
                    read_only=args.read_only,
                    allow_calls=args.allow_calls,
                    expires_in_days=args.expires_days,
                    actor="cli",
                )
                print(plain)
            elif args.action == "list":
                for t in tokens.list_tokens(session):
                    d = tokens.to_dict(t)
                    last = d["last_used_at"].strftime("%Y-%m-%d %H:%M") if d["last_used_at"] else "never"
                    until = d["expires_at"].strftime("%Y-%m-%d") if d["expires_at"] else "unlimited"
                    access = ("ro" if d["read_only"] else "rw") + ("+calls" if d["allow_calls"] else "")
                    print(
                        f"{d['id']:>4}  {d['name']:<24} {d['prefix']}  {access}  {d['status']:<8}  {d['user']:<12}"
                        f"  last used {last:<16}  valid until {until}"
                    )
            else:
                if not args.name or not args.name.isdigit():
                    print("ERROR give the token id (see 'phonix token list')", file=sys.stderr)
                    return 2
                token_id = int(args.name)
                if args.action == "delete":
                    tokens.delete(session, token_id, actor="cli")
                else:
                    tokens.set_enabled(session, token_id, args.action == "enable", actor="cli")
    except ServiceError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_cert(args: argparse.Namespace) -> int:
    from phonix.services import acme
    from phonix.services.common import ServiceError

    try:
        with _session() as session:
            print(acme.issue(session, force=args.force, user="cli"))
    except ServiceError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    from phonix.core import settings as st
    from phonix.services import privileged, update
    from phonix.services.common import ServiceError

    if args.action == "install":
        if not args.bundle:
            print("ERROR the update bundle is missing", file=sys.stderr)
            return 2
        try:
            info = update.run_install(Path(args.bundle).resolve(), args.user, remove=args.remove, force=args.force)
        except (ServiceError, privileged.PrivilegedError, OSError) as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 1
        print(f"version {info.version} installed - reboot to activate")
        return 0
    with _session() as session:
        settings = st.load(session, st.UpdateSettings)
    if args.auto and not settings.auto_check:
        return 0
    try:
        release = update.check_online(settings.check_url)
    except ServiceError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    if update.is_newer(release.version, __version__):
        print(f"version {release.version} is available (running {__version__}): {release.download or release.url}")
    else:
        print(f"running the latest version ({__version__})")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    import uvicorn

    kwargs: dict[str, object] = {"proxy_headers": True, "forwarded_allow_ips": "*"}
    if args.uds:
        kwargs["uds"] = args.uds
    else:
        kwargs["host"] = args.host
        kwargs["port"] = args.port
    uvicorn.run("phonix.web.app:create_app", factory=True, reload=args.reload, **kwargs)  # type: ignore[arg-type]
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    from phonix.services import monitor

    monitor.run_forever()
    return 0


def cmd_healthcheck(args: argparse.Namespace) -> int:
    from phonix.services import health

    ok, details = health.check()
    for line in details:
        print(line)
    if ok and args.mark_good:
        from phonix.services import privileged

        privileged.run("mark-good")
        print("boot slot marked good")
    return 0 if ok else 1


def cmd_tui(args: argparse.Namespace) -> int:
    from phonix import tui

    return tui.main()


def cmd_banner(args: argparse.Namespace) -> int:
    from phonix import tui

    print(tui.banner())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phonix", description="PhonixPBX management")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="create/upgrade the database").set_defaults(func=cmd_migrate)
    sub.add_parser("firstboot", help="initialise the data partition").set_defaults(func=cmd_firstboot)

    a = sub.add_parser("apply", help="generate and activate the configuration")
    a.add_argument("--boot", action="store_true", help="early boot: write files only")
    a.add_argument("--force", action="store_true", help="rewrite and reload everything")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_apply)

    g = sub.add_parser("generate", help="render all config files into a directory")
    g.add_argument("output")
    g.add_argument("--lan-ip", default="192.168.1.2")
    g.set_defaults(func=cmd_generate)

    u = sub.add_parser("user", help="manage web administrators")
    u.add_argument("action", choices=["list", "add", "passwd", "delete"])
    u.add_argument("username", nargs="?", default="admin")
    u.add_argument("--password")
    u.add_argument("--must-change", action="store_true")
    u.set_defaults(func=cmd_user)

    lg = sub.add_parser("legacy", help="import/export legacy AskoziaPBX config.xml")
    lg.add_argument("action", choices=["import", "export"])
    lg.add_argument("file")
    lg.add_argument("--dry-run", action="store_true")
    lg.add_argument("--merge", action="store_true")
    lg.set_defaults(func=cmd_legacy)

    b = sub.add_parser("backup", help="create or restore a backup")
    b.add_argument("action", choices=["create", "restore"])
    b.add_argument("file", nargs="?")
    b.add_argument("--dry-run", action="store_true", help="restore: only validate and show the contents")
    b.add_argument(
        "--restore-network",
        action="store_true",
        help="restore: also take the network, firewall and SSH settings from the backup (default: keep the current)",
    )
    b.add_argument("--keep-users", action="store_true", help="restore: keep the current web users and API tokens")
    b.add_argument(
        "--keep-certificate", action="store_true", help="restore: keep the current TLS certificate and ACME settings"
    )
    b.set_defaults(func=cmd_backup)

    cf = sub.add_parser("config", help="export/import the configuration as JSON (config.json)")
    cf.add_argument("action", choices=["export", "import", "schema"])
    cf.add_argument("file", nargs="?", help="'-' or empty for stdout (export); '-' for stdin (import)")
    cf.add_argument("--dry-run", action="store_true", help="import: only validate")
    cf.set_defaults(func=cmd_config)

    t = sub.add_parser("token", help="manage API bearer tokens")
    t.add_argument("action", choices=["create", "list", "enable", "disable", "delete"])
    t.add_argument("name", nargs="?", help="token name (create) or id (enable/disable/delete)")
    t.add_argument("--user", default="admin", help="owning administrator (create)")
    t.add_argument("--read-only", action="store_true", help="GET requests only (create)")
    t.add_argument("--allow-calls", action="store_true", help="may place calls via the API and MCP (create)")
    t.add_argument("--expires-days", type=int, help="validity in days (create); default unlimited")
    t.set_defaults(func=cmd_token)

    c = sub.add_parser("cert", help="ACME certificate (Let's Encrypt)")
    c.add_argument("action", choices=["renew"])
    c.add_argument("--force", action="store_true", help="request a new certificate even if not due")
    c.set_defaults(func=cmd_cert)

    up = sub.add_parser("update", help="firmware updates")
    up.add_argument("action", choices=["check", "install"])
    up.add_argument("bundle", nargs="?", help="install: the .update bundle (below /data)")
    up.add_argument("--user", default="cli", help="install: the user named in the audit log")
    up.add_argument("--remove", action="store_true", help="install: delete the bundle afterwards")
    up.add_argument("--force", action="store_true", help="install: allow the same or an older version")
    up.add_argument("--auto", action="store_true", help="only if automatic checks are enabled (periodic job)")
    up.set_defaults(func=cmd_update)

    w = sub.add_parser("web", help="run the web interface")
    w.add_argument("--uds", help="listen on a unix socket")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)
    w.add_argument("--reload", action="store_true")
    w.set_defaults(func=cmd_web)

    sub.add_parser("monitor", help="watch Asterisk security events").set_defaults(func=cmd_monitor)
    h = sub.add_parser("healthcheck", help="check web + Asterisk")
    h.add_argument("--mark-good", action="store_true", help="confirm the booted update slot")
    h.set_defaults(func=cmd_healthcheck)
    sub.add_parser("tui", help="console menu").set_defaults(func=cmd_tui)
    sub.add_parser("banner", help="print the console banner").set_defaults(func=cmd_banner)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    try:
        return int(args.func(args))
    finally:
        if args.command not in ("web", "monitor"):
            from phonix.services.ownership import fix_data_ownership

            fix_data_ownership()


if __name__ == "__main__":
    sys.exit(main())
