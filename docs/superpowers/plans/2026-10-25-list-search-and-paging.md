# List search and paging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every list page in the web UI gets a search field that filters as you type, paging with a page size choice and the view in the URL. The REST API and MCP list endpoints get the same search and paging.

**Architecture:** One service-level module, `phonix/services/listing.py`, does the matching (casefold substring over per-entity fields), the paging maths and the URL query, and the UI, REST and MCP all go through it. Entity lists are filtered and sliced in Python after their existing `list_*` query, so the order stays the same. The audit log filters and pages in SQL, using a `casefold()` SQLite function. In the UI, every list page always renders as a full page; htmx requests use `hx-select` to pick out the list region, and an out-of-band swap updates the count. That means no server-side fragment branching, and boosted navigation and history restore keep working unchanged.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy 2 / SQLite, Jinja2, htmx 4.0.0, Tabler 1.7.1, pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-list-search-and-paging-design.md`

## Global Constraints

- UI URL parameters are `q`, `page` (1-based) and `per_page`, with values `25`, `50`, `100` or `all`. Anything else falls back to `50`. Defaults (`q=""`, `page=1`, `per_page=50`) are left out of generated URLs.
- The audit log offers `25`, `50` and `100` per page. On the audit log, `per_page=all` falls back to `50`.
- REST and MCP use `q`, `limit` and `offset`. Without `limit` all matches are returned. Without any parameter the behaviour is unchanged.
- The REST list body stays a JSON array. The `X-Total-Count` header (the number of matches before `limit`/`offset`) is sent on every list response.
- MCP list tools return `{"items": [...], "total": N}`.
- Matching is case-insensitive substring matching via `str.casefold()` ("müller" finds "Müller"). SQL must not use SQLite `LIKE`/`ilike` folding.
- Search typing waits about 300 ms after the last keystroke. Typing uses `hx-replace-url`, while page links and the page size use `hx-push-url`. A new search returns to page 1, and a page past the end shows the last page.
- Highlighting escapes the text before inserting `<mark>`. No user text reaches the page unescaped.
- The CSP forbids inline scripts and `eval`. Use no htmx trigger filters (`[...]`), because they evaluate JS.
- Every function in `phonix/` is fully annotated (Python 3.10 style). Ruff line length is 120.
- Every new UI string uses `_()`/`ngettext` with named placeholders. Run `scripts/i18n.sh update` and fill all 11 catalogs with the `i18n-translator` agent. Update the manual in en and de, then run `scripts/help-build.sh`. Each user-visible change gets a CHANGELOG entry under `## [Unreleased]`. Keep `docs/SPEC.md` in step.
- Commit messages follow `area: lowercase summary`.

## Review Focus

1. **Search term with HTML or regex characters** (`<b>`, `a.b`, `(`, `%`, `_`): it must match literally, never break the page, and appear escaped in the field, in the highlight and in the URLs. The tests live in Task 1 (`test_highlight_escapes`, `test_search_literal_characters`) and Task 5 (`test_audit_search_like_wildcards`).
2. **Status polling on a filtered or paged phone list**: the poll must report only the visible rows, and after a search it must carry the new query. The test is in Task 3 (`test_phone_status_follows_view`).
3. **Media upload while a search is active**: the table returned after an upload must keep working, with a region id that matches the page. The test is in Task 4 (`test_media_upload_returns_list_region`).
4. **A page number past the end, zero, negative or not a number** (`page=0`, `page=-3`, `page=x`, `page=999`): it must clamp to a valid page and never return 500. The tests are in Task 1 (`test_page_of_clamps`) and Task 3 (`test_phone_list_bad_params`).
5. **Unchanged REST clients**: `GET /api/v1/phones` without parameters must still return the full array in the same order. The test is in Task 2 (`test_api_list_unchanged_without_params`).

---

### Task 1: Listing core and SQLite casefold

**Files:**
- Create: `phonix/services/listing.py`
- Modify: `phonix/core/db.py` (`_on_connect`)
- Modify: `phonix/web/templating.py` (register the `highlight` filter)
- Test: `tests/test_listing.py`

