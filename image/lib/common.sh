# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=sh
# Shared settings for the in-container build steps. Sourced with the board
# name in $BOARD.
set -eu

SRC=${SRC:-/src}
IMG=$SRC/image
WORK=${WORK:-$IMG/work}
OUT=${OUT:-$SRC/out}
ALPINE_BRANCH=${ALPINE_BRANCH:-v3.24}
ALPINE_MIRROR=${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}
KEYS_DIR=${PHONIX_KEYS_DIR:-$IMG/keys}
LOCAL_REPO=$OUT/repo
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(date +%s)}
export SOURCE_DATE_EPOCH

msg() {
	printf '\033[1;34m==>\033[0m %s\n' "$*" >&2
}

die() {
	printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2
	exit 1
}

# version of the python package (pyproject.toml), overridable
phonix_version() {
	if [ -n "${PHONIX_VERSION:-}" ]; then
		echo "$PHONIX_VERSION"
		return
	fi
	python3 -c 'import tomllib,sys; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' \
		"$SRC/pyproject.toml"
}

# PEP 440 -> apk version (1.1.0.dev0 -> 1.1.0_pre0, 1.0.0rc1 -> 1.0.0_rc1)
apk_version() {
	echo "$1" | sed -E \
		-e 's/\.?dev([0-9]*)$/_pre\1/' \
		-e 's/\.?rc([0-9]*)$/_rc\1/' \
		-e 's/\.?a([0-9]*)$/_alpha\1/' \
		-e 's/\.?b([0-9]*)$/_beta\1/' \
		-e 's/\.?post([0-9]*)$/_p\1/'
}

load_profile() {
	[ -f "$IMG/profiles/$BOARD.conf" ] || die "unknown board $BOARD"
	# shellcheck disable=SC1090
	. "$IMG/profiles/$BOARD.conf"
	VERSION=$(phonix_version)
	PKGVER=$(apk_version "$VERSION")
	BW=$WORK/$BOARD
	mkdir -p "$BW" "$OUT" "$WORK/cache/apk-$ARCH"
}

# read a package list (comments and blank lines removed)
pkglist() {
	sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$@"
}

# apk against a target root (no scripts: they could not run for foreign
# architectures anyway, their effects are reproduced by build-rootfs.sh)
apk_root() {
	_root=$1
	shift
	apk --root "$_root" --arch "$ARCH" \
		--cache-dir "$WORK/cache/apk-$ARCH" \
		--repositories-file /dev/null \
		-X "$LOCAL_REPO" \
		-X "$ALPINE_MIRROR/$ALPINE_BRANCH/main" \
		-X "$ALPINE_MIRROR/$ALPINE_BRANCH/community" \
		--no-interactive --no-scripts "$@"
}

# prepare an empty target root with the Alpine and our package keys
init_root() {
	_root=$1
	rm -rf "$_root"
	mkdir -p "$_root/etc/apk/keys"
	cp /usr/share/apk/keys/"$ARCH"/*.pub "$_root/etc/apk/keys/"
	cp "$KEYS_DIR"/abuild/*.rsa.pub "$_root/etc/apk/keys/"
	echo "$ARCH" >"$_root/etc/apk/arch"
}

# create the busybox applet links that busybox' post-install script would
# (busybox --install -s); the builder's busybox is the same Alpine build
busybox_links() {
	_root=$1
	busybox --list-full | while read -r _applet; do
		[ -e "$_root/$_applet" ] || [ -L "$_root/$_applet" ] && continue
		mkdir -p "$_root/$(dirname "$_applet")"
		ln -s /bin/busybox "$_root/$_applet"
	done
}

kernel_version() {
	ls "$1/lib/modules" | head -n 1
}

# SHA256SUMS over all release artifacts in $OUT (disk images, update
# bundles, container tarballs)
write_sha256sums() {
	(
		cd "$OUT" || exit 1
		set --
		for _f in phonix-*.img.zst phonix-*.update phonix-*.tar.xz; do
			[ -f "$_f" ] && set -- "$@" "$_f"
		done
		[ $# -gt 0 ] || exit 0
		sha256sum "$@" >SHA256SUMS
	)
}
