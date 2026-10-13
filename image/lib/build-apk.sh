#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Build the "phonix" apk from the working tree and publish it, signed, in the
# local repository out/repo/<arch>/ for every architecture (noarch package).
. /src/image/lib/common.sh

VERSION=$(phonix_version)
PKGVER=$(apk_version "$VERSION")
ARCHES=${ARCHES:-"x86_64 aarch64 x86"}

# --- signing key (throwaway unless provided) ------------------------------
mkdir -p "$KEYS_DIR/abuild"
if [ -n "${PHONIX_ABUILD_KEY:-}" ]; then
	cp "$PHONIX_ABUILD_KEY" "$KEYS_DIR/abuild/phonix-abuild.rsa"
	cp "$PHONIX_ABUILD_KEY.pub" "$KEYS_DIR/abuild/phonix-abuild.rsa.pub"
fi
if [ ! -f "$KEYS_DIR/abuild/phonix-abuild.rsa" ]; then
	msg "generating a throwaway package signing key ($KEYS_DIR/abuild)"
	openssl genrsa -out "$KEYS_DIR/abuild/phonix-abuild.rsa" 4096 2>/dev/null
	openssl rsa -in "$KEYS_DIR/abuild/phonix-abuild.rsa" -pubout \
		-out "$KEYS_DIR/abuild/phonix-abuild.rsa.pub" 2>/dev/null
fi
chmod 600 "$KEYS_DIR/abuild/phonix-abuild.rsa"
mkdir -p "$HOME/.abuild"
cat >"$HOME/.abuild/abuild.conf" <<CONF
PACKAGER="PhonixPBX build <build@phonix.invalid>"
PACKAGER_PRIVKEY="$KEYS_DIR/abuild/phonix-abuild.rsa"
CONF
cp "$KEYS_DIR/abuild/phonix-abuild.rsa.pub" /etc/apk/keys/

# --- source tarball ---------------------------------------------------------
B=$WORK/apkbuild/phonix
rm -rf "$B"
mkdir -p "$B"
cp "$SRC/packaging/apk/phonix/APKBUILD" "$SRC/packaging/apk/phonix/phonix.pre-install" "$B/"
msg "creating source tarball phonix-$PKGVER"
tar -C "$SRC" \
	--exclude=__pycache__ --exclude='*.pyc' --exclude='*.egg-info' \
	--sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
	--transform "s,^,phonix-$PKGVER/," \
	-czf "$B/phonix-$PKGVER.tar.gz" pyproject.toml README.md LICENSE NOTICE phonix system

# --- build ------------------------------------------------------------------
cd "$B" || exit 1
export PHONIX_PKGVER="$PKGVER"
abuild -F checksum >"$WORK/apkbuild/abuild.log" 2>&1
REPODEST=$WORK/apkbuild/repo abuild -F -d -m -K -P "$WORK/apkbuild/repo" >>"$WORK/apkbuild/abuild.log" 2>&1 ||
	{ tail -n 40 "$WORK/apkbuild/abuild.log"; die "abuild failed"; }

# --- publish to the local multi-arch repository -----------------------------
built=$(find "$WORK/apkbuild/repo" -name "phonix-*$PKGVER-r*.apk")
[ -n "$built" ] || die "no packages built"
for a in $ARCHES; do
	d=$LOCAL_REPO/$a
	mkdir -p "$d"
	rm -f "$d"/phonix-*.apk
	# shellcheck disable=SC2086
	cp $built "$d/"
	(
		cd "$d" || exit 1
		apk index --no-warnings --quiet --output APKINDEX.tar.gz.new \
			--description "phonix local" --rewrite-arch "$a" ./*.apk
		abuild-sign -q APKINDEX.tar.gz.new
		mv APKINDEX.tar.gz.new APKINDEX.tar.gz
	)
done
msg "phonix $PKGVER published to $LOCAL_REPO ($ARCHES)"
