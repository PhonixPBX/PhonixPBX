# Business Hours Out-of-Office Key and Special Periods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A BLF key on every phone shows and toggles the out-of-office state of a business hours object (temporary override, back to automatic on the second press), and business hours get an ordered list of special periods that can be switched on and off immediately, also from a phone key.

**Architecture:** Runtime state (permanent mode, temporary override, special period on/off) lives in AstDB so the dialplan works without the web app. The dialplan computes the automatic and effective state in per-object subroutines and sets `Custom:` device states that phones subscribe to via hints. A thread in `phonix monitor` re-evaluates every minute in Python (same rules), expires overrides, syncs the on/off switches back into SQLite and refreshes the lamps.

**Tech Stack:** Python 3.10, SQLAlchemy + Alembic, pydantic, FastAPI/Jinja/htmx, Asterisk 22 dialplan (`func_db`, `func_devstate`), AMI.

**Spec:** `docs/superpowers/specs/2026-10-24-business-hours-key-and-special-periods-design.md`

## Global Constraints

- Every function in `phonix/` fully annotated, Python 3.10 style; ruff line length 120; `ruff check`, `ruff format --check phonix tests`, `mypy phonix` clean.
- User-facing errors: `ServiceError(message, fields={field: msg})`; mutations write `audit(...)`; config changes `mark_dirty(session, "dialplan")`. Runtime switches (mode, override, special on/off) never mark dirty.
- UI strings with `_()` / `N_()` and named placeholders only; audit summaries, logs, JSON API errors, CLI output and generated config are not translated.
- No inline scripts (CSP); behaviour via `data-*` in `static/phonix.js` (reuse `data-add-row`, `data-remove-row`, `data-move`, `data-sortable-item`).
- Precedence (spec): 1 permanent mode → 2 temporary override → 3 first applying special period in list order → 4 holiday → 5 weekly ranges. "Automatic" = 3–5.
- Temporary override expires when its date is not today **or** the automatic state equals its value (spec goal 3).
- Lamp: `INUSE` = closed / switched on, `NOT_INUSE` = open / switched off. No ringing/blinking states.
- Special period → business hours only one level deep; the target has no special periods and is not the object itself.
- Commit messages `area: lowercase summary` (e.g. `hours: ...`, `dialplan: ...`, `ui: ...`). `CHANGELOG.md` entry committed together with the user-visible change.

## Review Focus

- A yearly period crossing the new year (24.12.–02.01.) must apply on 31.12. and 01.01. and not on 03.01. — Python and dialplan (tests in Task 2 and Task 4).
- An override set before midnight is expired after midnight even if the monitor thread did not run (dialplan purges it itself) — tests in Task 2 and Task 4.
- Asterisk down: UI/API/MCP switches raise `ServiceError("Asterisk is not running…")`, status shows mode `None`, the monitor thread logs and retries instead of dying — tests in Task 3 and Task 5.
- Deleting business hours B that a special period of A points to leaves A's period on hangup and generates no `Gosub` to a missing context — test in Task 1 and Task 4.
- Editing business hours keeps special period ids (AstDB keys and hints stay valid); importing a backup never reuses foreign ids — tests in Task 1 and Task 6.

---

### Task 1: Special periods model, migration and service validation

**Files:**
- Modify: `phonix/core/models.py` (after `BusinessHoursHoliday`), relationship on `BusinessHours`
- Create: `phonix/core/migrations/versions/0008_hours_special_periods.py`
- Modify: `phonix/services/hours.py` (schemas, `_check`, `_apply`, `to_dict`)
- Modify: `phonix/services/destinations.py` (`SpecialType`, `SPECIAL_TYPES`, `forget`)
- Modify: `phonix/services/common.py` (`ensure_extension_free`, `extension_owner`)
- Test: `tests/test_ivr.py`, `tests/test_migrate.py` (existing `test_migrations_match_models` must stay green)

