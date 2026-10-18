---
name: ui-change-checklist
description: Use when a PhonixPBX change touches templates, UI routes, menu entries, phonix.js or any _()/N_() string, or adds or changes behaviour an administrator can see, and before declaring such work done or committing it.
---

# UI change checklist

A user-visible change is not done until its translations, both manual languages, the built help, the
CHANGELOG and (when relevant) the SPEC are in the same commit. `tests/test_i18n.py` and `tests/test_help.py`
catch part of this; the CHANGELOG, the manual text and the SPEC are only caught by this checklist.

## Steps

1. **Find the gaps.** Run `bash .claude/skills/ui-change-checklist/check.sh` (or `... check.sh main` on a
   branch with commits). Every `MISSING` line is a step below that still has to happen.
2. **Translations** (when strings were added or changed):
   - `scripts/i18n.sh update`, then fill every empty `msgstr` in all catalogs under `phonix/locale/*/`.
   - Keep `%(name)s` placeholders identical; a literal `%` in a template string is `%%`.
   - German wording becomes the label the `de` manual quotes, so settle it first.
3. **Manual** (`docs/manual/content/{en,de}/`, path mirrors the menu URL):
   - Update the chapter in **both** languages, using the exact UI labels (German from the `de` catalog).
   - Heading anchors (`## Feld {#edit}`) must be identical in en and de. Forms rely on `{#edit}`.
   - A new menu item needs a new chapter in both languages.
   - `scripts/help-build.sh`, then commit `phonix/web/static/help/` with the change.
4. **CHANGELOG.md** under `## [Unreleased]`, section Added/Changed/Fixed/Removed/Security:
   - Write for administrators: what they can now do or what behaves differently.
   - Name menu paths in italics, e.g. *Dialplan → IVR Menus*.
   - Call out required action (config.json compatibility, upgrades, replaced containers).
   - Pure refactors and tests get no entry.
5. **docs/SPEC.md** when the data model, feature scope, API/MCP or backup format changed.
6. **Verify:** `.venv/bin/pytest -q tests/test_i18n.py tests/test_help.py tests/test_web.py`, then re-run
   `check.sh` until it exits 0 (or every remaining line is a justified `check`).

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Only the English manual updated | de chapter with German labels, same anchors |
| Manual edited, help not rebuilt | `scripts/help-build.sh`, commit `phonix/web/static/help/` |
| Hand-editing `messages.pot` or files in `static/help/` | Regenerate with the scripts |
| Translating logs, audit summaries, API errors, CLI output | Those stay English and unmarked |
| Sentence built from translated fragments or an f-string in `_()` | One string with named placeholders |
| CHANGELOG written for developers ("refactor form macro") | Describe the effect and the menu path |
