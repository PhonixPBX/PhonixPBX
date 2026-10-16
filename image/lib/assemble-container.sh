#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Package the root file system of a container board (CONTAINER=1, lxc-*).
#   assemble-container.sh <board>
# -> out/phonix-<version>-lxc-<arch>.tar.xz       rootfs tarball: Proxmox VE CT
#                                                  template, lxc-create -t local --fstree
#    out/phonix-<version>-lxc-<arch>.meta.tar.xz  metadata for lxc-create -t local
#    out/phonix-<version>-incus-<arch>.tar.xz     Incus/LXD unified image
#    out/phonix-<version>-lxc-<arch>.packages
#    out/phonix-<version>-lxc-<arch>.update       signed package update bundle
#
# Runs inside the build container, where the files have their real (numeric)
# ownership; the tarballs store numeric ids only (root = 0, asterisk = 101,
# phonix = 200, ...), which LXC/Incus/Proxmox shift for unprivileged
# containers when they unpack them.
BOARD=$1
. /src/image/lib/common.sh
load_profile
[ "${CONTAINER:-0}" = 1 ] || die "$BOARD is not a container board"

R=$BW/rootfs
[ -x "$R/sbin/init" ] || die "no root file system in $R (run build-rootfs.sh first)"
SUFFIX=${BOARD#lxc-}
NAME=phonix-$VERSION-$BOARD
INCUS_NAME=phonix-$VERSION-incus-$SUFFIX
C=$BW/container
rm -rf "$C"
mkdir -p "$C/lxc-meta" "$C/incus/templates"
BUILD_DATE=$(date -u -d "@$SOURCE_DATE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)
ALPINE=$(cat "$R/etc/alpine-release")

# reproducible tar of a list of paths below a directory (numeric ids, no
# xattrs, mtimes clamped to SOURCE_DATE_EPOCH)
mktar() { # out.tar.xz dir path...
	_out=$1
	_dir=$2
	shift 2
	tar -C "$_dir" --numeric-owner --sort=name --format=gnu \
		--mtime="@$SOURCE_DATE_EPOCH" --clamp-mtime \
		-cf - "$@" | xz -T0 -9 -c >"$_out.tmp"
	mv "$_out.tmp" "$_out"
}

# --- rootfs tarball -------------------------------------------------------------------
msg "[$BOARD] rootfs tarball"
mktar "$OUT/$NAME.tar.xz" "$R" .

# --- lxc-create -t local metadata ---------------------------------------------------------
# LXC_TEMPLATE_CONFIG is replaced by lxc-local with /usr/share/lxc/config;
# alpine.common.conf is the configuration Proxmox VE also uses for Alpine
cat >"$C/lxc-meta/config" <<EOF
lxc.include = LXC_TEMPLATE_CONFIG/alpine.common.conf
lxc.arch = $INCUS_ARCH
EOF
cat >"$C/lxc-meta/config-user" <<EOF
lxc.include = LXC_TEMPLATE_CONFIG/alpine.common.conf
lxc.include = LXC_TEMPLATE_CONFIG/userns.conf
lxc.arch = $INCUS_ARCH
EOF
: >"$C/lxc-meta/templates"
: >"$C/lxc-meta/excludes-user"
cat >"$C/lxc-meta/create-message" <<EOF
PhonixPBX $VERSION ($BOARD) was created.
Start it with "lxc-start -n <name>". The console menu shows the web address
and the initial admin password: "lxc-console -n <name> -t 0".
EOF
mktar "$OUT/$NAME.meta.tar.xz" "$C/lxc-meta" config config-user templates excludes-user create-message

# --- Incus / LXD unified image ---------------------------------------------------------------
msg "[$BOARD] Incus image"
cat >"$C/incus/metadata.yaml" <<EOF
architecture: $INCUS_ARCH
creation_date: $SOURCE_DATE_EPOCH
properties:
  os: PhonixPBX
  release: "$VERSION"
  variant: default
  architecture: $INCUS_ARCH
  description: PhonixPBX $VERSION (Alpine Linux $ALPINE, $INCUS_ARCH, built $BUILD_DATE)
  serial: "$(date -u -d "@$SOURCE_DATE_EPOCH" +%Y%m%d_%H%M)"
templates:
  /etc/hostname:
    when:
      - create
      - copy
      - rename
    template: hostname.tpl
  /etc/hosts:
    when:
      - create
      - copy
      - rename
    template: hosts.tpl
EOF
printf '{{ container.name }}\n' >"$C/incus/templates/hostname.tpl"
printf '127.0.0.1\tlocalhost {{ container.name }}\n::1\tlocalhost\n' >"$C/incus/templates/hosts.tpl"
# metadata + templates, and the rootfs as "rootfs/" (a sibling of $C)
tar -C "$C/incus" --numeric-owner --owner=0 --group=0 --sort=name --format=gnu \
	--mtime="@$SOURCE_DATE_EPOCH" -cf "$C/incus.tar" metadata.yaml templates
tar -C "$BW" --numeric-owner --sort=name --format=gnu \
	--mtime="@$SOURCE_DATE_EPOCH" --clamp-mtime -rf "$C/incus.tar" rootfs
xz -T0 -9 -c "$C/incus.tar" >"$OUT/$INCUS_NAME.tar.xz.tmp"
mv "$OUT/$INCUS_NAME.tar.xz.tmp" "$OUT/$INCUS_NAME.tar.xz"
rm -f "$C/incus.tar"

cp "$BW/packages.txt" "$OUT/$NAME.packages"

# --- update bundle -------------------------------------------------------------------------
# every installed package at the installed version, as an apk repository: priv
# install-update upgrades a running container to exactly this package set. The
# index is not signed: the manifest signature covers packages.tar as a whole.
msg "[$BOARD] update bundle"
P=$C/payload
mkdir -p "$P" "$C/repo/$ARCH"
# shellcheck disable=SC2046
apk --root "$R" --arch "$ARCH" --cache-dir "$WORK/cache/apk-$ARCH" --repositories-file /dev/null \
	-X "$LOCAL_REPO" -X "$ALPINE_MIRROR/$ALPINE_BRANCH/main" -X "$ALPINE_MIRROR/$ALPINE_BRANCH/community" \
	--no-interactive fetch --output "$C/repo/$ARCH" $(apk --root "$R" info 2>/dev/null) >"$C/fetch.log" 2>&1 ||
	{ tail -n 20 "$C/fetch.log"; die "apk fetch failed"; }
(cd "$C/repo/$ARCH" && ls -- *.apk | sed 's/\.apk$//' | sort) >"$C/fetched.txt"
cmp -s "$C/fetched.txt" "$BW/packages.txt" ||
	{ diff "$BW/packages.txt" "$C/fetched.txt" || true; die "the repositories do not have the installed package versions"; }
(
	cd "$C/repo/$ARCH" || exit 1
	apk --keys-dir "$R/etc/apk/keys" index --no-warnings --quiet --output APKINDEX.tar.gz \
		--description "PhonixPBX $VERSION $BOARD" --rewrite-arch "$ARCH" ./*.apk
) || die "apk index failed"
tar -C "$C/repo" --format=ustar --owner=0 --group=0 --numeric-owner --sort=name \
	--mtime="@$SOURCE_DATE_EPOCH" -cf "$P/packages.tar" "$ARCH"
cp "$R/etc/apk/world" "$P/world"
cp "$R/usr/share/phonix/image-info" "$P/image-info"
SIGNKEY=${PHONIX_UPDATE_SIGNING_KEY:-$KEYS_DIR/update-signing.pem}
"$IMG/mkbundle.sh" "$BOARD" "$VERSION" "$P" "$SIGNKEY" "$OUT/$NAME.update"
rm -rf "$C/repo" "$P"

write_sha256sums
msg "[$BOARD] done: $NAME.tar.xz ($(du -h "$OUT/$NAME.tar.xz" | cut -f1)), $INCUS_NAME.tar.xz ($(du -h "$OUT/$INCUS_NAME.tar.xz" | cut -f1)), $NAME.update ($(du -h "$OUT/$NAME.update" | cut -f1))"