**Interfaces:**
- Produces, all in `phonix/services/listing.py`:
  - `PER_PAGE_DEFAULT: int = 50`
  - `PER_PAGE_CHOICES: tuple[int | None, ...] = (25, 50, 100, None)`, where `None` means "all"
  - `PER_PAGE_NO_ALL: tuple[int | None, ...] = (25, 50, 100)`
  - `def matches(q: str, values: Iterable[object]) -> bool`: whether `q.casefold()` is a substring of `str(v).casefold()` for any non-`None` value. An empty or whitespace-only `q` matches everything. `q` is stripped.
  - `def search(items: Iterable[T], q: str, fields: Callable[[T], Iterable[object]]) -> list[T]`: keeps the input order.
  - `def parse_page(value: object) -> int`: a positive int, otherwise 1.
  - `def parse_per_page(value: object, choices: tuple[int | None, ...] = PER_PAGE_CHOICES) -> int | None`: `"all"` gives `None` only if `None` is in `choices`; a number in `choices` gives that number; anything else gives `PER_PAGE_DEFAULT`.
  - `@dataclass(frozen=True) class ListPage(Generic[T])` with fields `items: list[T]`, `matched: int`, `total: int`, `page: int`, `per_page: int | None`, `q: str`, `choices: tuple[int | None, ...]`, and these members:
    - properties `pages: int` (at least 1), `start: int` (1-based, 0 when `matched == 0`), `end: int`, `searching: bool` (`q != ""`)
    - `def page_links(self) -> list[int | None]`: first, last and current ±2, with `None` for each gap
    - `def query(self, **changes: object) -> str`: a urlencoded `q`/`page`/`per_page` without defaults (`per_page=None` becomes `all`), with `changes` applied. A change of `q` or `per_page` resets `page` to 1.
  - `def page_of(items: Sequence[T], total: int, q: str, page: int, per_page: int | None, choices: tuple[int | None, ...] = PER_PAGE_CHOICES) -> ListPage[T]`: `items` are the matches already; this clamps `page` into `1..pages` and slices.
  - `def slice_api(items: Sequence[T], offset: int, limit: int | None) -> list[T]`
- Produces, in `phonix/core/db.py`: the SQLite function `casefold(text)`, registered on every connection.
- Produces, in `phonix/web/templating.py`: the Jinja filter `highlight(text: object, q: str) -> Markup`. It escapes `text`, then wraps every case-insensitive occurrence of `q` (`re.escape`, `re.IGNORECASE`) in `<mark>`. For an empty `q` it returns the escaped text.

- [ ] **Step 1: Write the failing tests** in `tests/test_listing.py`

```python
from phonix.services import listing as ls

def test_matches_casefold_and_umlauts():
    assert ls.matches("mül", ["Anna Müller"]) and ls.matches("MEI", ["meier"])
    assert ls.matches("", ["x"]) and ls.matches("  ", [None])
    assert not ls.matches("x", [None, ""])

def test_search_literal_characters():
    items = ["a.b", "axb", "50%", "(x)", "<b>"]
    assert ls.search(items, ".", lambda s: [s]) == ["a.b"]
    assert ls.search(items, "%", lambda s: [s]) == ["50%"]
    assert ls.search(items, "(", lambda s: [s]) == ["(x)"]

def test_search_keeps_order():
    assert ls.search(["b1", "a1", "c2"], "1", lambda s: [s]) == ["b1", "a1"]

def test_parse_page_and_per_page():
    assert [ls.parse_page(v) for v in ("3", "0", "-2", "x", None)] == [3, 1, 1, 1, 1]
    assert ls.parse_per_page("100") == 100 and ls.parse_per_page("all") is None
    assert ls.parse_per_page("7") == 50 and ls.parse_per_page(None) == 50
    assert ls.parse_per_page("all", ls.PER_PAGE_NO_ALL) == 50

def test_page_of_clamps():
    items = list(range(120))
    p = ls.page_of(items, 500, "", 99, 50)
    assert (p.page, p.pages, p.start, p.end, p.items[0]) == (3, 3, 101, 120, 100)
    assert ls.page_of(items, 500, "", 0, 50).page == 1
    empty = ls.page_of([], 500, "zz", 1, 50)
    assert (empty.pages, empty.start, empty.end, empty.matched) == (1, 0, 0, 0)
    assert ls.page_of(items, 120, "", 1, None).items == items

def test_page_links():
    p = ls.page_of(list(range(500)), 500, "", 6, 50)
    assert p.page_links() == [1, None, 4, 5, 6, 7, 8, 9, 10]
    assert ls.page_of(list(range(100)), 100, "", 1, 50).page_links() == [1, 2]

def test_query():
    p = ls.page_of(list(range(500)), 500, "mei er", 2, 50)
    assert p.query() == "q=mei+er&page=2"
    assert p.query(page=3) == "q=mei+er&page=3"
    assert p.query(q="") == ""
    assert p.query(per_page=None) == "q=mei+er&per_page=all"

def test_slice_api():
    assert ls.slice_api(list(range(10)), 8, None) == [8, 9]
    assert ls.slice_api(list(range(10)), 2, 3) == [2, 3, 4]

def test_sqlite_casefold(session):
    from sqlalchemy import func, select
    assert session.scalar(select(func.casefold("ÄBC"))) == "äbc"

def test_highlight_escapes():
    from phonix.web.templating import templates
    hl = templates.env.filters["highlight"]
    assert str(hl("<b>Meier</b>", "mei")) == "&lt;b&gt;<mark>Mei</mark>er&lt;/b&gt;"
    assert str(hl("a.b axb", ".")) == "a<mark>.</mark>b axb"
    assert str(hl("x", "")) == "x"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_listing.py -q`
