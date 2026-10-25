# List views: search and paging

Status: design, agreed in conversation on 2026-10-25; awaiting approval of this document.

## Intent

None of the list pages in the web UI can be searched, and none of them except the audit log is paged. On a large installation (about 500 phones) the phone list is long and slow to scan, and the applications list has the same problem on a smaller scale. The administrator wants **search and paging as the standard for every list**, built with htmx: typing filters the list right away, the view (search term, page, page size) is in the address so reload, the back button and a shared link show the same view, and the REST API and MCP can search and page as well, so scripts and AI tools don't have to fetch 500 phones every time.

## Goals

1. Every entity list page has a **search field** and **paging** with one shared look and behaviour (agreed with the user, mockup "A with per page from B"):
   - card header: search field on the left, next to it the count ("500 phones" without a search, "12 of 500" with one), on the right **Per page** with 25 / 50 / 100 / all, default 50;
   - card footer: "51–100 of 500" and page links ‹ 1 2 3 … 10 ›; the footer is hidden when everything fits on one page;
   - matches of the search term are **highlighted** in the rows.
2. **Typing filters immediately** (htmx): shortly after the user stops typing, only the table body, the counts and the footer are replaced; the search field keeps focus and its caret. A new search goes back to page 1.
3. The search is **case-insensitive substring** matching ("mei" finds "Meier"), also for non-ASCII letters ("müller" finds "Müller"). Each list searches its own visible text columns. For phones: extension, name (caller ID name) and description (agreed with the user).
4. **The view is in the address**: `?q=…&page=N&per_page=N|all`. Reload, the back button and shared links show the same view. Typing updates the address without adding a history entry per keystroke.
5. Behaviour that exists today keeps working on the rows shown: status polling (phones, providers), enable/disable toggles, delete, the live special period switches on business hours.
6. **No match**: the table shows "No phones found" (per list) with a link that clears the search, instead of the "No phones yet" empty state, which stays for a list that really is empty.
7. **REST API**: every list endpoint gets optional `q`, `limit` and `offset` query parameters. The search matches the same fields as the UI. Without parameters the endpoint behaves exactly as today.
8. **MCP**: every entity list tool gets optional `q`, `limit` and `offset` arguments and reports the total number of matches.
9. UI, REST and MCP use **one implementation** of search and paging in the service layer, so they always return the same matches.

## Scope: which lists

| List | Search fields | Notes |
|---|---|---|
| Accounts → Phones | extension, caller ID name, description | the main case, up to ~500 |
| Accounts → Providers | name, host, username | |
| Dialplan → Applications | number, name, description | |
| Dialplan → Call Groups | number, name | |
| Dialplan → IVR Menus | number, name, description | |
| Dialplan → Business Hours | name, description, feature code | |
| Services → Conferencing | number, name | |
| Services → Media | name, type | the table is also replaced after an upload (`#media-files`); that has to keep working |
| Advanced → Manager | username | |
| Advanced → Users | username | |
| Advanced → API Tokens | name, prefix, owner | |
| System → Backup/Restore | file name | from the file system, not the database |
| Status → Audit Log | user, action, object | replaces "Newer"/"Older" with the shared footer; unbounded, so it must page in SQL; **Per page** offers 25 / 50 / 100 without "all" |

Small lists get it too, for one consistent behaviour (agreed with the user: "generally as the standard"). The search fields in this table are my proposal from the visible columns. The user only fixed the phone fields.

## Non-goals

- **Sorting by column** (clicking table headers). Each list keeps its current order, phones by extension (length, then number).
- **Saving** the page size or the search per user. A fresh visit without parameters shows 50 rows and no search.
- **Live views**: Status → Logs (live tail over SSE) and Status → Calls & Registrations are not lists and stay as they are.
- Advanced filters (by type, enabled/disabled, registered, …), search operators, fuzzy matching.
- Paging the child rows inside forms (dial patterns, IVR options, call group members).

## Anti-goals

- **Existing API clients must not break.** A `GET /api/v1/phones` without the new parameters returns the same JSON array as today. My call: paging metadata goes into an `X-Total-Count` response header and the body stays an array, rather than changing the body to `{"items": …, "total": …}`.
- The search field must never lose focus or the typed text while the list updates.
- A search must never show rows that don't match, and must not interpret the term as markup. Highlighting must escape the text before marking (no XSS through phone names).
- Status polling must not fetch or render the status of all 500 phones when only 50 are shown.

