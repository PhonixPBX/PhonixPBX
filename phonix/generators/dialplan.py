# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
"""extensions.conf generator - port of legacy etc/inc/extensions.inc to Asterisk 22.

Context layout
--------------
``internal``            every internal number (phones, call groups, applications,
                        conference rooms), parking, hints and directed pickup
``public-direct-dial``  numbers reachable from providers / anonymous callers
                        (objects with "public access" enabled)
``incoming-dest``       ring targets used by provider incoming routes
``phone-<ext>``         per phone: internal + allowed providers (+ call forwarding)
``phone-<ext>-out``     per phone: provider dial patterns not blocked for the phone
``prov-<id>-out``       per provider: dial patterns -> Dial(), failover
``prov-<id>-in``        per provider: incoming routes
``app-<id>``            custom application logic
``conf-<id>``           conference room PIN handling
``ivr-<id>[-pub]``      IVR menu (``-pub``: for callers from outside: public direct
                        dial, no transfer feature)
``hours-<id>[-pub]``    business hours: open/closed destination
``sub-*``               shared subroutines (Gosub; Macro() is gone in Asterisk 21+)
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from phonix.core.models import Application, BusinessHours, CallGroup, ConferenceRoom, IvrMenu, Phone, Provider
from phonix.core.validation import parse_dialpattern
from phonix.generators.base import HEADER, Snapshot

NOTIFY_SCRIPT = "/usr/libexec/phonix/notify"
CF_MAX_HOPS = 3
APP_PATTERN = "_[0-9a-zA-Z*#]!"
CATCHALL_PATTERN = "_[0-9*#+]!"
# Asterisk database family of the live business hours mode (key: id, value: open/closed)
HOURS_DB = "phonix-hours"
ASTERISK_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_UNSAFE = re.compile(r"[^\w .@+-]")


def safe_text(text: str) -> str:
    """Text for NoOp() and comments: no variables, quotes or argument separators."""
    return _UNSAFE.sub("", text)


def ext_pattern(extension: str) -> str:
    """Port of extensions_patternify(): non-numeric extensions become patterns."""
    return extension if extension.isdigit() else "_" + extension.lstrip("_")


class Context:
    def __init__(self, name: str, comment: str = "") -> None:
        self.name = name
        self.comment = comment
        self.lines: list[str] = []

    def include(self, other: str) -> None:
        self.lines.append(f"include => {other}")

    def ext(self, exten: str, steps: Iterable[str], comment: str = "") -> None:
        """Add an extension: first step gets priority 1, the rest ``same => n``.

        A step written as ``"@label App()"`` gets the priority label ``label``.
        """
        steps = list(steps)
        if not steps:
            return
        if comment:
            self.lines.append(f"; {comment}")
        for idx, step in enumerate(steps):
            label = ""
            if step.startswith("@"):
                label, step = step[1:].split(" ", 1)
                label = f"({label})"
            prio = "1" if idx == 0 else "n"
            prefix = f"exten => {exten}," if idx == 0 else " same => "
            self.lines.append(f"{prefix}{prio}{label},{step}")

    def raw(self, line: str) -> None:
        self.lines.append(line)

    def render(self) -> str:
        head = f"; {self.comment}\n" if self.comment else ""
        return head + f"[{self.name}]\n" + "\n".join(self.lines) + "\n"


@dataclass
class RingTarget:
    """Something that rings: dialstring + voicemail box + notification settings."""

    dialstring: str
    vm_box: str
    notify_email: str
    ringlength: int | None
    # key of the target in phonix-notify.json (language and name of the missed call mail)
    notify_target: str = ""
    cf_extension: str = ""
    pickupmark: str = ""


def phone_dialstring(phone: Phone, snap: Snapshot) -> str:
    if phone.tech == "pjsip":
        return f"PJSIP/{phone.extension}"
    if phone.tech == "iax":
        return f"IAX2/{phone.extension}"
    # external phone (legacy extensions_phone_uniqid_to_dialstring)
    if phone.dial_type == "sip_uri":
        return f"PJSIP/uri-dial/sip:{phone.dial_string}"
    if phone.dial_type == "iax_uri":
        user, host = phone.dial_string.split("@", 1)
        return f"IAX2/{host}/{user}"
    provider = snap.provider(phone.dial_provider_id)
    if provider is None or not provider.enabled:
        return ""
    if provider.tech == "iax":
        return f"IAX2/prov-{provider.id}/{phone.dial_string}"
    return f"PJSIP/{phone.dial_string}@prov-{provider.id}"


def phone_target(phone: Phone, snap: Snapshot) -> RingTarget:
    return RingTarget(
        dialstring=phone_dialstring(phone, snap),
        vm_box=phone.extension if phone.vm_enabled else "",
        notify_email=phone.notify_email if phone.notify_missed else "",
        ringlength=phone.ringlength,
        notify_target=phone.extension,
        cf_extension=phone.extension if phone.tech != "external" else "",
        pickupmark=phone.extension,
    )


def group_notify_target(group: CallGroup) -> str:
    """Key of a call group in phonix-notify.json."""
    return f"group-{group.id}"


def group_steps(
    group: CallGroup, snap: Snapshot, _seen: set[int] | None = None
) -> list[tuple[int | None, list[Phone]]]:
    """The members of a call group in order, with nested call groups resolved to their phones.

    Each step is ``(ringlength, phones)``: a phone member is a step with its own ring time, a nested
    call group one step that rings all its (recursively resolved) phones at once with the nested
    group's ring time. Disabled phones, phones seen before and empty steps are left out; a group
    that is already being resolved is skipped (the service layer rejects such loops).
    """
    seen = _seen if _seen is not None else set()
    seen.add(group.id)
    phones_seen: set[int] = set()
    steps: list[tuple[int | None, list[Phone]]] = []
    for member in group.members:
        if member.member_group_id is not None:
            child = snap.callgroup(member.member_group_id)
            if child is None or child.id in seen:
                continue
            phones = [p for _rl, ps in group_steps(child, snap, seen) for p in ps]
            ringlength = child.ringlength
        else:
            phone = snap.phone(member.phone_id) if member.phone_id is not None else None
            phones = [phone] if phone is not None and phone.enabled else []
            ringlength = phone.ringlength if phone is not None else None
        phones = [p for p in phones if p.id not in phones_seen]
        phones_seen.update(p.id for p in phones)
        if phones:
            steps.append((ringlength, phones))
    return steps


def group_members(group: CallGroup, snap: Snapshot) -> list[Phone]:
    """All active phones of a call group, nested call groups included, in ringing order."""
    return [p for _rl, phones in group_steps(group, snap) for p in phones]


def ring_steps(target: RingTarget, from_public: bool, linear: list[RingTarget] | None = None) -> list[str]:
    """Dialplan steps that ring a target (legacy extensions_generate_*_extension)."""
    steps: list[str] = []
    if target.pickupmark:
        steps.append(f"Set(__PICKUPMARK={target.pickupmark})")
    if target.cf_extension:
        steps.append(f"Gosub(sub-checkcf,s,1({target.cf_extension}))")
    if target.notify_email:
        steps.append(f"Set(NOTIFY_EMAIL={target.notify_email})")
        steps.append(f"Set(NOTIFY_TARGET={target.notify_target})")
        steps.append("Set(CHANNEL(hangup_handler_push)=sub-missed-call,s,1)")
    # callers coming from outside must not get the transfer and disconnect features (legacy "t" vs "tT");
    # h/H enable the disconnect code (*0) for the called / calling phone
    options = "th" if from_public else "tThH"
    timeout = str(target.ringlength) if target.ringlength else ""
    if linear:
        for member in linear:
            steps.append(f"Gosub(sub-try,s,1({member.dialstring},{options},{member.ringlength or 20}))")
        steps.append(f"Gosub(sub-dial,s,1(,{target.vm_box},{options},))")
    else:
        if not target.dialstring:
            return [*steps, "Congestion(5)", "Hangup()"]
        steps.append(f"Gosub(sub-dial,s,1({target.dialstring},{target.vm_box},{options},{timeout}))")
    steps.append("Hangup()")
    return steps


def callgroup_steps(group: CallGroup, snap: Snapshot, from_public: bool) -> list[str]:
    members = group_steps(group, snap)
    if not members:
        return ["NoOp(Call group has no active members)", "Congestion(5)", "Hangup()"]
    first = members[0][1][0]
    target = RingTarget(
        dialstring=_joined(members, snap),
        # legacy: the first member's mailbox takes unanswered group calls
        vm_box=first.extension if first.vm_enabled else "",
        notify_email=first.notify_email if first.notify_missed else "",
        ringlength=group.ringlength,
        notify_target=group_notify_target(group),
    )
    if group.strategy == "linear":
        linear = [
            RingTarget(
                dialstring=_joined([(ringlength, phones)], snap),
                vm_box="",
                notify_email="",
                ringlength=group.ringlength or ringlength or 20,
            )
            for ringlength, phones in members
        ]
        return ring_steps(target, from_public, linear=[t for t in linear if t.dialstring])
    return ring_steps(target, from_public)


def _joined(steps: list[tuple[int | None, list[Phone]]], snap: Snapshot) -> str:
    dialstrings = (phone_dialstring(p, snap) for _rl, phones in steps for p in phones)
    return "&".join(d for d in dialstrings if d)


def application_steps(app: Application) -> list[str]:
    return [f"Goto(app-{app.id},${{EXTEN}},1)"]


def room_steps(room: ConferenceRoom) -> list[str]:
    return [f"Gosub(conf-{room.id},s,1)", "Hangup()"]


def last_minute(end: str) -> str:
    """GotoIfTime() includes the end minute and takes no 24:00: "17:30" (exclusive) -> "17:29"."""
    minutes = (24 * 60 if end == "24:00" else int(end[:2]) * 60 + int(end[3:])) - 1
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def ivr_context(menu: IvrMenu, from_public: bool) -> str:
    return f"ivr-{menu.id}-pub" if from_public else f"ivr-{menu.id}"


def hours_context(hours: BusinessHours, from_public: bool) -> str:
    return f"hours-{hours.id}-pub" if from_public else f"hours-{hours.id}"


def _terminated(steps: list[str]) -> list[str]:
    if steps and steps[-1].startswith(("Hangup(", "Goto(")):
        return steps
    return [*steps, "Hangup()"]


class DialplanBuilder:
    def __init__(self, snap: Snapshot) -> None:
        self.snap = snap
        self.contexts: OrderedDict[str, Context] = OrderedDict()

    def ctx(self, name: str, comment: str = "") -> Context:
        if name not in self.contexts:
            self.contexts[name] = Context(name, comment)
        return self.contexts[name]

    # -- static subroutines ---------------------------------------------------

    def subroutines(self) -> None:
        snap = self.snap
        greeting = None
        if snap.media.custom_vm_greeting:
            greeting = next((m for m in snap.media_files if m.kind == "vm_greeting"), None)

        sub = self.ctx("sub-dial", "ARG1 dialstring, ARG2 voicemail box, ARG3 dial options, ARG4 timeout")
        sub.ext(
            "s",
            [
                'GotoIf($["${ARG1}" = ""]?s-NOANSWER,1)',
                "Dial(${ARG1},${ARG4},${ARG3})",
                "Goto(s-${DIALSTATUS},1)",
            ],
        )
        sub.ext("s-ANSWER", ["Hangup()"])
        sub.ext("s-CANCEL", ["Hangup()"])
        sub.ext(
            "s-BUSY",
            [
                "Set(MISSEDCAUSE=busy)",
                'GotoIf($["${ARG2}" = ""]?nobox)',
                "Answer()",
                "VoiceMail(${ARG2}@default,b)",
                "Hangup()",
                "@nobox Busy(10)",
            ],
        )
        sub.ext("s-NOANSWER", ["Set(MISSEDCAUSE=no-answer)", "Goto(vm,1)"])
        sub.ext("_s-.", ["Set(MISSEDCAUSE=unavailable)", "Goto(vm,1)"])
        vm_steps = [
            'GotoIf($["${ARG2}" = ""]?nobox)',
            "Answer()",
            "Wait(1)",
        ]
        if greeting is not None:
            sound = f"{snap.facts.data_dir}/media/{greeting.path.rsplit('.', 1)[0]}"
            vm_steps += [f"Playback({sound})", "VoiceMail(${ARG2}@default,s)"]
        else:
            vm_steps += ["VoiceMail(${ARG2}@default,u)"]
        vm_steps += ["Hangup()", "@nobox Hangup()"]
        sub.ext("vm", vm_steps)

        # sequential ringing for "linear" call groups: returns unless answered
        sub = self.ctx("sub-try", "ARG1 dialstring, ARG2 options, ARG3 timeout")
        sub.ext(
            "s",
            [
                "Dial(${ARG1},${ARG3},${ARG2})",
                'GotoIf($["${DIALSTATUS}" = "ANSWER"]?done)',
                "Return()",
                "@done Hangup()",
            ],
        )

        # call forwarding (legacy macro-checkcf): DB(CF/<ext>) holds the target
        sub = self.ctx("sub-checkcf", "ARG1 extension that may be forwarded")
        sub.ext(
            "s",
            [
                "Set(LOCAL(dest)=${DB(CF/${ARG1})})",
                'GotoIf($["${dest}" = ""]?ret)',
                'GotoIf($["${dest}" = "${CALLERID(num)}"]?ret)',
                f"GotoIf($[0${{CF_HOPS}} >= {CF_MAX_HOPS}]?ret)",
                "Set(__CF_HOPS=$[0${CF_HOPS} + 1])",
                "GotoIf($[${DIALPLAN_EXISTS(phone-${ARG1},${dest},1)}]?fwd)",
                "@ret Return()",
                "@fwd StackPop()",
                "Goto(phone-${ARG1},${dest},1)",
            ],
        )

        # missed call notification e-mail (hangup handler)
        sub = self.ctx("sub-missed-call", "hangup handler: mail missed calls")
        if snap.email.configured:
            sub.ext(
                "s",
                [
                    'GotoIf($["${DIALSTATUS}" = "ANSWER"]?done)',
                    'GotoIf($["${NOTIFY_EMAIL}" = ""]?done)',
                    'GotoIf($["${VMSTATUS}" = "SUCCESS"]?done)',
                    f'System({NOTIFY_SCRIPT} missed "${{NOTIFY_EMAIL}}" "${{NOTIFY_TARGET}}" '
                    '"${IF($["${MISSEDCAUSE}" = ""]?hung-up:${MISSEDCAUSE})}" '
                    '"${FILTER(0-9a-zA-Z +._@<>-,${CALLERID(all)})}")',
                    "@done Return()",
                ],
            )
        else:
            sub.ext("s", ["Return()"])

        self.ctx("no-inbound", "inbound requests on helper endpoints are refused").ext("_X.", ["Hangup(21)"])

    # -- per object -------------------------------------------------------------

    def target_steps(self, kind: str, obj: object, from_public: bool) -> list[str]:
        snap = self.snap
        if kind == "phone":
            assert isinstance(obj, Phone)
            return ring_steps(phone_target(obj, snap), from_public)
        if kind == "callgroup":
            assert isinstance(obj, CallGroup)
            return callgroup_steps(obj, snap, from_public)
        if kind == "application":
            assert isinstance(obj, Application)
            return application_steps(obj)
        if kind == "ivr":
            assert isinstance(obj, IvrMenu)
            return [f"Goto({ivr_context(obj, from_public)},s,1)"]
        if kind == "hours":
            assert isinstance(obj, BusinessHours)
            return [f"Goto({hours_context(obj, from_public)},s,1)"]
        assert isinstance(obj, ConferenceRoom)
        return room_steps(obj)

    def pools(self) -> dict[str, list[Any]]:
        """Objects a destination may point to (disabled ones are left out)."""
        snap = self.snap
        return {
            "phone": snap.active_phones,
            "callgroup": snap.callgroups,
            "application": [a for a in snap.applications if a.enabled],
            "conference": snap.rooms,
            "ivr": [m for m in snap.ivr_menus if m.enabled],
            "hours": snap.business_hours,
        }

    def dest_steps(self, kind: str, dest_id: int | None, from_public: bool) -> list[str]:
        """Steps for one destination of an IVR key or of business hours; always terminated."""
        if kind == "hangup":
            return ["Hangup()"]
        if kind == "repeat":
            return ["Goto(s,prompt)"]
        if kind == "voicemail":
            phone = next((p for p in self.snap.active_phones if p.id == dest_id), None)
            if phone is None or not phone.vm_enabled:
                return ["NoOp(Voicemail box not available)", "Hangup()"]
            # sub-dial's vm step plays the custom greeting, if there is one
            return [f"Gosub(sub-dial,vm,1(,{phone.extension},,))", "Hangup()"]
        obj = next((o for o in self.pools().get(kind, []) if o.id == dest_id), None)
        if obj is None:
            return [f"NoOp(Destination {kind} {dest_id} is not available)", "Hangup()"]
        if kind == "application":
            return [f"Goto(app-{obj.id},s,1)"]
        return _terminated(self.target_steps(kind, obj, from_public))

    def numbered_objects(self) -> list[tuple[str, str, str, object, bool, str]]:
        """(kind, number, label, obj, public_access, public_name) for every dialable object."""
        snap = self.snap
        out: list[tuple[str, str, str, object, bool, str]] = []
        for phone in snap.active_phones:
            out.append(
                (
                    "phone",
                    phone.extension,
                    f"phone {phone.callerid} <{phone.extension}>",
                    phone,
                    phone.public_access,
                    phone.public_name,
                )
            )
        for group in snap.callgroups:
            if group.extension:
                out.append(
                    (
                        "callgroup",
                        group.extension,
                        f"call group {group.name}",
                        group,
                        group.public_access,
                        group.public_name,
                    )
                )
        for app in snap.applications:
            if app.enabled:
                out.append(
                    (
                        "application",
                        ext_pattern(app.extension),
                        f"application {app.name}",
                        app,
                        app.public_access,
                        app.public_name,
                    )
                )
        for room in snap.rooms:
            out.append(
                ("conference", room.number, f"conference {room.name}", room, room.public_access, room.public_name)
            )
        for menu in snap.ivr_menus:
            if menu.enabled and menu.extension:
                out.append(
                    (
                        "ivr",
                        menu.extension,
                        f"IVR menu {safe_text(menu.name)}",
                        menu,
                        menu.public_access,
                        menu.public_name,
                    )
                )
        return out

    def internal(self) -> None:
        snap = self.snap
        internal = self.ctx("internal", "every internal number")
        public = self.ctx("public-direct-dial", "numbers reachable from outside")
        for kind, number, label, obj, is_public, public_name in self.numbered_objects():
            internal.ext(number, [f"NoOp(Internal call to {label})", *self.target_steps(kind, obj, False)], label)
            if is_public:
                pub_number = public_name or number
                if kind == "application" and public_name:
                    steps = [f"Goto(app-{obj.id},s,1)"]  # type: ignore[attr-defined]
                else:
                    steps = self.target_steps(kind, obj, True)
                public.ext(pub_number, [f"NoOp(Public call to {label})", *steps], label)

        for hours in snap.business_hours:
            if hours.feature_code:
                key = f"{HOURS_DB}/{hours.id}"
                internal.ext(
                    hours.feature_code,
                    [
                        f"NoOp(Switch business hours {safe_text(hours.name)})",
                        "Answer()",
                        f'GotoIf($["${{DB({key})}}" = ""]?close)',
                        f"Set(HOURS_OLD=${{DB_DELETE({key})}})",
                        "Playback(de-activated)",
                        "Hangup()",
                        f"@close Set(DB({key})=closed)",
                        "Playback(activated)",
                        "Hangup()",
                    ],
                    f"business hours {safe_text(hours.name)}: closed / automatic",
                )

        f = snap.features
        internal.raw("; call parking")
        internal.include("parkedcalls")
        internal.raw("; directed pickup")
        internal.ext(f"_{f.pickup}X.", [f"Pickup(${{EXTEN:{len(f.pickup)}}}@PICKUPMARK)", "Hangup()"])
        internal.raw("; device state hints")
        for phone in snap.active_phones:
            if phone.tech == "pjsip":
                internal.raw(f"exten => {phone.extension},hint,PJSIP/{phone.extension}")
            elif phone.tech == "iax":
                internal.raw(f"exten => {phone.extension},hint,IAX2/{phone.extension}")

    def applications(self) -> None:
        for app in self.snap.applications:
            if not app.enabled:
                continue
            ctx = self.ctx(f"app-{app.id}", f"application: {app.name}")
            includes = []
            body = []
            for line in app.logic.splitlines():
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                if line.lower().startswith("include"):
                    includes.append(line)
                else:
                    body.append(line)
            for line in includes:
                ctx.raw(line)
            # legacy extensions_generate_application_context2(): every number and "s"
            for exten in (APP_PATTERN, "s"):
                for line in body:
                    ctx.raw(f"exten => {exten},{line}")

    def rooms(self) -> None:
        for room in self.snap.rooms:
            ctx = self.ctx(f"conf-{room.id}", f"conference room {room.name} <{room.number}>")
            bridge = f"ConfBridge({room.number},phonix_bridge,phonix_user,phonix_menu)"
            admin = f"ConfBridge({room.number},phonix_bridge,phonix_admin,phonix_admin_menu)"
            steps = ["Answer()", "Wait(1)"]
            if not room.pin and not room.admin_pin:
                ctx.ext("s", [*steps, bridge, "Return()"])
                continue
            steps += ["Set(LOCAL(tries)=0)", "@ask Read(PIN,conf-getpin,16,,1,10)"]
            if room.admin_pin:
                steps.append(f'GotoIf($["${{PIN}}" = "{room.admin_pin}"]?admin)')
            if room.pin:
                steps.append(f'GotoIf($["${{PIN}}" = "{room.pin}"]?user)')
            else:
                steps.append('GotoIf($["${PIN}" = ""]?user)')
            steps += [
                "Set(LOCAL(tries)=$[${tries} + 1])",
                "Playback(conf-invalidpin)",
                "GotoIf($[${tries} < 3]?ask)",
                "Return()",
                f"@admin {admin}",
                "Return()",
                f"@user {bridge}",
                "Return()",
            ]
            ctx.ext("s", steps)

    # -- IVR menus and business hours --------------------------------------------

    def prompt(self, menu: IvrMenu) -> str:
        if menu.prompt_mode == "sound":
            return menu.prompt_sound
        media = next((m for m in self.snap.media_files if m.id == menu.prompt_media_id), None)
        if media is None:
            return ""
        return f"{self.snap.facts.data_dir}/media/{media.path.rsplit('.', 1)[0]}"

    def ivr_menus(self) -> None:
        for menu in self.snap.ivr_menus:
            if not menu.enabled:
                continue
            name = safe_text(menu.name)
            for public in (False, True):
                comment = f"IVR menu {name}" + (" (callers from outside)" if public else "")
                ctx = self.ctx(ivr_context(menu, public), comment)
                if menu.direct_dial:
                    ctx.include("public-direct-dial" if public else "internal")
                prompt = self.prompt(menu)
                wait = f"WaitExten({menu.timeout})"
                steps = [f"NoOp(IVR menu {name})", "Answer()", "Set(IVR_TRIES=0)", "Wait(1)"]
                steps += [f"@prompt Background({prompt})", wait] if prompt else [f"@prompt {wait}"]
                ctx.ext("s", steps)
                for option in menu.options:
                    label = safe_text(option.label) or option.key
                    ctx.ext(
                        option.key,
                        [f"NoOp(IVR menu {name}: {label})", *self.dest_steps(option.dest_type, option.dest_id, public)],
                    )
                if menu.invalid_dest_type == "repeat":
                    ctx.ext("i", ["Playback(option-is-invalid)", "Goto(t,1)"])
                else:
                    ctx.ext("i", self.dest_steps(menu.invalid_dest_type, menu.invalid_dest_id, public))
                ctx.ext(
                    "t",
                    [
                        "Set(IVR_TRIES=$[${IVR_TRIES} + 1])",
                        f"GotoIf($[${{IVR_TRIES}} <= {menu.repeats}]?s,prompt)",
                        *self.dest_steps(menu.timeout_dest_type, menu.timeout_dest_id, public),
                    ],
                )

    def business_hours(self) -> None:
        for hours in self.snap.business_hours:
            name = safe_text(hours.name)
            for public in (False, True):
                comment = f"business hours {name}" + (" (callers from outside)" if public else "")
                ctx = self.ctx(hours_context(hours, public), comment)
                steps = [
                    f"NoOp(Business hours {name})",
                    f"Set(HOURS_MODE=${{DB({HOURS_DB}/{hours.id})}})",
                    'GotoIf($["${HOURS_MODE}" = "open"]?open)',
                    'GotoIf($["${HOURS_MODE}" = "closed"]?closed)',
                ]
                if hours.holidays:
                    steps.append("Set(HOURS_TODAY=${STRFTIME(${EPOCH},,%Y-%m-%d)})")
                    for h in hours.holidays:
                        if h.yearly:
                            steps.append(f'GotoIf($["${{HOURS_TODAY:5}}" = "{h.date:%m-%d}"]?closed)')
                        else:
                            steps.append(f'GotoIf($["${{HOURS_TODAY}}" = "{h.date.isoformat()}"]?closed)')
                for r in hours.ranges:
                    steps.append(f"GotoIfTime({r.start}-{last_minute(r.end)},{ASTERISK_DAYS[r.weekday]},*,*?open)")
                steps.append("Goto(closed)")
                steps.append("@open NoOp(open)")
                steps += self.dest_steps(hours.open_dest_type, hours.open_dest_id, public)
                steps.append("@closed NoOp(closed)")
                steps += self.dest_steps(hours.closed_dest_type, hours.closed_dest_id, public)
                ctx.ext("s", steps)

    # -- providers --------------------------------------------------------------

    def provider_out(self, provider: Provider) -> None:
        if not provider.dialpatterns:
            return
        ctx = self.ctx(f"prov-{provider.id}-out", f"outgoing via {provider.name}")
        failover = self.snap.provider(provider.failover_provider_id)
        if failover is not None and (not failover.enabled or not failover.dialpatterns):
            failover = None
        for dp in provider.dialpatterns:
            pattern, prefix, strip = parse_dialpattern(dp.pattern)
            number = prefix + (f"${{EXTEN:{strip}}}" if strip else "${EXTEN}")
            if provider.tech == "iax":
                dial = f"Dial(IAX2/prov-{provider.id}/{number},,TH)"
            else:
                dial = f"Dial(PJSIP/{number}@prov-{provider.id},,TH)"
            steps = [f"NoOp(Outgoing call via {provider.name})", "Set(CDR(userfield)=outbound)", dial]
            if failover is not None:
                steps += [
                    'GotoIf($["${DIALSTATUS}" != "CHANUNAVAIL" & "${DIALSTATUS}" != "CONGESTION"]?done)',
                    f"GotoIf($[${{DIALPLAN_EXISTS(prov-{failover.id}-out,${{EXTEN}},1)}}]"
                    f"?prov-{failover.id}-out,${{EXTEN}},1)",
                ]
            steps.append("@done Hangup()" if failover is not None else "Hangup()")
            ctx.ext("_" + pattern, steps)

    def phone_contexts(self) -> None:
        snap = self.snap
        for phone in snap.active_phones:
            if phone.tech == "external":
                continue
            ctx = self.ctx(f"phone-{phone.extension}", f"{phone.callerid} <{phone.extension}>")
            ctx.include("internal")
            ctx.include(f"phone-{phone.extension}-out")
            out = self.ctx(f"phone-{phone.extension}-out")
            blocked = {p.id for p in phone.blocked_providers}
            overrides = {c.provider_id: c.callerid for c in phone.provider_callerids}
            for provider in snap.active_providers:
                if provider.id in blocked or not provider.dialpatterns:
                    continue
                cid = overrides.get(provider.id)
                if cid is None and provider.callerid_source == "string":
                    cid = provider.callerid_string
                for dp in provider.dialpatterns:
                    pattern = parse_dialpattern(dp.pattern)[0]
                    steps = [f"NoOp(Outgoing call to {provider.name})", "Set(ORIGEXTEN=${EXTEN})"]
                    if cid:
                        steps.append(f"Set(CALLERID(all)={cid})")
                    steps.append(f"Goto(prov-{provider.id}-out,${{EXTEN}},1)")
                    out.ext("_" + pattern, steps)

    def provider_in(self, provider: Provider) -> None:
        snap = self.snap
        ctx = self.ctx(f"prov-{provider.id}-in", f"incoming via {provider.name}")
        ctx.include("public-direct-dial")
        # group destinations sharing a pattern ("impromptu call groups")
        grouped: OrderedDict[str, list[tuple[str, int]]] = OrderedDict()
        for route in provider.incoming_routes:
            grouped.setdefault(route.pattern, []).append((route.dest_type, route.dest_id))

        def cid_steps() -> list[str]:
            mode, text = provider.incoming_cid_override, provider.incoming_cid_string
            if mode == "replacenamewithnum":
                return ["Set(CALLERID(name)=${CALLERID(number)})"]
            if mode == "replace":
                return [f"Set(CALLERID(all)={text})"]
            if mode == "prepend":
                return [f"Set(CALLERID(name)={text} ${{CALLERID(name)}})"]
            return []

        for pattern, dests in grouped.items():
            steps = self.destination_steps(dests)
            if not steps:
                continue
            if pattern == "":
                extens = [CATCHALL_PATTERN, "s"]
                if provider.tech == "pjsip" and provider.username not in extens:
                    extens.append(provider.username)
            elif pattern.isdigit():
                extens = [pattern]
            else:
                extens = ["_" + pattern]
            for exten in extens:
                ctx.ext(
                    exten,
                    [
                        f"NoOp(Incoming call via {provider.name} to ${{EXTEN}})",
                        "Set(CDR(userfield)=inbound)",
                        *cid_steps(),
                        *steps,
                    ],
                )
        del snap

    def destination_steps(self, dests: list[tuple[str, int]]) -> list[str]:
        snap = self.snap
        resolved: list[tuple[str, object]] = []
        pools = self.pools()
        for kind, dest_id in dests:
            obj = next((o for o in pools.get(kind, []) if o.id == dest_id), None)
            if obj is not None:
                resolved.append((kind, obj))
        if not resolved:
            return []
        if len(resolved) == 1:
            kind, obj = resolved[0]
            if kind == "application":
                return [f"Goto(app-{obj.id},s,1)"]  # type: ignore[attr-defined]
            return self.target_steps(kind, obj, True)
        # several destinations for one pattern: ring all phones in parallel
        phones = [obj for kind, obj in resolved if kind == "phone"]
        if not phones:
            kind, obj = resolved[0]
            return self.target_steps(kind, obj, True)
        group = CallGroup(name="impromptu", ringlength=None, strategy="ringall")
        targets = [phone_target(p, snap) for p in phones]  # type: ignore[arg-type]
        first = phones[0]
        target = RingTarget(
            dialstring="&".join(t.dialstring for t in targets if t.dialstring),
            vm_box=first.extension if first.vm_enabled else "",  # type: ignore[attr-defined]
            notify_email="",
            ringlength=group.ringlength,
        )
        return ring_steps(target, True)

    def multi_account_hosts(self) -> dict[int, str]:
        """Providers sharing a host get one shared incoming context (legacy
        sip_get_hosts_with_multiple_accounts); returns provider id -> context."""
        by_host: OrderedDict[str, list[Provider]] = OrderedDict()
        for p in self.snap.active_providers:
            if p.tech == "pjsip":
                by_host.setdefault(p.host.lower(), []).append(p)
        mapping: dict[int, str] = {}
        for idx, (host, providers) in enumerate(by_host.items()):
            if len(providers) < 2:
                continue
            name = f"prov-host-{idx}-in"
            ctx = self.ctx(name, f"several accounts at {host}")
            for p in providers:
                ctx.ext(p.username, [f"Goto(prov-{p.id}-in,s,1)"])
            first = providers[0]
            ctx.ext(CATCHALL_PATTERN, [f"Goto(prov-{first.id}-in,${{EXTEN}},1)"])
            ctx.ext("s", [f"Goto(prov-{first.id}-in,s,1)"])
            for p in providers:
                mapping[p.id] = name
        return mapping

    def build(self) -> str:
        snap = self.snap
        self.subroutines()
        self.internal()
        self.applications()
        self.rooms()
        self.ivr_menus()
        self.business_hours()
        for provider in snap.active_providers:
            self.provider_in(provider)
            self.provider_out(provider)
        self.multi_account_hosts()
        self.phone_contexts()

        out = [HEADER.format(version=snap.facts.version)]
        out.append("[general]\nstatic=yes\nwriteprotect=yes\nclearglobalvars=yes\n")
        out.append(f"[globals]\nPHONIX_LAN_IP={snap.facts.lan_ip}\nTRANSFER_CONTEXT=internal\n")
        for ctx in self.contexts.values():
            out.append(ctx.render())
        return "\n".join(out)


def provider_contexts(snap: Snapshot) -> dict[int, str]:
    """Inbound context of every provider endpoint (shared for multi-account hosts)."""
    builder = DialplanBuilder(snap)
    shared = builder.multi_account_hosts()
    return {p.id: shared.get(p.id, f"prov-{p.id}-in") for p in snap.providers}


def identify_providers(snap: Snapshot) -> set[int]:
    """Providers that get an IP based identify section (first one per host)."""
    seen: set[str] = set()
    out: set[int] = set()
    for p in snap.active_providers:
        if p.tech != "pjsip":
            continue
        host = p.host.lower()
        if host not in seen:
            seen.add(host)
            out.add(p.id)
    return out


def generate(snap: Snapshot) -> str:
    return DialplanBuilder(snap).build()
