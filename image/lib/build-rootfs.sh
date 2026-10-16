#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Build the root file system of a board into image/work/<board>/rootfs.
#   build-rootfs.sh <board>
#
# Container boards (CONTAINER=1 in the profile, lxc-*) get the same system
# without kernel, firmware, device management and A/B slot handling.
#
# Packages are installed with "apk --no-scripts" so that foreign
# architectures need no emulation; the effects of the install scripts
# (users/groups, busybox links, depmod, ...) are reproduced here
# deterministically.
BOARD=$1
. /src/image/lib/common.sh
load_profile

R=$BW/rootfs
SYS=$SRC/system

msg "[$BOARD] base layout"
init_root "$R"
apk_root "$R" add --initdb alpine-baselayout alpine-baselayout-data alpine-keys >/dev/null

# --- users and groups (fixed ids; package pre-install scripts are not run) -
add_group() { # name gid [members]
	grep -q "^$1:" "$R/etc/group" || echo "$1:x:$2:${3:-}" >>"$R/etc/group"
}
add_member() { # group user
	sed -i -E "s/^($1:[^:]*:[^:]*:)(.*)$/\1\2,$2/; s/^($1:[^:]*:[^:]*:),/\1/" "$R/etc/group"
}
add_user() { # name uid gid home shell
	grep -q "^$1:" "$R/etc/passwd" || echo "$1:x:$2:$3:$1:$4:$5" >>"$R/etc/passwd"
	grep -q "^$1:" "$R/etc/shadow" || echo "$1:!::0:::::" >>"$R/etc/shadow"
}
add_group shadow 42
add_group klogd 101
add_user klogd 100 101 /dev/null /sbin/nologin
add_group asterisk 102
add_user asterisk 101 102 /var/lib/asterisk /sbin/nologin
add_member dialout asterisk
add_group chrony 103
add_user chrony 102 103 /dev/null /sbin/nologin
add_group nginx 104
add_user nginx 103 104 /var/lib/nginx /sbin/nologin
add_member www-data nginx
add_group avahi 105
add_user avahi 104 105 /dev/null /sbin/nologin
add_group phonix 200
add_user phonix 200 200 /data /sbin/nologin
add_member asterisk phonix
# root: no password (console menu / service shell / ssh keys); the SSH
# root password from the web interface is set at boot (ssh-root-password)
sed -i 's/^root:[^:]*:/root:*:/' "$R/etc/shadow"

# --- packages ---------------------------------------------------------------
msg "[$BOARD] installing packages"
PKGS=$(pkglist "$IMG/profiles/common.packages" "$IMG/profiles/$BOARD.packages")
for _x in ${PACKAGES_EXCLUDE:-}; do
	PKGS=$(echo "$PKGS" | grep -vx -- "$_x")
done
# shellcheck disable=SC2086
apk_root "$R" add $PKGS \
	>"$BW/apk-install.log" 2>&1 || { tail -n 30 "$BW/apk-install.log"; die "apk add failed"; }
grep -E '^(ERROR|WARNING)' "$BW/apk-install.log" || true

# check that no package script wants a user we do not know about
tar -xzOf "$R/lib/apk/db/scripts.tar.gz" 2>/dev/null |
	sed -n 's/.*adduser .* \([a-z_][a-z0-9_-]*\) 2>.*/\1/p' | sort -u |
	while read -r u; do
		grep -q "^$u:" "$R/etc/passwd" || msg "WARNING: package script creates unknown user '$u'"
	done

# --- effects of the skipped install scripts ---------------------------------
busybox_links "$R"
chown root:42 "$R/etc/shadow"
chmod 640 "$R/etc/shadow"
if [ "${CONTAINER:-0}" = 1 ]; then
	# the kernel is the container host's
	KVER=none
	[ -z "$(ls -A "$R/lib/modules" 2>/dev/null)" ] || die "container board $BOARD has kernel modules installed"
else
	KVER=$(kernel_version "$R")
	[ -n "$KVER" ] || die "no kernel installed"
	# the kernel packages ship modules.dep & co. (kmod trigger not needed)
	[ -s "$R/lib/modules/$KVER/modules.dep" ] || depmod -b "$R" "$KVER"
fi
mkdir -p "$R/run/nginx"

# --- PhonixPBX image integration --------------------------------------------
# overlay, console, nginx, symlinks to /data, runlevels: the same script sets
# up an LXC container again after a package update (priv install-update)
msg "[$BOARD] system integration"
PHONIX_FIXUP_BUILD=1 PHONIX_ROOTFS_SRC="$SYS/rootfs" PHONIX_SERIAL_TTYS="$SERIAL_TTYS" \
	PHONIX_CLOCK_SERVICE="$CLOCK_SERVICE" \
	PHONIX_APK_REPOS="$(printf '%s\n' "$ALPINE_MIRROR/$ALPINE_BRANCH/main" "$ALPINE_MIRROR/$ALPINE_BRANCH/community")" \
	sh "$SYS/libexec/rootfs-fixup" "$R" "$BOARD" "$VERSION"

# version, update key
cp "$KEYS_DIR/update-key.pub" "$R/etc/phonix/update-key.pub"
chmod 644 "$R/etc/phonix/update-key.pub"
mkdir -p "$R/usr/share/phonix"
cat >"$R/usr/share/phonix/image-info" <<INFO
PHONIX_VERSION="$VERSION"
PHONIX_BOARD="$BOARD"
PHONIX_ARCH="$ARCH"
PHONIX_KERNEL="$KVER"
PHONIX_CONTAINER="${CONTAINER:-0}"
PHONIX_BUILD_DATE="$(date -u -d "@$SOURCE_DATE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
INFO

# --- trim ---------------------------------------------------------------------
# kernel, device trees and firmware blobs go to the boot partition
mkdir -p "$BW/boot"
rm -rf "${BW:?}/boot"/*
[ "${CONTAINER:-0}" = 1 ] || cp -a "$R/boot/." "$BW/boot/"
rm -rf "${R:?}/boot"/*
rm -rf "$R/var/cache/apk"/* "$R/usr/share/man" "$R/usr/share/doc" "$R/usr/share/info"

apk --root "$R" info -v 2>/dev/null | sort >"$BW/packages.txt"
msg "[$BOARD] root file system ready: $(du -sh "$R" | cut -f1), kernel $KVER, $(wc -l <"$BW/packages.txt") packages"
