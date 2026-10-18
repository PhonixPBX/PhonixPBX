#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Report the follow-up work a change still lacks (translations, manual, help build, CHANGELOG, SPEC).
#
#   bash .claude/skills/ui-change-checklist/check.sh          uncommitted + untracked changes vs HEAD
#   bash .claude/skills/ui-change-checklist/check.sh main     everything since the merge base with main
#
# Exits 1 when something is missing. It only reads; it never runs the build scripts.
set -eu

cd "$(git rev-parse --show-toplevel)"

if [ $# -gt 0 ]; then
	BASE=$(git merge-base "$1" HEAD)
else
	BASE=HEAD
fi

FILES=$( (git diff --name-only "$BASE"; git ls-files --others --exclude-standard) | sort -u)
DIFF=$(git diff "$BASE" -- phonix; for f in $(git ls-files --others --exclude-standard phonix); do sed 's/^/+/' "$f"; done)

has() { printf '%s\n' "$FILES" | grep -Eq "$1"; }

missing=0
todo() { echo "MISSING  $1"; missing=1; }
ok() { echo "ok       $1"; }
hint() { echo "check    $1"; }

ui=0
has '^phonix/web/(templates|routes/ui|static/phonix\.js|templating\.py)' && ui=1
strings=0
printf '%s\n' "$DIFF" | grep -E '^[+-]' | grep -Eq '(^|[^A-Za-z_])N?_\(' && strings=1
code=0
printf '%s\n' "$FILES" | grep -E '^phonix/' | grep -Evq '^phonix/(locale|web/static/help)/' && code=1

if [ $ui = 0 ] && [ $strings = 0 ] && [ $code = 0 ]; then
	echo "No changes under phonix/ - nothing to check."
	exit 0
fi

echo "UI files changed: $([ $ui = 1 ] && echo yes || echo no)   translatable strings touched: $([ $strings = 1 ] && echo yes || echo no)"
echo

# Translations
if [ $strings = 1 ]; then
	if has '^phonix/locale/messages\.pot$'; then ok "messages.pot updated"; else todo "run scripts/i18n.sh update"; fi
	n=$(printf '%s\n' "$FILES" | grep -Ec '^phonix/locale/[^/]+/LC_MESSAGES/messages\.po$' || true)
	total=$(ls -d phonix/locale/*/LC_MESSAGES | wc -l)
	if [ "$n" -ge "$total" ]; then ok "all $total catalogs touched"; else todo "translate new entries: $n of $total catalogs changed"; fi
fi

# Manual
if [ $ui = 1 ]; then
	en=0; de=0
	has '^docs/manual/content/en/' && en=1
	has '^docs/manual/content/de/' && de=1
	if [ $en = 1 ]; then ok "manual (en) updated"; else todo "update the chapter in docs/manual/content/en/"; fi
	if [ $de = 1 ]; then ok "manual (de) updated"; else todo "update the chapter in docs/manual/content/de/"; fi
	if git diff "$BASE" -- phonix/web/templating.py | grep -Eq '^[+-].*MenuItem|^[+-].*url='; then
		hint "menu changed: a new menu item needs a new chapter in both languages (tests/test_help.py)"
	fi
fi
if has '^docs/manual/'; then
	if has '^phonix/web/static/help/'; then ok "help output rebuilt"; else todo "run scripts/help-build.sh and commit phonix/web/static/help/"; fi
fi

# CHANGELOG
if [ $ui = 1 ] || [ $code = 1 ]; then
	if has '^CHANGELOG\.md$'; then ok "CHANGELOG.md updated"; else todo "CHANGELOG.md entry under [Unreleased] (skip only for refactors/tests)"; fi
fi

# SPEC
if has '^phonix/(core/models\.py|core/settings\.py|services/resources\.py|services/settings_api\.py|mcp\.py|web/routes/api\.py|services/backup)'; then
	if has '^docs/SPEC\.md$'; then ok "docs/SPEC.md updated"; else hint "data model/API/MCP changed: does docs/SPEC.md need an update?"; fi
fi

exit $missing