Expected: FAIL (`ModuleNotFoundError: phonix.services.listing`). If the `session` fixture does not exist in `tests/conftest.py`, use the fixture the existing service tests use (`tests/test_services.py`).

- [ ] **Step 3: Implement `phonix/services/listing.py`** with the interfaces above. `page_links` for 1 to 7 pages lists every page.

- [ ] **Step 4: Register `casefold` in `phonix/core/db.py` `_on_connect`:** `dbapi_conn.create_function("casefold", 1, lambda s: s.casefold() if isinstance(s, str) else s, deterministic=True)`.

- [ ] **Step 5: Add the `highlight` filter** in `phonix/web/templating.py` next to the other filters (`templates.env.filters["highlight"] = _highlight`). Use `markupsafe.escape` on each non-matching and matching part.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_listing.py -q && .venv/bin/ruff check phonix tests && .venv/bin/mypy phonix`
Expected: all pass, `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add phonix/services/listing.py phonix/core/db.py phonix/web/templating.py tests/test_listing.py
git commit -m "lists: search and paging helpers"
```

---

### Task 2: Search fields per entity, REST and MCP

**Files:**
- Modify: `phonix/services/phones.py`, `providers.py`, `dialplan.py`, `ivr.py`, `hours.py`, `manager.py`, `media.py`, `users.py`, `tokens.py`, `backup.py` (one `search_fields` function each)
- Modify: `phonix/services/resources.py` (`Resource.search_fields`)
- Modify: `phonix/web/routes/api.py` (`crud` → `list_items`)
- Modify: `phonix/mcp.py` (`_resource_tools` → `list_items` and the tool's properties)
- Modify: `docs/SPEC.md` (the API/MCP section), `CHANGELOG.md`
- Test: `tests/test_web.py` (API), `tests/test_mcp.py`

**Interfaces:**
- Consumes: `listing.search`, `listing.slice_api`.
- Produces: one search function per entity. The return type is `tuple[object, ...]`, the parameter is the model, and the order of the values does not matter:
  - `phones.search_fields(p: Phone)` returns `(p.extension, p.callerid, p.description)`
  - `providers.search_fields(p: Provider)` returns `(p.name, p.host, p.username)`
  - `dialplan.application_search_fields(a: Application)` returns `(a.extension, a.name, a.description)`
  - `dialplan.callgroup_search_fields(g: CallGroup)` returns `(g.extension, g.name)`
  - `dialplan.room_search_fields(r: ConferenceRoom)` returns `(r.number, r.name)`
  - `ivr.search_fields(m: IvrMenu)` returns `(m.extension, m.name, m.description)`
  - `hours.search_fields(h: BusinessHours)` returns `(h.name, h.description, h.feature_code)`
  - `manager.search_fields(u: AmiUser)` returns `(u.username,)`
  - `media.search_fields(f: MediaFile)` returns `(f.name, f.kind, <translated kind label>)`; use `KINDS[f.kind]` translated with `_()`
  - `users.search_fields(u: User)` returns `(u.username,)`
  - `tokens.search_fields(t: ApiToken)` returns `(t.name, t.prefix, t.user.username if t.user else "")`
  - `backup.search_fields(p: Path)` returns `(p.name,)`
- Produces: `Resource.search_fields: Callable[[Any], Iterable[object]]`, a new required field placed before the optional ones, set for all 8 resources.
- Produces, REST: `GET <path>?q=&limit=&offset=` gives the JSON array plus the `X-Total-Count` header. `limit` is `int | None` with `ge=1`, `offset` is `int` with `ge=0`, both declared with `Query` so they appear in OpenAPI.
- Produces, MCP: list tool properties `q` (string), `limit` (integer ≥ 1) and `offset` (integer ≥ 0), all optional. The result is `{"items": [...], "total": <matches>}`. Invalid types raise `ToolInputError` (use `_int`/`_str`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`:

