#!/bin/sh
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
add_group phonix 200
add_user phonix 200 200 /data /sbin/nologin
add_member asterisk phonix
# root: no password (console menu / service shell / ssh keys only)
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
rm -f "$R/etc/nginx/http.d/default.conf"
mkdir -p "$R/run/nginx"

# --- PhonixPBX image integration --------------------------------------------
msg "[$BOARD] system integration"
cp -a "$SYS/rootfs/." "$R/"
# cp -a keeps the checkout's modes (group writable with umask 002)
chmod 755 "$R"
(cd "$SYS/rootfs" && find . -mindepth 1 ! -type l) | while read -r _p; do chmod go-w "$R/$_p"; done
chmod 644 "$R/etc/inittab" "$R/etc/fstab"
for t in $SERIAL_TTYS; do
	sed -i "/^::ctrlaltdel/i ::respawn:/usr/libexec/phonix/console $t" "$R/etc/inittab"
done
if [ "${CONTAINER:-0}" = 1 ]; then
	# container console (incus console, lxc-console -t 0, pct console with
	# cmode=console); tty1 stays for lxc-console / pct console (cmode=tty)
	sed -i "/^::ctrlaltdel/i ::respawn:/usr/libexec/phonix/console console" "$R/etc/inittab"
	sed -i 's/^# \/etc\/inittab - PhonixPBX appliance/# \/etc\/inittab - PhonixPBX system container/' "$R/etc/inittab"
	# Proxmox VE appends "ttyN::respawn:/sbin/getty" lines to the inittab of
	# Alpine containers at every start; a getty on tty1 next to the console
	# menu makes both fight over the terminal
	: >"$R/etc/.pve-ignore.inittab"
	sed -i '1s/.*/# Default for system containers: DHCP on eth0. Not managed by PhonixPBX;\n# Proxmox VE rewrites this file from the container settings./' \
		"$R/etc/network/interfaces"
	cat >"$R/etc/fstab" <<'FSTAB'
# PhonixPBX system container: the root file system and /data are set up by
# the container host (LXC, Incus, Proxmox VE).
FSTAB
	cat >"$R/etc/motd" <<'MOTD'

PhonixPBX system container. Configuration lives in /data/phonix.db; use the
web interface or the "phonix" command. Files that PhonixPBX generates (e.g.
/etc/asterisk) are rewritten at every start. Network and host name are
configured on the container host.

MOTD
fi

# Asterisk: the configuration is generated at boot (phonix apply)
rm -rf "$R/etc/asterisk"
install -d -m 0750 "$R/etc/asterisk"
chown 200:102 "$R/etc/asterisk"
install -d -m 0750 -o 200 -g 102 "$R/etc/phonix"
mkdir -p "$R/var/lib/asterisk/keys"
chown -R 101:102 "$R/var/lib/asterisk" "$R/var/spool/asterisk" "$R/var/log/asterisk" 2>/dev/null || true

# board, version, update key
echo "$BOARD" >"$R/etc/phonix/board"
cp "$KEYS_DIR/update-key.pub" "$R/etc/phonix/update-key.pub"
chmod 644 "$R/etc/phonix/board" "$R/etc/phonix/update-key.pub"
mkdir -p "$R/usr/share/phonix"
cat >"$R/usr/share/phonix/image-info" <<INFO
PHONIX_VERSION="$VERSION"
PHONIX_BOARD="$BOARD"
PHONIX_ARCH="$ARCH"
PHONIX_KERNEL="$KVER"
PHONIX_CONTAINER="${CONTAINER:-0}"
PHONIX_BUILD_DATE="$(date -u -d "@$SOURCE_DATE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
INFO
sed -i "s/^PRETTY_NAME=.*/PRETTY_NAME=\"PhonixPBX $VERSION (Alpine Linux $(cat "$R/etc/alpine-release"))\"/" \
	"$R/etc/os-release"

# persistent state on /data
mkdir -p "$R/data" "$R/media/boot"
[ "${CONTAINER:-0}" = 1 ] || mkdir -p "$R/media/root-ro" "$R/media/overlay"
if [ "${CONTAINER:-0}" = 1 ]; then
	# no bind mount needed: voicemail and other spool data live on /data
	rm -rf "$R/var/spool/asterisk"
	ln -s /data/spool "$R/var/spool/asterisk"
fi
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
if [ "${CONTAINER:-0}" = 1 ]; then
	# no devices, modules, sysctl, kernel log, hardware clock, ACPI or entropy
	# seeding (the host's business); time comes from the host (no chronyd);
	# no A/B slots (no phonix-healthcheck); the host mounts the file systems
	# and sets the host name (lxc.uts.name)
	mkdir -p "$R/etc/runlevels/sysinit"
	rl boot bootmisc syslog phonix-firstboot phonix-apply nftables networking
	rl default crond asterisk phonix-web nginx phonix-monitor
	rl shutdown killprocs savecache
else
	rl sysinit devfs dmesg mdev hwdrivers
	rl boot modules sysctl hostname bootmisc syslog klogd seedrng "$CLOCK_SERVICE" \
		phonix-firstboot phonix-apply nftables networking
	rl default acpid crond chronyd asterisk phonix-web nginx phonix-monitor phonix-healthcheck
	rl shutdown killprocs savecache mount-ro
fi
mkdir -p "$R/etc/runlevels/nonetwork"

# --- trim ---------------------------------------------------------------------
# kernel, device trees and firmware blobs go to the boot partition
mkdir -p "$BW/boot"
rm -rf "${BW:?}/boot"/*
[ "${CONTAINER:-0}" = 1 ] || cp -a "$R/boot/." "$BW/boot/"
rm -rf "${R:?}/boot"/*
rm -rf "$R/var/cache/apk"/* "$R/usr/share/man" "$R/usr/share/doc" "$R/usr/share/info"

apk --root "$R" info -v 2>/dev/null | sort >"$BW/packages.txt"
msg "[$BOARD] root file system ready: $(du -sh "$R" | cut -f1), kernel $KVER, $(wc -l <"$BW/packages.txt") packages"