**Interfaces:**
- Produces: model `BusinessHoursSpecial` (`__tablename__ = "business_hours_specials"`): `id`, `hours_id` (FK cascade), `position: int`, `name: str(80)`, `enabled: bool = False`, `start: date | None`, `end: date | None`, `yearly: bool = False`, `feature_code: str(16) | None` (unique), `dest_type: str(16)`, `dest_id: int | None`. `BusinessHours.specials` relationship ordered by `position`, cascade delete-orphan, `lazy="selectin"`.
- Produces: `hours.SpecialIn` (pydantic, `extra="ignore"`): `id: int | None = None`, `name`, `enabled: bool = False`, `start: dt.date | None = None`, `end: dt.date | None = None`, `yearly: bool = False`, `feature_code: str = ""`, `dest_type: dst.SpecialType`, `dest_id: int | None = None`. `BusinessHoursIn.specials: list[SpecialIn] = Field(default_factory=list, max_length=50)`. `to_dict()` adds `"specials": [{"id", "name", "enabled", "start" (iso or None), "end", "yearly", "feature_code", "dest_type", "dest_id"}]` in position order.
- Produces: `dst.SpecialType = Literal[*HoursType args, "hours"]`, `dst.SPECIAL_TYPES`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ivr.py`:

```python
def test_special_periods_validation(session, ids):
    office = ids["office"]
    target = hours.create_hours(session, _hours(name="Christmas"))
    # start and end both or neither
    with pytest.raises(ServiceError) as exc:
        hours.create_hours(session, _hours(specials=[{"name": "x", "start": "2026-12-24", "dest_type": "hangup"}]))
    assert "specials.0" in exc.value.fields
    # one level: a target must not have special periods, and not be itself
    a = hours.create_hours(session, _hours(name="A", specials=[{"name": "xmas", "dest_type": "hours", "dest_id": target.id}]))
    with pytest.raises(ServiceError) as exc:
        hours.update_hours(session, target.id, _hours(name="Christmas", specials=[{"name": "y", "dest_type": "hangup"}]))
    assert "specials" in exc.value.fields
    with pytest.raises(ServiceError):
        hours.create_hours(session, _hours(name="B", specials=[{"name": "z", "dest_type": "hours", "dest_id": a.id}]))
    # feature codes are unique across extensions and other feature codes
    with pytest.raises(ServiceError) as exc:
        hours.update_hours(session, a.id, _hours(name="A", specials=[{"name": "e", "dest_type": "hangup", "feature_code": "*31"}]))
    assert "specials.0.feature_code" in exc.value.fields


def test_special_periods_keep_ids_and_order(session, ids):
    h = hours.create_hours(session, _hours(specials=[
        {"name": "Emergency", "dest_type": "hangup", "feature_code": "*70"},
        {"name": "Xmas", "start": "2026-12-24", "end": "2027-01-02", "yearly": True, "dest_type": "hangup"},
    ]))
    first, second = [s.id for s in h.specials]
    data = hours.to_dict(h)
    data["specials"].reverse()
    hours.update_hours(session, h.id, hours.BusinessHoursIn.model_validate(data))
    session.expire_all()
    assert [(s.id, s.position) for s in hours.get_hours(session, h.id).specials] == [(second, 0), (first, 1)]