```python
def test_api_list_unchanged_without_params(client):
    auth = bearer(read_only=True)
    r = client.get("/api/v1/phones", headers=auth)
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert int(r.headers["X-Total-Count"]) == len(r.json())
    assert [p["extension"] for p in r.json()] == sorted((p["extension"] for p in r.json()), key=lambda e: (len(e), e))

def test_api_list_search_and_paging(client):
    auth = bearer(read_only=True)
    every = client.get("/api/v1/phones", headers=auth).json()
    name = every[0]["callerid"]
    r = client.get("/api/v1/phones", params={"q": name.upper()}, headers=auth)
    assert any(p["id"] == every[0]["id"] for p in r.json())
    r = client.get("/api/v1/phones", params={"limit": 1, "offset": 1}, headers=auth)
    assert [p["id"] for p in r.json()] == [every[1]["id"]] and r.headers["X-Total-Count"] == str(len(every))
    assert client.get("/api/v1/phones", params={"limit": 0}, headers=auth).status_code == 422
    assert "q" in str(client.get("/api/v1/openapi.json").json()["paths"]["/api/v1/phones"]["get"]["parameters"])

def test_every_resource_has_search_fields():
    from phonix.services.resources import RESOURCES
    assert all(callable(r.search_fields) for r in RESOURCES)
```

In `tests/test_mcp.py`, reuse its `call()` helper and its existing auth header fixture:

```python
def test_list_tool_search_and_paging(client):
    every = call(client, "list_phones", AUTH)          # adapt AUTH to the file's token fixture
    assert set(every) == {"items", "total"} and every["total"] == len(every["items"])
    page = call(client, "list_phones", AUTH, limit=1, offset=1)
    assert page["items"] == every["items"][1:2] and page["total"] == every["total"]
    found = call(client, "list_phones", AUTH, q=every["items"][0]["extension"])
    assert every["items"][0] in found["items"]
```

Then update the existing tests that read MCP `list_*` results as bare lists, so they read `["items"]`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web.py -k "api_list or search_fields" tests/test_mcp.py -q`
Expected: FAIL (no `X-Total-Count`; MCP returns a list; `Resource` has no `search_fields`).

- [ ] **Step 3: Add the search functions and `Resource.search_fields`**, then wire `list_items` in `api.py`. Use `listing.search(res.list_fn(db), q, res.search_fields)` and set the header through a `response: Response` parameter. Wire MCP `list_items` and its properties the same way.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web.py tests/test_mcp.py -q && .venv/bin/mypy phonix`
Expected: PASS.

- [ ] **Step 5: Docs.**
  - **`docs/SPEC.md`:** in the REST/MCP section, describe the `q`/`limit`/`offset` parameters, `X-Total-Count` and the MCP `{"items", "total"}` result.
  - **`CHANGELOG.md`, Added:** "REST API: list endpoints accept `q` (search), `limit` and `offset`; the `X-Total-Count` header carries the number of matches."
  - **`CHANGELOG.md`, Changed:** "MCP: the `list_*` tools return `{"items": [...], "total": N}` instead of a bare list and accept `q`, `limit` and `offset`. Clients that read the result as a list need to read `items`."

- [ ] **Step 6: Commit**

```bash
git add phonix/services phonix/web/routes/api.py phonix/mcp.py tests/test_web.py tests/test_mcp.py docs/SPEC.md CHANGELOG.md
git commit -m "api: search and paging for list endpoints and mcp list tools"
```

---

### Task 3: UI building blocks and the phone list

