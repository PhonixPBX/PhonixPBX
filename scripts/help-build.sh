#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Build the user manual (docs/manual, Hugo) into phonix/web/static/help/.
# The output is committed, so packages and images need no Hugo.
#   scripts/help-build.sh          rebuild
#   scripts/help-build.sh check    fail if the committed output is out of date (CI)
set -eu

HUGO_VERSION=0.166.0

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/docs/manual"
DEST="$ROOT/phonix/web/static/help"
HUGO=${HUGO:-hugo}

if ! "$HUGO" version 2>/dev/null | grep -q "v$HUGO_VERSION[-+ ]"; then
    echo "error: hugo $HUGO_VERSION required (found: $("$HUGO" version 2>/dev/null || echo none))" >&2
    exit 1
fi

build() {
    "$HUGO" --quiet --minify --panicOnWarning --source "$SRC" --destination "$1" --cleanDestinationDir
}

case "${1:-build}" in
build)
    build "$DEST"
    ;;
check)
    WORK=$(mktemp -d)
    trap 'rm -rf "$WORK"' EXIT
    build "$WORK/help"
    if ! diff -r "$DEST" "$WORK/help" >/dev/null; then
        diff -rq "$DEST" "$WORK/help" >&2 || true
        echo "error: phonix/web/static/help is out of date, run scripts/help-build.sh" >&2
        exit 1
    fi
    ;;
*)
    echo "usage: $0 [build|check]" >&2
    exit 2
    ;;
esac