def test_deleting_target_hours_falls_back_to_hangup(session, ids):
    target = hours.create_hours(session, _hours(name="Christmas"))
    a = hours.create_hours(session, _hours(name="A", specials=[{"name": "x", "dest_type": "hours", "dest_id": target.id}]))
    hours.delete_hours(session, target.id)
    session.expire_all()
    assert (hours.get_hours(session, a.id).specials[0].dest_type, hours.get_hours(session, a.id).specials[0].dest_id) == ("hangup", None)
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_ivr.py -k special -q` — Expected: FAIL (`specials` unknown / no model).

- [ ] **Step 3: Implement** the model, migration `0008` (revises `0007`, mirrors the model exactly), `SpecialIn` with a `model_validator` for start/end both-or-neither and `start <= end` unless `yearly` (yearly may wrap the new year), and in `_check`: `dst.check` per period (`field=f"specials.{idx}.dest"`), feature code via `ensure_extension_free` (`field=f"specials.{idx}.feature_code"`, pickup-prefix check as for the hours code, also distinct from the object's own feature code and the other periods), and the one-level rule (error on `"specials"` or `f"specials.{idx}.dest"`). `_apply` updates periods **in place by `id`** (only ids belonging to this object; unknown ids are treated as new), creates new ones, deletes missing ones, sets `position` from list order. Add `BusinessHoursSpecial.feature_code` to `ensure_extension_free` / `extension_owner`. `forget()` resets periods pointing at the deleted destination to `("hangup", None)`.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_ivr.py tests/test_migrate.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** `hours: special periods data model and validation`

---

### Task 2: Runtime state and evaluation in Python

**Files:**
- Modify: `phonix/generators/dialplan.py` (constants only, next to `HOURS_DB`)
- Modify: `phonix/services/hours.py` (`Runtime`, parsing, `automatic`, `status`, `live_status`)
- Modify: `phonix/web/routes/ui/ivr.py` (`_status_rows`), `phonix/web/templates/macros/hours.html` callers only if signatures need it
- Modify: `tests/conftest.py` (`FakeAmi.command`: support `database show <family>` → lines `/<family>/<key>    : <value>`)
- Test: `tests/test_ivr.py` (rewrite `test_hours_status` to the new signature)

**Interfaces:**
- Produces in `phonix/generators/dialplan.py`: `OVERRIDE_DB = "phonix-hours-tmp"`, `SPECIAL_DB = "phonix-special"`, `def hours_device(hours_id: int) -> str` → `"Custom:phonix-hours-<id>"`, `def special_device(special_id: int) -> str` → `"Custom:phonix-special-<id>"`.
- Produces in `phonix/services/hours.py`:
  - `@dataclass class Runtime: modes: dict[int, str]; overrides: dict[int, tuple[str, dt.date]]; active: dict[int, bool]` (all default empty).
  - `def parse_override(value: str) -> tuple[str, dt.date] | None` — AstDB value format `"<open|closed>:<YYYY-MM-DD>"`.
  - `def read_runtime(client: ami.AmiClient) -> Runtime` (via `database show` of the three families; special values `"1"`/`"0"`).
  - `def load_runtime() -> Runtime | None` (`None` when AMI unreachable).
  - `def special_on(p: BusinessHoursSpecial, rt: Runtime) -> bool` → `rt.active.get(p.id, p.enabled)`.
  - `def special_matches(p: BusinessHoursSpecial, day: dt.date) -> bool`.
  - `def automatic(hours: BusinessHours, rt: Runtime, now: dt.datetime, others: Mapping[int, BusinessHours]) -> dict[str, Any]` → `{"open": bool, "reason": "special"|"holiday"|"schedule", "holiday": str|None, "special": str|None, "special_id": int|None, "until": dt.date|None}`; a period pointing to hours B uses `status(B, …)["open"]`.
  - `def status(hours: BusinessHours, rt: Runtime, now: dt.datetime, others: Mapping[int, BusinessHours]) -> dict[str, Any]` → automatic fields plus `"reason"` overwritten by `"forced"` / `"override"`, `"override": "open"|"closed"|None`, `"reverts_to": bool|None` (automatic open-state while overridden). Expired overrides are ignored.
  - `live_status(session, hours_id, now=None)` keeps its signature; adds `"override"` and `"specials": [{"id", "name", "active", "applies", "feature_code"}]`; `"mode"` stays `None` when AMI is unreachable.

- [ ] **Step 1: Write the failing tests** — replace the parametrized `test_hours_status` (same cases, `hours.Runtime(modes={office: mode})` for non-auto modes) and add:

```python
def test_override_expires(session, ids):
    office = hours.get_hours(session, ids["office"])
    mon9 = dt.datetime(2026, 10, 19, 9, 0)
    rt = hours.Runtime(overrides={office.id: ("closed", mon9.date())})
    assert (hours.status(office, rt, mon9, {})["open"], hours.status(office, rt, mon9, {})["reason"]) == (False, "override")
    # automatic reaches the overridden value at 17:30 -> override gone
    assert hours.status(office, rt, mon9.replace(hour=18), {})["reason"] == "schedule"
    # set yesterday -> expired at midnight
    rt = hours.Runtime(overrides={office.id: ("open", dt.date(2026, 10, 18))})
    assert hours.status(office, rt, dt.datetime(2026, 10, 19, 0, 5), {})["reason"] == "schedule"