**Files:**
- Create: `phonix/web/templates/macros/lists.html`
- Modify: `phonix/web/routes/ui/common.py` (`list_page`)
- Modify: `phonix/web/routes/ui/accounts.py` (`phone_list`, `phone_status`)
- Modify: `phonix/web/templates/pages/phones.html`, `partials/phone_row.html`, `partials/phone_status.html`
- Modify: `phonix/web/static/phonix.css` (`mark` in tables, header layout) only if Tabler's defaults do not fit
- Modify: `docs/manual/content/{en,de}/getting-started/_index.md` (a new section `## Lists {#lists}`), `docs/manual/content/{en,de}/accounts/phones.md`, the catalogs, `phonix/web/static/help/`, `CHANGELOG.md`, `docs/SPEC.md` (UI section)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `listing.search`, `listing.page_of`, `listing.parse_page`, `listing.parse_per_page`, `ListPage`, the filter `highlight`, and `phones.search_fields`.
- Produces: `def list_page(request: Request, items: Sequence[T], fields: Callable[[T], Iterable[object]], choices: tuple[int | None, ...] = listing.PER_PAGE_CHOICES) -> ListPage[T]` in `common.py`. It reads `q`, `page` and `per_page` from `request.query_params`. Its `total` is `len(items)`.
- Produces: macros in `macros/lists.html`, imported `with context`:
  - `list_header(lv, list_id, url, count_text, placeholder)` renders the `card-header` with `<form method="get" action="{{ url }}" role="search">`. Its contents:
    - an `<input type="search" name="q" value="{{ lv.q }}" placeholder=… aria-label=…>` with `hx-get="{{ url }}" hx-trigger="input changed delay:300ms, search" hx-include="closest form" hx-target="#{{ list_id }}" hx-select="#{{ list_id }}" hx-select-oob="#{{ list_id }}-count" hx-swap="outerHTML" hx-replace-url="true"`
    - `<span id="{{ list_id }}-count" class="text-secondary">{{ count_text }}</span>`
    - **Per page**: `<select name="per_page">` with `lv.choices` (option `all` for `None`, label "All"), the same htmx attributes with `hx-trigger="change"` and `hx-push-url="true"` instead of replace
    - Enter submits the form as a normal GET.
  - `list_footer(lv, list_id, url)` renders the `card-footer` only when `lv.pages > 1`: the text "%(start)d–%(end)d of %(matched)d" and Tabler `.pagination` with ‹, the `page_links()` entries (`…` for `None`) and ›. Each link has `href="{{ url }}?{{ lv.query(page=n) }}"`, the same `hx-target`/`hx-select`/`hx-select-oob`/`hx-swap`, and `hx-push-url="true"`. The current page is `.active` with `aria-current="page"`.
  - `no_matches(text, url)` renders an `.empty` with `text` and a link "Clear search" to `url`.
- Produces: the convention for the list region. `<div id="list-<name>">` wraps the table (or the no-match / empty state) and the footer. The count span with `id="list-<name>-count"` sits in the header, outside the region.
- Produces: the count strings, chosen per list in the template:
  - `ngettext("%(num)d phone", "%(num)d phones", lv.total)` when not searching
  - `_("%(matched)d of %(total)d", matched=…, total=…)` when searching

- [ ] **Step 1: Write the failing tests** in `tests/test_web.py`. The sample data has phones 101–103 plus more; create about 60 extra phones in the test with `phone_svc.create_phone`, extensions `"3" + f"{i:02}"` and caller ID `f"Bulk {i}"`.

```python
def test_phone_list_search_and_paging(client):
    login(client)
    _bulk_phones(60)                                    # helper in the test module
    page = client.get("/accounts/phones").text
    assert 'id="list-phones"' in page and 'name="q"' in page and 'name="per_page"' in page
    assert page.count('id="phone-') - page.count('id="phone-status-') == 50
    assert 'hx-select="#list-phones"' in page and 'hx-replace-url="true"' in page
    assert "?page=2" in page                            # footer link
    r = client.get("/accounts/phones", params={"q": "bulk 5"})
    assert "<mark>Bulk 5</mark>" in r.text and "Bulk 12" not in r.text
    assert "of" in r.text                               # "11 of 63"-style count
    r = client.get("/accounts/phones", params={"q": "zzz-none"})
    assert "No phones found" in r.text and 'href="/accounts/phones"' in r.text
    r = client.get("/accounts/phones", params={"per_page": "all"})
    assert r.text.count('<tr id="phone-') == len(phone_svc.list_phones(...))  # all rows; no footer
    assert 'class="pagination' not in r.text

def test_phone_list_bad_params(client):
    login(client)
    for q in ("page=0", "page=-3", "page=x", "page=999", "per_page=7", "per_page=all&page=5"):
        assert client.get(f"/accounts/phones?{q}").status_code == 200, q

def test_phone_list_search_escapes(client):
    login(client)
    r = client.get("/accounts/phones", params={"q": '<script>"x'})
    assert "<script>\"x" not in r.text and "&lt;script&gt;" in r.text

def test_phone_status_follows_view(client):
    login(client)
    _bulk_phones(60)
    page = client.get("/accounts/phones", params={"q": "bulk 1"}).text
    assert 'hx-get="/accounts/phones/status?q=bulk+1"' in page
    part = client.get("/accounts/phones/status", params={"q": "bulk 1"}).text
    shown = re.findall(r'hx-target="#phone-status-(\d+)"', part)
    assert 0 < len(shown) <= 11
```

