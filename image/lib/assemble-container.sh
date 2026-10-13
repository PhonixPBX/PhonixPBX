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
write_sha256sums
msg "[$BOARD] done: $NAME.tar.xz ($(du -h "$OUT/$NAME.tar.xz" | cut -f1)), $INCUS_NAME.tar.xz ($(du -h "$OUT/$INCUS_NAME.tar.xz" | cut -f1))"
