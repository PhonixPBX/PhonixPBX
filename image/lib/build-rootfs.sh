#!/bin/sh
# Build the root file system of a board into image/work/<board>/rootfs.
#   build-rootfs.sh <board>
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
add_group askozia 200
add_user askozia 200 200 /data /sbin/nologin
add_member asterisk askozia
# root: no password (console menu / service shell / ssh keys only)
sed -i 's/^root:[^:]*:/root:*:/' "$R/etc/shadow"

# --- packages ---------------------------------------------------------------
msg "[$BOARD] installing packages"
# shellcheck disable=SC2046
apk_root "$R" add $(pkglist "$IMG/profiles/common.packages" "$IMG/profiles/$BOARD.packages") \
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
KVER=$(kernel_version "$R")
[ -n "$KVER" ] || die "no kernel installed"
# the kernel packages ship modules.dep & co. (kmod trigger not needed)
[ -s "$R/lib/modules/$KVER/modules.dep" ] || depmod -b "$R" "$KVER"
rm -f "$R/etc/nginx/http.d/default.conf"
mkdir -p "$R/run/nginx"

# --- AskoziaPBX image integration --------------------------------------------
msg "[$BOARD] system integration"
cp -a "$SYS/rootfs/." "$R/"
chmod 644 "$R/etc/inittab" "$R/etc/fstab"
for t in $SERIAL_TTYS; do
	sed -i "/^::ctrlaltdel/i ::respawn:/usr/libexec/askozia/console $t" "$R/etc/inittab"
done

# Asterisk: the configuration is generated at boot (askozia apply)
rm -rf "$R/etc/asterisk"
install -d -m 0750 "$R/etc/asterisk"
chown 200:102 "$R/etc/asterisk"
install -d -m 0750 -o 200 -g 102 "$R/etc/askozia"
mkdir -p "$R/var/lib/asterisk/keys"
chown -R 101:102 "$R/var/lib/asterisk" "$R/var/spool/asterisk" "$R/var/log/asterisk" 2>/dev/null || true

# board, version, update key
echo "$BOARD" >"$R/etc/askozia/board"
cp "$KEYS_DIR/update-key.pub" "$R/etc/askozia/update-key.pub"
chmod 644 "$R/etc/askozia/board" "$R/etc/askozia/update-key.pub"
mkdir -p "$R/usr/share/askozia"
cat >"$R/usr/share/askozia/image-info" <<INFO
ASKOZIA_VERSION="$VERSION"
ASKOZIA_BOARD="$BOARD"
ASKOZIA_ARCH="$ARCH"
ASKOZIA_KERNEL="$KVER"
ASKOZIA_BUILD_DATE="$(date -u -d "@$SOURCE_DATE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
INFO
sed -i "s/^PRETTY_NAME=.*/PRETTY_NAME=\"AskoziaPBX $VERSION (Alpine Linux $(cat "$R/etc/alpine-release"))\"/" \
	"$R/etc/os-release"

# persistent state on /data
mkdir -p "$R/data" "$R/media/boot" "$R/media/root-ro" "$R/media/overlay"
rm -rf "$R/etc/dropbear"
ln -s /data/ssh/dropbear "$R/etc/dropbear"
install -d -m 0700 "$R/root/.ssh"
ln -sfn /data/ssh/authorized_keys "$R/root/.ssh/authorized_keys"

# apk is not used on the read-only system; point it at the real repositories
printf '%s\n' "$ALPINE_MIRROR/$ALPINE_BRANCH/main" "$ALPINE_MIRROR/$ALPINE_BRANCH/community" \
	>"$R/etc/apk/repositories"

# --- services -----------------------------------------------------------------
rl() { # runlevel service...
	_lvl=$1
	shift
	mkdir -p "$R/etc/runlevels/$_lvl"
	for _s in "$@"; do
		[ -e "$R/etc/init.d/$_s" ] || die "missing service $_s"
		ln -sfn "/etc/init.d/$_s" "$R/etc/runlevels/$_lvl/$_s"
	done
}
rm -rf "$R/etc/runlevels"
rl sysinit devfs dmesg mdev hwdrivers
rl boot modules sysctl hostname bootmisc syslog klogd seedrng "$CLOCK_SERVICE" \
	askozia-firstboot askozia-apply nftables networking
rl default acpid crond chronyd asterisk askozia-web nginx askozia-monitor askozia-healthcheck
rl shutdown killprocs savecache mount-ro
mkdir -p "$R/etc/runlevels/nonetwork"

# --- trim ---------------------------------------------------------------------
# kernel, device trees and firmware blobs go to the boot partition
mkdir -p "$BW/boot"
rm -rf "${BW:?}/boot"/*
cp -a "$R/boot/." "$BW/boot/"
rm -rf "${R:?}/boot"/*
rm -rf "$R/var/cache/apk"/* "$R/usr/share/man" "$R/usr/share/doc" "$R/usr/share/info"

apk --root "$R" info -v 2>/dev/null | sort >"$BW/packages.txt"
msg "[$BOARD] root file system ready: $(du -sh "$R" | cut -f1), kernel $KVER, $(wc -l <"$BW/packages.txt") packages"