Fill in `phone_svc.list_phones(...)` with the test's session.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web.py -k "phone_list or phone_status_follows" -q`
Expected: FAIL.

- [ ] **Step 3: Implement `list_page`, the macros, and the phone list.** `phone_list` passes `lv=list_page(request, phone_svc.list_phones(db), phone_svc.search_fields)`; the template iterates over `lv.items`.
  - The `.empty` state "No phones yet" applies only when `lv.total == 0`; otherwise `no_matches(_("No phones found"), "/accounts/phones")`.
  - In `phone_row.html`, the extension, name and description cells use `| highlight(lv.q)`. The row partial is also rendered by the toggle route without `lv`, so default to `lv.q if lv is defined else ""`.
  - The polling `<tbody>` becomes `hx-get="/accounts/phones/status{{ '?' ~ lv.query() if lv.query() }}"`.
  - `phone_status` uses the same `list_page(...)` and renders `lv.items`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web.py -q`
Expected: PASS.

- [ ] **Step 5: Check in a browser.**
  - **Setup:** use the scratch Playwright set-up from the session (`/tmp/claude-1000/.../scratchpad/pw`), or install Playwright into a scratch venv. Run the app as in CLAUDE.md, in dry-run mode on port 8765.
  - **Typing:** on `/accounts/phones`, typing "bul" keeps focus and caret in the field and changes only `#list-phones` and the count. The URL becomes `?q=bul` without a new history entry.
  - **Paging and back:** page 2 pushes an entry, and the back button restores page 1. Per page "All" shows every row.
  - **No errors:** no CSP or JS errors. Remember from the earlier boost check that `page.wait_for_function` with a string is blocked by the CSP; poll from Python instead.

- [ ] **Step 6: i18n and docs.**
  - **i18n:** run `scripts/i18n.sh update`, then the `i18n-translator` agent for the new strings ("Search", "Per page", "All", "%(start)d–%(end)d of %(matched)d", "%(matched)d of %(total)d", "No phones found", "Clear search", the phone count plural). Then run `.venv/bin/pytest tests/test_i18n.py -q`.
  - **Manual, shared section:** a new section `## Lists {#lists}` in `getting-started/_index.md` (en and de). It explains search (which fields, as you type, upper/lower case), Per page, the page links and that the address can be bookmarked.
  - **Manual, phones chapter:** add a sentence in `accounts/phones.md`, en and de, that links to that section. Then run `scripts/help-build.sh`.
  - **CHANGELOG, Added:** "*Accounts → Phones*: search (extension, name, description) as you type, and paging with 25/50/100/all per page; the address keeps the view."
  - **SPEC:** describe the list pattern in the UI section.

- [ ] **Step 7: Commit**

```bash
git add phonix tests docs CHANGELOG.md
git commit -m "phones: search and paging in the phone list"
```

---

### Task 4: The other entity lists