## Constraints

- htmx 4 (vendored), Tabler 1.7.1, CSP without inline scripts (behaviour goes in `static/phonix.js` via `data-*`), server-rendered Jinja2.
- The sidebar uses `hx-boost` and swaps `#page`, and the back button restores `#page` (`hx-history-elt`). List URLs with parameters must restore correctly through that path.
- Service layer conventions: `ServiceError`, no translations in the API, fully typed Python 3.10, ruff/mypy.
- Every new UI string goes through gettext with all 11 catalogs filled, and both manuals (en/de) are updated (`ui-change-checklist`). `docs/SPEC.md` is kept in step (UI, API/MCP sections). CHANGELOG entries are written for administrators. The MCP result change below needs a "Changed" entry.
- Sizes: entity lists stay in the hundreds, the audit log is unbounded.

## Decided (my calls, open to correction)

- **URL parameters**: UI `q`, `page` (1-based), `per_page` (25, 50, 100, `all`; anything else falls back to 50). REST and MCP use `q`, `limit` and `offset`, the usual API style.
- **REST**: the body stays a JSON array. Add `X-Total-Count`, the total number of matches before `limit`/`offset`, and send it always, also without parameters. Without `limit`, all matches are returned. The parameters show up in the OpenAPI docs.
- **MCP**: list tools return `{"items": [...], "total": N}` instead of a bare array. MCP clients are mostly LLMs that read the result, so the extra wrapper is cheap there, and the total is what they need for paging. Without `limit` the tool returns all matches, as before. This changes the MCP tool output, so it gets a CHANGELOG entry under "Changed".
- **Case folding**: "case-insensitive" covers umlauts and other non-ASCII letters. Python compares with `casefold()`. SQL (the audit log, and entity lists if they move to SQL) must not rely on SQLite's ASCII-only `LIKE`/`ilike`: register a Python function (e.g. `casefold`) on the SQLite connection and compare with it.
- **"All" per page**: offered on every list except the audit log, which can grow to tens of thousands of rows with diffs. The per-page options are therefore set per list. The default set is 25 / 50 / 100 / all, and the audit log uses 25 / 50 / 100. `per_page=all` on the audit log falls back to 50.
- **Where the filtering happens**: entity lists are small (hundreds) and some sort in Python (phones by extension length, then number). Filtering and slicing in Python after the existing `list_*` query is fine and keeps the current order. The audit log filters and pages in SQL (`ILIKE`, `OFFSET`/`LIMIT`, `COUNT`). The builder can switch entity lists to SQL if it is simpler, as long as the order stays the same.
- **Debounce**: about 300 ms after the last keystroke, plus Enter and the search field's clear (×) button. Typing replaces the history entry, and changing the page or the page size pushes one.
- **Swap region**: one container per list card that holds the counts, the table and the footer, without the search field. It is replaced on search, page change and page size change, so focus stays in the input.
- **Status polling**: the polling element sits inside the swapped region and passes the current `q`/`page`/`per_page`, so it only reports the rows shown.
- **Deleting or toggling a row** keeps working as today (the row is replaced or removed). The counts and the footer may be stale until the next search or page change. That is accepted.
- **A page past the end** (e.g. `page=9` after a search shrank the list) shows the last page.

## Left to the builder

- The shared building blocks: a service-level helper (search fields per resource, total, slice), a Jinja macro for the card header and footer, a highlight filter, and the htmx wiring in `phonix.js` if attributes alone are not enough.
- Whether the swapped fragment comes from the same route (`HX-Request`/`HX-Target`) or a separate `/…/rows` endpoint.
- How `Resource` in `phonix/services/resources.py` declares its search fields, so REST and MCP get them generically.
- The page link pattern for many pages (e.g. first, last, current ±2, with ellipses).
- Exact strings and their translations, and the manual: a short shared section on searching and paging lists, plus a sentence in each list chapter. The builder decides the structure, in both languages.
- Tests: service helper (matching, order kept, total, slicing, bounds), UI (fragment vs full page, URL parameters, no-match state, highlight escaping), REST (`X-Total-Count`, parameters, unchanged behaviour without them), MCP (arguments, `total`), audit log paging in SQL.
