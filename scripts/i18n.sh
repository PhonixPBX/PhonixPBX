#!/bin/sh
# Web interface translations (phonix/locale/<lang>/LC_MESSAGES/messages.po).
#
#   scripts/i18n.sh extract   collect the marked strings into phonix/locale/messages.pot
#   scripts/i18n.sh update    extract, then merge new/changed strings into every catalog
#                             (creates missing catalogs for the languages in phonix/i18n.py)
#
# Catalogs are read directly by phonix/i18n.py; no .mo files are built.
# tests/test_i18n.py checks that every catalog is complete and its placeholders match.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PYBABEL=${PYBABEL:-.venv/bin/pybabel}
POT=phonix/locale/messages.pot

extract() {
	mkdir -p phonix/locale
	"$PYBABEL" extract -F babel.cfg -k N_ --no-location --sort-output \
		--project PhonixPBX -o "$POT" phonix
}

case "${1:-}" in
extract)
	extract
	;;
update)
	extract
	langs=$(.venv/bin/python -c 'from phonix import i18n; print(" ".join(l for l in i18n.LANGUAGE_NAMES if l != i18n.DEFAULT and l not in i18n.FALLBACK))')
	for lang in $langs; do
		po=phonix/locale/$lang/LC_MESSAGES/messages.po
		if [ -f "$po" ]; then
			"$PYBABEL" update -i "$POT" -d phonix/locale -l "$lang" --no-fuzzy-matching --ignore-obsolete
		else
			"$PYBABEL" init -i "$POT" -d phonix/locale -l "$lang"
		fi
	done
	;;
*)
	sed -n '2,10p' "$0"
	exit 2
	;;
esac