**Files:**
- Modify: the routes `accounts.py` (`provider_list`, `provider_status`), `dialplan.py` (`Kind` gets `search_fields`; `register.list_view`), `services.py` (ROOMS `Kind`, `media`, `media_upload`), `advanced.py` (AMI `Kind`, `admin_users`, `_tokens_page`), `ivr.py` (`ivr_list`, `hours_list`, `_status_rows`), `system.py` (`backup`)
- Modify: the templates `pages/providers.html`, `partials/provider_row.html`, `partials/provider_status.html`, `pages/applications.html`, `pages/callgroups.html`, `pages/conferences.html`, `pages/ami_users.html`, `pages/ivr_menus.html`, `partials/ivr_row.html`, `pages/hours.html`, `partials/hours_row.html`, `pages/media.html`, `partials/media_table.html`, `pages/advanced_users.html`, `pages/advanced_tokens.html`, `partials/token_row.html`, `pages/system_backup.html`
- Modify: the manual chapters for these pages (en and de), the catalogs, the help, `CHANGELOG.md`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: everything from Task 3 (`list_page`, the macros, the region convention) and the Task 2 search functions.
- Produces: `Kind.search_fields: Callable[[Any], Iterable[object]]`, a new required field set for `APPS`, `GROUPS`, `ROOMS` and `AMI`. The region ids are:
  - `list-providers`, `list-applications`, `list-callgroups`, `list-conferences`, `list-ami-users`
  - `list-ivr`, `list-hours`, `list-media`, `list-users`, `list-tokens`, `list-backups`

  Each list has its own `ngettext` count noun and its own "No … found" text. The noun is the list's plural ("%(num)d provider"/"%(num)d providers", …).
- Each region and `#…-count` appears exactly once on its page. In `media_table.html` the region `<div id="list-media">` sits inside the partial, so the upload response (`media_upload`, rendered with `list_page(request, …)` from default parameters) still replaces `#media-files` with a working list. The `#…-count` span goes into the partial header as well.
- The backup list has no `<thead>` today. Keep it that way and just add the header form and the footer.
- The hours rows have live special switches that target `#hours-row-{id}`. They keep working because the rows keep their ids.

- [ ] **Step 1: Write the failing tests** in `tests/test_web.py`, one parametrised test over the lists that the sample data fills:

```python
LISTS = [
    ("/accounts/providers", "list-providers"), ("/dialplan/applications", "list-applications"),
    ("/dialplan/callgroups", "list-callgroups"), ("/services/conferencing", "list-conferences"),
    ("/advanced/manager", "list-ami-users"), ("/dialplan/ivr", "list-ivr"), ("/dialplan/hours", "list-hours"),
    ("/services/media", "list-media"), ("/advanced/users", "list-users"), ("/advanced/tokens", "list-tokens"),
    ("/system/backup", "list-backups"),
]

@pytest.mark.parametrize("url,region", LISTS)
def test_list_has_search_and_region(client, url, region):
    login(client)
    page = client.get(url).text
    assert page.count(f'id="{region}"') == 1 and page.count(f'id="{region}-count"') == 1
    assert f'hx-select="#{region}"' in page and 'name="q"' in page
    r = client.get(url, params={"q": "zzz-nothing-matches"})
    assert r.status_code == 200 and "Clear search" in r.text

def test_provider_search_highlight(client):
    login(client)
    r = client.get("/accounts/providers", params={"q": "iax tr"})
    assert "<mark>IAX Tr</mark>unk" in r.text and "Example Trunk" not in r.text

def test_media_upload_returns_list_region(client):
    # upload as in tests/test_media.py; the response must contain id="list-media" and id="list-media-count"
    ...
```

`test_media_upload_returns_list_region` reuses the upload helper from `tests/test_media.py` and asserts both ids in the response. For `/system/backup`, create one backup first (`backup_svc.create()` or the existing test helper) so that the region and not the empty text is rendered.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web.py -k "list_has_search or provider_search or media_upload_returns" -q`
Expected: FAIL.

- [ ] **Step 3: Apply the pattern to each list.** Use the same macro calls as the phone list, highlight the searched columns, and keep the real empty states for `lv.total == 0`.
  - **`provider_status`:** pages like `phone_status`.
  - **`hours_list`:** pass `lv` over the rows from `_status_rows`, filtering on the `BusinessHours` part of each `(h, st)` tuple, i.e. `lambda row: hours_svc.search_fields(row[0])`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy phonix`
Expected: PASS.

- [ ] **Step 5: Check in a browser:** search and page links on providers (status still updates), media (upload during a search), business hours (switch a special period during a search) and backups. Expect no JS or CSP errors.

