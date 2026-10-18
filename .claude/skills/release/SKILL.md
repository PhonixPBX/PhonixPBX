---
name: release
description: Cut a PhonixPBX release (version bump, CHANGELOG section, golden files, signed v-tag) and start the next development version.
disable-model-invocation: true
argument-hint: "[version, e.g. 1.5.0 or 1.5.0rc1]"
---

# Release

`docs/RELEASING.md` is the procedure: follow its steps in order, it is not repeated here. This skill adds the
decisions and the stops around it. `$ARGUMENTS`, if given, is the version.

## 1. Gather, then ask once

- Previous release: `git describe --tags --abbrev=0`.
- Run the checks of step 2 now, so their results go into the same message.
- Base the version proposal on the `## [Unreleased]` section of `CHANGELOG.md`:
  - only Fixed or Security → patch (`1.4.1`)
  - anything under Added or Changed → minor (`1.5.0`)
  - an incompatible change for administrators (config.json format, replaced containers, a manual upgrade step) →
    ask whether it is a major release
- Compare the section with `git log v<previous>..HEAD --oneline`:
  - every user-visible commit has an entry
  - entries describe the effect for administrators and name menu paths
  - required actions are called out
  - the release section has no empty subsections
- **Stop and ask the maintainer**, in one message:
  1. the proposed version and the date (today)
  2. changelog gaps, with the wording you propose
  3. failed checks or uncommitted changes to tracked files
  4. user-visible changes since the last tag that were never verified outside the tests (for example only run
     under `dry-run`, not on an appliance, LXC or OCI): name them and ask whether to release anyway
- Pre-releases (`1.5.0rc1`): `scripts/release.sh check` needs a `## [1.5.0rc1]` section. Ask how the changelog
  should look before editing it.

## 2. Prepare the release commit

- Agreed changelog fixes go into a separate `docs: changelog for X.Y.Z` commit before the release commit, so the
  release commit only bumps versions.
- Untracked files (for example `.claude/` work in progress) stay untracked. Stage explicit paths, never
  `git commit -a` or `git add -A`.
- Run every "Before the release" check from `docs/RELEASING.md`, plus:
  - ruff, mypy and the full `pytest -q`
  - `scripts/help-build.sh` leaves `phonix/web/static/help/` unchanged (CI checks it)
  - `gh secret list` shows the three secrets by name (their values cannot be checked)
- Then the steps up to and including the `release: X.Y.Z` commit.
- After `UPDATE_GOLDEN=1`, `git diff --stat tests/golden` shows only the header version line. Anything else is a
  bug: stop and report it.
- `scripts/release.sh check vX.Y.Z` passes, and `scripts/release.sh notes vX.Y.Z` prints the expected text.

## 3. Push, wait for CI, then tag

Pushes and tags are outward-facing: get an explicit OK for each one.

1. `git push origin main`
2. Wait until CI is green **for the release commit**: `gh run list --commit <sha>`, then `gh run watch <id>`.
   A tag starts the image and container builds that publish the release. Never tag a commit whose CI has failed
   or is still running.
3. Tag with `git tag -s` as in `docs/RELEASING.md`.
   - Signing can need the maintainer's passphrase (pinentry), which this shell cannot answer. If the tag fails
     with a gpg error, ask the maintainer to run the `git tag -s ...` and `git push origin vX.Y.Z` lines
     themselves (`! <command>` in the prompt).
   - Never fall back to an unsigned or lightweight tag.
4. Watch `image.yml` and `container.yml` for the tag. Check the release assets and ghcr.io tags as in
   `docs/RELEASING.md`.

## 4. Start the next development version

- Do the "After the release" commit (`release: start X.Y+1.0 development`) only after the tag is pushed, so the
  tag points at the release commit. The new `## [Unreleased]` is the bare heading, without subsections, as in
  earlier releases.
- Same golden-file regeneration and checks as above.
- Push only after an OK.

## Report

The version, the release commit and the tag. The CI and release workflow results, with links. Anything that was
skipped or left to the maintainer.