@pytest.mark.parametrize("day, applies", [("2026-12-31", True), ("2027-01-01", True), ("2027-01-03", False), ("2026-12-23", False)])
def test_yearly_special_crosses_new_year(session, ids, day, applies):
    h = hours.create_hours(session, _hours(specials=[{"name": "Xmas", "enabled": True, "start": "2025-12-24", "end": "2026-01-02", "yearly": True, "dest_type": "hangup"}]))
    assert hours.special_matches(h.specials[0], dt.date.fromisoformat(day)) is applies


def test_precedence_first_applying_special_wins(session, ids):
    target = hours.create_hours(session, _hours(name="Morning", ranges=[{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(7)]))
    h = hours.create_hours(session, _hours(specials=[
        {"name": "Emergency", "enabled": False, "dest_type": "hangup"},
        {"name": "Xmas", "enabled": True, "start": "2026-12-24", "end": "2027-01-02", "dest_type": "hours", "dest_id": target.id},
    ]))
    others = {target.id: target}
    xmas10 = dt.datetime(2026, 12, 28, 10, 0)
    st = hours.status(h, hours.Runtime(), xmas10, others)
    assert (st["open"], st["reason"], st["special"]) == (True, "special", "Xmas")
    emergency = h.specials[0].id
    st = hours.status(h, hours.Runtime(active={emergency: True}), xmas10, others)
    assert (st["open"], st["special"]) == (False, "Emergency")
    # the key (override) sits above every special period
    st = hours.status(h, hours.Runtime(active={emergency: True}, overrides={h.id: ("open", xmas10.date())}), xmas10, others)
    assert (st["open"], st["reason"]) == (True, "override")


def test_read_runtime(fake_ami):
    fake_ami.astdb = {("phonix-hours", "1"): "closed", ("phonix-hours-tmp", "2"): "open:2026-10-24", ("phonix-special", "5"): "1"}
    from phonix import ami
    with ami.AmiClient() as c:
        rt = hours.read_runtime(c)
    assert rt == hours.Runtime(modes={1: "closed"}, overrides={2: ("open", dt.date(2026, 10, 24))}, active={5: True})
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_ivr.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces above; update `_status_rows` in `routes/ui/ivr.py` to load the runtime once (`load_runtime()`, `Runtime()` + mode `None` when unreachable) and pass `others = {h.id: h for h in list}`; update `live_status` callers in `api.py` / `mcp.py` only if needed (signature unchanged).
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_ivr.py tests/test_web.py tests/test_mcp.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** `hours: evaluate special periods and temporary overrides`

---

### Task 3: Live switches and lamps from the services

**Files:**
- Modify: `phonix/services/hours.py`
- Test: `tests/test_ivr.py`

**Interfaces:**
- Consumes: Task 2 `Runtime`, `read_runtime`, `status`, device name helpers.
- Produces:
  - `def refresh_lamps(session: Session, client: ami.AmiClient, rt: Runtime, now: dt.datetime) -> None` — `devstate change <device> INUSE|NOT_INUSE` (AMI CLI) for every hours object with a feature code and every special period with a feature code.
  - `set_mode(session, hours_id, mode, user="") -> str` additionally deletes `OVERRIDE_DB/<id>` and calls `refresh_lamps`.
  - `def set_special_active(session: Session, hours_id: int, special_id: int, active: bool, user: str = "") -> bool` — writes `SPECIAL_DB/<sid>` = `1`/`0`, sets `special.enabled` in SQLite **without** `mark_dirty`, audits `"special"` (`f"{hours.name}/{special.name}: on|off"`), refreshes lamps; `NotFound` if the period does not belong to the object; `ServiceError(_("Asterisk is not running, the mode cannot be changed: %(error)s", …))` when AMI fails (reuse the existing message).

- [ ] **Step 1: Write the failing tests:**

```python
def test_set_mode_clears_override_and_sets_lamp(session, ids, fake_ami):
    office = ids["office"]
    fake_ami.astdb[("phonix-hours-tmp", str(office))] = f"open:{dt.date.today()}"
    hours.set_mode(session, office, "closed", "admin")
    assert ("phonix-hours-tmp", str(office)) not in fake_ami.astdb
    assert ("Command", {"Command": f"devstate change Custom:phonix-hours-{office} INUSE"}) in fake_ami.actions


def test_set_special_active(session, ids, fake_ami):
    h = hours.create_hours(session, _hours(specials=[{"name": "Emergency", "dest_type": "hangup", "feature_code": "*70"}]))
    sid = h.specials[0].id
    hours.set_special_active(session, h.id, sid, True, "admin")
    assert fake_ami.astdb[("phonix-special", str(sid))] == "1"
    assert hours.get_hours(session, h.id).specials[0].enabled is True
    assert ("Command", {"Command": f"devstate change Custom:phonix-special-{sid} INUSE"}) in fake_ami.actions
    with pytest.raises(NotFound):
        hours.set_special_active(session, ids["office"], sid, False, "admin")


def test_set_special_active_without_asterisk(session, ids):
    h = hours.create_hours(session, _hours(specials=[{"name": "E", "dest_type": "hangup"}]))
    with pytest.raises(ServiceError, match="Asterisk is not running"):
        hours.set_special_active(session, h.id, h.specials[0].id, True, "admin")
```
(Import `NotFound` from `phonix.services.common`; check that `mark_dirty` was not called by asserting no pending dialplan area, using the helper `test_ivr.py`/`test_services.py` already use for dirty areas.)

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_ivr.py -k "lamp or special_active or set_mode" -q` — Expected: FAIL.
- [ ] **Step 3: Implement.** Also make `update_hours` push changed `enabled` values to AstDB best-effort (ignore AMI errors: the monitor will reconcile) so an edit form save and the AstDB agree.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_ivr.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** `hours: switch special periods and refresh the phone lamps`

---

### Task 4: Dialplan — subroutines, routing, feature codes, hints

**Files:**
- Modify: `phonix/generators/dialplan.py` (`business_hours()`, the feature-code block in the `internal` builder, the hints block)
- Modify: golden files under `tests/golden/` (`UPDATE_GOLDEN=1`)
- Test: `tests/test_ivr.py` (`test_dialplan` and new tests), `tests/test_generators.py`

**Interfaces:**
- Consumes: constants and device helpers from Task 2.
- Produces contexts per business hours object (decided here; tests and the integration test rely on them):
  - `[hours-<id>-auto]` `s`: computes levels 3–5, `Return(<open|closed>-<special id or 0>)`. Special periods in `position` order: skip when off (`${DB(phonix-special/<sid>)}`, empty → generated configured `enabled` default) or not matching today (`STRFTIME(${EPOCH},,%Y-%m-%d)`; yearly compares `%m-%d`, with an OR across the new year when start > end). A matching period pointing to hours B returns B's state from `Gosub(hours-<B>-state,s,1)`, else `closed`.
  - `[hours-<id>-state]` `s`: permanent mode → `forced`; else automatic via Gosub; override from `phonix-hours-tmp/<id>` is deleted (`DB_DELETE`) when its date ≠ today or its value = automatic, otherwise → `override`; `Return(<open|closed>-<forced|override|auto>-<special id or 0>)`.
  - `[hours-<id>-lamp]` `s`: Gosub state, `Set(DEVICE_STATE(Custom:phonix-hours-<id>)=INUSE|NOT_INUSE)`, `Return()`.
  - `[hours-<id>]` / `[hours-<id>-pub]` `s`: Gosub state; `forced`/`override` → open/closed destination; `auto` with special id ≠ 0 → that period's destination (`hours` → `Goto(hours-<B>[-pub],s,1)`); else open/closed destination.
  - In `internal`: `exten => <hours code>,hint,Custom:phonix-hours-<id>` and `exten => <special code>,hint,Custom:phonix-special-<sid>`.
  - Hours feature code (`internal`), steps in this order:

```
Answer()
AUTO = CUT(Gosub hours-<id>-auto, "-", 1)
Gosub hours-<id>-state              ; purges an expired override first
PERM = DB(phonix-hours/<id>) ; TMP = DB(phonix-hours-tmp/<id>)
if PERM != "":  DB_DELETE(perm); if PERM == AUTO: DB(tmp) = opposite(AUTO):today -> announce opposite(AUTO)
                                  else -> announce automatic
elif TMP != "": DB_DELETE(tmp) -> announce automatic
else:           DB(tmp) = opposite(AUTO):today -> announce opposite(AUTO)
Gosub hours-<id>-lamp, then hours-<R>-lamp for every R whose special periods point to <id>
Hangup()
```
  - Special period feature code: current = `DB(phonix-special/<sid>)` (empty → configured default); store the opposite (`1`/`0`), `Set(DEVICE_STATE(Custom:phonix-special-<sid>)=…)`, Gosub lamp of the owning hours and of every R pointing to the owner, announce activated / de-activated, `Hangup()`.
  - Announcements: list the sound files in the dev container (`dev/test-asterisk.sh` image, `ls /usr/share/asterisk/sounds/en`) and pick existing ones for "closed", "open", "automatic"; `activated` / `de-activated` for special periods. Record the choice in `docs/SPEC.md` (Task 9).

- [ ] **Step 1: Write the failing tests** (string checks on `dialplan.generate(build_snapshot(session))`, in the style of `test_dialplan`):
  - `test_dialplan_hours_subroutines`: contexts `[hours-<office>-auto]`, `-state`, `-lamp` exist; `exten => *31,hint,Custom:phonix-hours-<office>` present; the routing context starts with a `Gosub(hours-<office>-state,s,1)`.
  - `test_dialplan_special_periods`: a yearly 24.12.–02.01. period produces a check that matches `12-24`…`12-31` **or** `01-01`…`01-02`; an off-by-default period with code `*70` produces `exten => *70,hint,Custom:phonix-special-<sid>` and a default of `0` when the AstDB entry is empty; a period pointing to hours B produces `Gosub(hours-<B>-state,s,1)` in A's `-auto` and `Goto(hours-<B>-pub,s,1)` in A's `-pub` routing.
  - `test_dialplan_override_purged_in_dialplan`: `-state` contains `DB_DELETE(phonix-hours-tmp/<id>)` guarded by the date/automatic comparison.
  - `test_dialplan_no_gosub_to_deleted_hours`: after deleting B (Task 1 fallback), A's generated dialplan contains no `hours-<B>`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_ivr.py -k dialplan -q` — Expected: FAIL.
- [ ] **Step 3: Implement**; keep `GotoIfTime` + `last_minute` for ranges and the date comparisons for holidays as today.
- [ ] **Step 4: Run** `UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_generators.py tests/legacy -q`, review the golden diff (only business hours contexts and hints change), then `.venv/bin/pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `dialplan: business hours override key, special periods and lamps`

---

### Task 5: Minute sync in `phonix monitor`

**Files:**
- Create: `phonix/services/hours_sync.py`
- Modify: `phonix/services/monitor.py` (`run_forever` starts the thread)
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `read_runtime`, `status`, `refresh_lamps`, constants (Tasks 2–3).
- Produces:
  - `def sync_once(session: Session, client: ami.AmiClient, now: dt.datetime) -> None` — reads the runtime; deletes expired overrides from AstDB; for each special period: AstDB value present and ≠ `enabled` → copy into SQLite (no `mark_dirty`, no audit); absent → write `enabled` to AstDB; deletes AstDB keys of ids that no longer exist (all three families); then `refresh_lamps` (every run, so an Asterisk restart is covered).
  - `def run_forever(interval: float = 60.0, stop: threading.Event | None = None) -> None` — loops `sync_once` in a `session_scope()` with a fresh `AmiClient`; on `ami.AmiError`/`OSError` logs at info and waits `interval`; never raises.
  - `monitor.run_forever()` starts `threading.Thread(target=hours_sync.run_forever, name="hours-sync", daemon=True)` before its loop.

- [ ] **Step 1: Write the failing tests:**

```python
def test_sync_once(session, fake_ami):  # uses factories.sample_pbx via the ids fixture pattern of test_ivr.py
    ...
    # expired override removed, unknown ids removed, special switched by a phone copied into SQLite,
    # missing AstDB switch written, lamps set:
    assert ("phonix-hours-tmp", str(office)) not in fake_ami.astdb
    assert ("phonix-special", "999") not in fake_ami.astdb
    assert hours.get_hours(session, h.id).specials[0].enabled is True
    assert fake_ami.astdb[("phonix-special", str(other_sid))] == "0"
    assert any(a[1].get("Command", "").startswith(f"devstate change Custom:phonix-hours-{office}") for a in fake_ami.actions)


def test_run_forever_survives_ami_errors(monkeypatch):
    # AmiClient raising AmiError: run_forever with a stop event set after the first wait returns without raising
```
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_monitor.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_monitor.py tests/test_ivr.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** `monitor: keep business hours lamps and switches in sync`

---

### Task 6: Configuration backup version 5

**Files:**
- Modify: `phonix/services/configdoc.py` (`CONFIG_VERSION = 5`, `_upgrade_4` no-op with docstring "4 -> 5: business hours got special periods (optional, nothing to change)", `UPGRADES[4]`, import path)
- Test: `tests/test_configdoc.py`, `tests/test_backup.py` if it pins the version

**Interfaces:**
- Consumes: `BusinessHoursIn.specials` (Task 1).
- Produces: exported `business_hours[].specials` (via `to_dict`); on import, every special's `id` is set to `None` before `create_hours`, and special periods pointing to `hours` are resolved like the other destinations in the second pass of `menus_and_hours` (first pass creates them with `dest_type="hangup"`, second pass `update_hours` with mapped ids).

- [ ] **Step 1: Write the failing tests:** round trip of a doc with two periods (one pointing to other hours) yields the same names/order/flags/codes and a mapped `dest_id`; a version-4 document still imports; importing into a database where special id 1 already exists does not touch that period.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_configdoc.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_configdoc.py tests/test_backup.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** `backup: special periods in config.json version 5`

---

### Task 7: REST API and MCP

**Files:**
- Modify: `phonix/web/routes/api.py`, `phonix/mcp.py` (tool list and instructions text mentioning immediate tools)
- Test: `tests/test_ivr.py` (REST/MCP section), `tests/test_mcp.py` if it lists tools

**Interfaces:**
- Consumes: `set_special_active`, `live_status` (Tasks 2–3).
- Produces: `PUT /api/v1/business-hours/{hours_id}/special/{special_id}` with body `{"active": bool}` → `live_status`; MCP write tool `set_business_hours_special` (`id`, `special_id`, `active`) → `live_status`. Read-only tokens rejected like `set_business_hours_mode`.

- [ ] **Step 1: Write the failing tests** mirroring the existing mode endpoint/tool tests: success with `fake_ami`, 404 for a foreign period, read-only token refused, MCP tool listed only for write tokens.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_ivr.py tests/test_mcp.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same — Expected: PASS.
- [ ] **Step 5: Commit** `api: switch special periods of business hours`

---

### Task 8: Web UI

**Files:**
- Modify: `phonix/web/routes/ui/ivr.py` (`_hours_form_data`, `_hours_page` choices for `dst.SPECIAL_TYPES`, new `POST /dialplan/hours/{id}/special/{sid}`)
- Modify: `phonix/web/templates/pages/hours_form.html` (card "Special periods" below holidays; rows with hidden `sp_id_<i>`, `sp_name_<i>`, `sp_enabled_<i>`, `sp_start_<i>`, `sp_end_<i>`, `sp_yearly_<i>`, `sp_code_<i>`, `sp_dest_<i>`; `data-sortable-item` + up/down `data-move` buttons as in `partials/ivr_option_row.html`; feature-code help text updated for the new toggle behaviour)
- Modify: `phonix/web/templates/partials/hours_mode.html` (on/off toggle per period, hx-post to the new route, current reason)
- Modify: `phonix/web/templates/macros/hours.html` (reasons `special` with name and "until <date>", `override` with "until the next change")
- Modify: `phonix/web/templates/pages/hours.html` (status column shows the new reasons; per period an on/off toggle posting to the same route)
- Modify: `CHANGELOG.md` `## [Unreleased]` (entries listed in Task 9, committed here with the UI)
- Test: `tests/test_ivr.py` (web section, next to `test_hours_form`)

**Interfaces:**
- Consumes: Tasks 1–3.

- [ ] **Step 1: Write the failing tests:** posting the form with two period rows (reversed order on the second save) stores them in that order and keeps ids; the edit page renders the period rows and the toggles; `POST /dialplan/hours/{id}/special/{sid}` with `active=true` and the CSRF header switches it (fake_ami) and returns the partial; the list page shows "Xmas" as the reason while a period applies (freeze time with `monkeypatch` on `dt.datetime` as the existing tests do, or assert via `status` rows).
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_ivr.py -k "form or special" -q` — Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `scripts/i18n.sh update` and dispatch the `i18n-translator` agent to fill all 11 catalogs.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` (includes `tests/test_i18n.py`) — Expected: PASS.
- [ ] **Step 5: Commit** `ui: special periods and override status for business hours` (with the catalogs and the CHANGELOG entries)

---

### Task 9: Integration test, manual, changelog, spec

**Files:**
- Modify: `tests/integration/test_asterisk.py` (`test_business_hours_mode_and_feature_code` → new behaviour)
- Modify: `docs/manual/content/{en,de}/dialplan/hours.md` (special periods, precedence, Snom BLF key setup: function key type "BLF", number = feature code), rebuild with `scripts/help-build.sh`
- `CHANGELOG.md` (written in Task 8; adjust if needed): *Added* out-of-office key with lamp (*Dialplan → Business Hours*), special periods with their own feature codes and lamps; *Changed* the feature code now toggles a temporary override (until the next change, at midnight at the latest) and lifts a permanent mode instead of switching closed ⇄ automatic
- Modify: `docs/SPEC.md` (data model `business_hours_specials`; business hours feature paragraph incl. precedence; API/MCP list; implementation notes for AstDB families `phonix-hours-tmp`, `phonix-special`, device names, the subroutine contexts and the chosen sound files; backup format version 5)

- [ ] **Step 1: Update the integration test:** dial the hours feature code via `channel originate Local/<code>@internal`; assert `database get phonix-hours-tmp <id>` holds the opposite of the automatic state with today's date and `core show hint <code>` reports `InUse`/`Idle` accordingly; dial again → entry gone; with a permanent mode set equal to automatic, a press sets an override to the opposite; a special period code toggles `phonix-special/<sid>` and its hint.
- [ ] **Step 2: Run** `dev/test-asterisk.sh` — Expected: PASS.
- [ ] **Step 3: Write manual (de/en) and SPEC, review the CHANGELOG entries**; run `scripts/help-build.sh`; follow the `ui-change-checklist` skill.
- [ ] **Step 4: Run** `.venv/bin/ruff check . && .venv/bin/ruff format --check phonix tests && .venv/bin/mypy phonix && .venv/bin/pytest -q` — Expected: all clean.
- [ ] **Step 5: Commit** `hours: manual, changelog and spec for the out-of-office key and special periods`