- [ ] **Step 6: i18n and docs.**
  - **i18n:** run `scripts/i18n.sh update` and the `i18n-translator` agent.
  - **Manual:** add one sentence in each affected chapter, en and de, that links to `getting-started#lists`. `tests/test_help.py` must pass. Then run `scripts/help-build.sh`.
  - **CHANGELOG, Added:** replace the phones entry from Task 3 with one entry for all lists: "Every list (phones, providers, applications, call groups, IVR menus, business hours, conference rooms, media, manager users, administrators, API tokens, backups) can be searched as you type and is paged (25/50/100/all per page); the address keeps the view."

- [ ] **Step 7: Commit**

```bash
git add phonix tests docs CHANGELOG.md
git commit -m "ui: search and paging in all lists"
```

---

### Task 5: Audit log in SQL

**Files:**
- Modify: `phonix/services/common.py` (add `audit_page` below `audit`)
- Modify: `phonix/web/routes/ui/status.py` (`audit_log`)
- Modify: `phonix/web/templates/pages/status_audit.html`
- Modify: `docs/manual/content/{en,de}/status/audit.md`, the catalogs, the help, `CHANGELOG.md`
- Test: `tests/test_web.py` (or `tests/test_services.py` for the service function)

**Interfaces:**
- Consumes: `listing.ListPage`, `listing.parse_page`, `listing.parse_per_page`, `listing.PER_PAGE_NO_ALL`, the macros from Task 3, and the SQLite `casefold` function from Task 1.
- Produces: `def audit_page(session: Session, q: str, page: int, per_page: int) -> ListPage[AuditLog]` in `phonix/services/common.py`. It returns the newest entries first.
  - **Filter:** without `q` there is none. With `q`, the filter is `or_(func.casefold(col).contains(q.casefold(), autoescape=True) for col in (username, action, object_type, summary))`.
  - **Counts:** `matched` comes from `COUNT` with the filter, `total` from `COUNT` without it.
  - **Paging:** `page` is clamped to `1..pages` before `OFFSET`/`LIMIT`.
  - **Page size:** `choices=PER_PAGE_NO_ALL`.
- Produces: the audit page uses the region `list-audit`, and the count `ngettext("%(num)d entry", "%(num)d entries", total)`. The old `page_no` parameter and the "Newer"/"Older" links are removed.

- [ ] **Step 1: Write the failing tests**

```python
def test_audit_search_and_paging(client):
    login(client)
    with session_scope() as s:
        for i in range(70):
            audit(s, "admin", "update", "phone", i, f"Müller {i}")
    r = client.get("/status/audit", params={"q": "müller 6"})
    assert "Müller 6" in r.text and "Müller 5" not in r.text      # matches 6 and 60–69
    r = client.get("/status/audit", params={"q": "MÜLLER"})
    assert "of" in r.text                                           # casefold, not ASCII-only
    page = client.get("/status/audit").text
    assert 'id="list-audit"' in page and "?page=2" in page and 'value="all"' not in page
    assert client.get("/status/audit", params={"per_page": "all", "page": "99"}).status_code == 200

def test_audit_search_like_wildcards(client):
    login(client)
    with session_scope() as s:
        audit(s, "admin", "update", "phone", 1, "100% done")
        audit(s, "admin", "update", "phone", 2, "plain")
    r = client.get("/status/audit", params={"q": "%"})
    assert "100% done" in r.text and "plain" not in r.text
    r = client.get("/status/audit", params={"q": "_"})
    assert "plain" not in r.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web.py -k audit -q`
Expected: FAIL.

- [ ] **Step 3: Implement `audit_page`, rewire `audit_log`** to read `q`/`page`/`per_page` with `parse_per_page(..., PER_PAGE_NO_ALL)`, and switch the template to the shared macros. Highlight the user, action and object cells.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q && .venv/bin/mypy phonix`
Expected: PASS.

- [ ] **Step 5: i18n and docs.**
  - **i18n:** run `scripts/i18n.sh update` and the translator. The old strings "Newer"/"Older" drop out if they are unused elsewhere.
  - **Manual:** update the audit chapter, en and de: search over user, action and object, per page without "All", and no more Newer/Older. Then run `scripts/help-build.sh`.
  - **CHANGELOG:** extend the list entry from Task 4 with the audit log: "*Status → Audit Log*: search over user, action and object; page links instead of Newer/Older."

- [ ] **Step 6: Run the checklist and commit**

Run: `bash .claude/skills/ui-change-checklist/check.sh main`, then `.venv/bin/pytest -q`.

```bash
git add phonix tests docs CHANGELOG.md
git commit -m "audit: search and page links in the audit log"
```
