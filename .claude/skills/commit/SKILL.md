---
name: commit
description: Commit the current PhonixPBX changes with a project-style message after checking lint, tests and the user-visible follow-ups.
disable-model-invocation: true
argument-hint: "[optional hint for the summary or area]"
---

# Commit

Commit the working tree changes as one coherent commit in the project's style. `$ARGUMENTS`, if given, is a hint
for the area or summary.

## 1. Look at what is there

- `git status --short`, `git diff` and `git diff --cached`. Read the changes; don't commit what you haven't seen.
- On `main`: commit there (this project commits to main) unless the user asked for a branch.
- Unrelated changes mixed together: stop and propose how to split them instead of committing one blob.
- Never stage `.env`, credentials, `dev/root/`, `out/`, editor files or other build leftovers. Stage paths explicitly
  (`git add <paths>`), not `git add -A`.

## 2. Check before committing

Run and fix failures first; report anything you could not fix instead of committing around it:

```sh
.venv/bin/ruff check . && .venv/bin/ruff format --check phonix tests
.venv/bin/mypy phonix                      # when Python under phonix/ changed
.venv/bin/pytest -q                        # when code, templates, generators or catalogs changed
bash .claude/skills/ui-change-checklist/check.sh
```

- `check.sh` reports `MISSING`: complete those steps (translations, manual en+de, `scripts/help-build.sh`,
  CHANGELOG) before committing - they belong in the same commit. Use the ui-change-checklist skill for how.
- Golden file diffs: only accept with `UPDATE_GOLDEN=1` when the output change is intended, and say so.
- Schema change: an Alembic revision must be part of the commit.
- Docs-only, CI-only or `.claude/` changes: skip mypy/pytest.

## 3. Write the message

```
area: lowercase summary without trailing period

Optional body, wrapped at 72, explaining what changed for the admin and
why. Lists use "- " and may name menu paths (Dialplan > IVR Menus),
CLI commands, migrations and config/backup version bumps.
```

- **Area** = the subsystem, as used in history: `dialplan`, `api`, `ui`, `sip`, `firewall`, `firmware`, `console`,
  `status`, `certificate`, `nginx`, `backup`, `i18n`, `docs`, `ci`, `dev`, `scripts`, `demo`, `release`, `claude`.
  Pick the one a reader would look under; for a cross-cutting feature use the area of its main effect.
- **Summary** in lowercase, imperative or noun phrase, under ~70 chars: `dialplan: ivr menus and business hours`,
  `scripts: brace the hugo version in help-build.sh (shellcheck SC1087)`.
- **Body** for anything non-trivial; skip it for one-line fixes. Describe behaviour, not the diff line by line.
- No `Co-Authored-By`, "Generated with" or other attribution lines.

## 4. Commit and report

- Commit with a heredoc so the body keeps its formatting: `git commit -F - <<'EOF' ... EOF`.
- Hooks fail: fix the cause and create a new commit; never `--no-verify`, never `--amend` a commit you didn't just
  make in this run.
- Do not push unless asked.
- Report the commit hash and subject, and anything you skipped or could not verify.
