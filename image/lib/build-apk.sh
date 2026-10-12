#!/bin/sh
# Build the "askozia" apk from the working tree and publish it, signed, in the
# local repository out/repo/<arch>/ for every architecture (noarch package).
. /src/image/lib/common.sh

VERSION=$(askozia_version)
PKGVER=$(apk_version "$VERSION")
ARCHES=${ARCHES:-"x86_64 aarch64 x86"}

# --- signing key (throwaway unless provided) ------------------------------
mkdir -p "$KEYS_DIR/abuild"
if [ -n "${ASKOZIA_ABUILD_KEY:-}" ]; then
	cp "$ASKOZIA_ABUILD_KEY" "$KEYS_DIR/abuild/askozia-abuild.rsa"
	cp "$ASKOZIA_ABUILD_KEY.pub" "$KEYS_DIR/abuild/askozia-abuild.rsa.pub"
fi
if [ ! -f "$KEYS_DIR/abuild/askozia-abuild.rsa" ]; then
	msg "generating a throwaway package signing key ($KEYS_DIR/abuild)"
	openssl genrsa -out "$KEYS_DIR/abuild/askozia-abuild.rsa" 4096 2>/dev/null
	openssl rsa -in "$KEYS_DIR/abuild/askozia-abuild.rsa" -pubout \
		-out "$KEYS_DIR/abuild/askozia-abuild.rsa.pub" 2>/dev/null
fi
chmod 600 "$KEYS_DIR/abuild/askozia-abuild.rsa"
mkdir -p "$HOME/.abuild"
cat >"$HOME/.abuild/abuild.conf" <<CONF
PACKAGER="AskoziaPBX build <build@askozia.invalid>"
PACKAGER_PRIVKEY="$KEYS_DIR/abuild/askozia-abuild.rsa"
CONF
cp "$KEYS_DIR/abuild/askozia-abuild.rsa.pub" /etc/apk/keys/

# --- source tarball ---------------------------------------------------------
B=$WORK/apkbuild/askozia
rm -rf "$B"
mkdir -p "$B"
cp "$SRC/packaging/apk/askozia/APKBUILD" "$SRC/packaging/apk/askozia/askozia.pre-install" "$B/"
msg "creating source tarball askozia-$PKGVER"
tar -C "$SRC" \
	--exclude=__pycache__ --exclude='*.pyc' --exclude='*.egg-info' \
	--sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
	--transform "s,^,askozia-$PKGVER/," \
	-czf "$B/askozia-$PKGVER.tar.gz" pyproject.toml README.md askozia system

# --- build ------------------------------------------------------------------
cd "$B" || exit 1
export ASKOZIA_PKGVER="$PKGVER"
abuild -F checksum >"$WORK/apkbuild/abuild.log" 2>&1
REPODEST=$WORK/apkbuild/repo abuild -F -d -m -K -P "$WORK/apkbuild/repo" >>"$WORK/apkbuild/abuild.log" 2>&1 ||
	{ tail -n 40 "$WORK/apkbuild/abuild.log"; die "abuild failed"; }

# --- publish to the local multi-arch repository -----------------------------
built=$(find "$WORK/apkbuild/repo" -name "askozia-*$PKGVER-r*.apk")
[ -n "$built" ] || die "no packages built"
for a in $ARCHES; do
	d=$LOCAL_REPO/$a
	mkdir -p "$d"
	rm -f "$d"/askozia-*.apk
	# shellcheck disable=SC2086
	cp $built "$d/"
	(
		cd "$d" || exit 1
		apk index --no-warnings --quiet --output APKINDEX.tar.gz.new \
			--description "askozia local" --rewrite-arch "$a" ./*.apk
		abuild-sign -q APKINDEX.tar.gz.new
		mv APKINDEX.tar.gz.new APKINDEX.tar.gz
	)
done
msg "askozia $PKGVER published to $LOCAL_REPO ($ARCHES)"
