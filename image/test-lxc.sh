#!/bin/sh
# Boot test of the LXC/Incus root file system tarball as a podman/docker
# system container (no LXC needed).
#
#   image/test-lxc.sh [out/phonix-<version>-lxc-amd64.tar.xz]
#
# Imports the tarball as an image, boots it with /sbin/init (busybox init +
# OpenRC, as in LXC), waits until https://localhost:<port>/login answers 200
# and Asterisk runs, checks board, runlevels and data ownership, creates a
# phone through the REST API and applies it, and finally halts the container
# the way LXC/Incus do (SIGPWR) and checks that it stopped cleanly.
#
# The container engine owns the network here, so ifupdown-ng only brings up
# lo (in LXC/Incus/Proxmox it configures eth0). Environment: CONTAINER
# (podman, docker), PORT (host port for 443, default 18443), TIMEOUT (300).
set -eu
ENGINE=${CONTAINER:-podman}
PORT=${PORT:-18443}
TIMEOUT=${TIMEOUT:-300}
tarball=${1:-}
if [ -z "$tarball" ]; then
	for tarball in out/phonix-*-lxc-amd64.tar.xz; do :; done
fi
[ -f "$tarball" ] || { echo "usage: $0 <phonix-...-lxc-<arch>.tar.xz>" >&2; exit 64; }
name=phonix-lxc-test-$$
image=localhost/phonix-lxc-test:$$
tmp=$(mktemp -d)

cleanup() {
	"$ENGINE" rm -f "$name" >/dev/null 2>&1 || true
	"$ENGINE" rmi -f "$image" >/dev/null 2>&1 || true
	rm -rf "$tmp"
}
trap cleanup EXIT INT TERM

fail() {
	echo "FAIL: $*" >&2
	"$ENGINE" logs "$name" 2>&1 | tail -n 60 >&2 || true
	exit 1
}

in_ct() {
	"$ENGINE" exec "$name" sh -c "$1"
}

echo "== importing $tarball"
# podman cannot import xz compressed tarballs reliably
xz -dc "$tarball" >"$tmp/rootfs.tar"
"$ENGINE" import "$tmp/rootfs.tar" "$image" >/dev/null
rm -f "$tmp/rootfs.tar"

echo "== booting"
"$ENGINE" run -d --name "$name" -t \
	--cap-add NET_ADMIN --cap-add NET_RAW --cap-add SYS_CHROOT --cap-add AUDIT_WRITE \
	--stop-signal SIGPWR -p "127.0.0.1:$PORT:443" "$image" \
	/bin/sh -c 'printf "auto lo\niface lo inet loopback\n" >/etc/network/interfaces; exec /sbin/init' >/dev/null

t=0
until [ "$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$PORT/login")" = 200 ]; do
	t=$((t + 5))
	[ $t -lt "$TIMEOUT" ] || fail "no web interface after ${TIMEOUT}s"
	sleep 5
done
echo "ok: https://127.0.0.1:$PORT/login answers 200 after ~${t}s"
in_ct 'asterisk -rx "core show version"' | grep -q '^Asterisk 22' || fail "Asterisk is not running"
echo "ok: Asterisk 22 running"

board=$(in_ct 'cat /etc/phonix/board')
case "$board" in lxc-*) echo "ok: board $board" ;; *) fail "unexpected board '$board'" ;; esac
for svc in phonix-firstboot phonix-apply asterisk phonix-web nginx phonix-monitor; do
	in_ct "rc-service $svc status" >/dev/null 2>&1 || fail "service $svc is not started"
done
echo "ok: PhonixPBX services started"
[ "$(in_ct 'ps -o user,args | grep "[p]honix web" | cut -d" " -f1')" = phonix ] ||
	fail "web process does not run as user phonix"
echo "ok: web process runs as phonix"
own=$(in_ct 'stat -c "%U:%G" /data/ssh /data/spool /data/tmp/nginx /data/phonix.db /etc/asterisk' | tr '\n' ' ')
[ "$own" = "root:root asterisk:asterisk nginx:nginx phonix:phonix phonix:asterisk " ] ||
	fail "unexpected ownership: $own"
echo "ok: ownership $own"
in_ct 'su -s /bin/sh phonix -c "doas -n /usr/libexec/phonix/priv install-update /data/x.update"' 2>&1 |
	grep -q container || fail "install-update is not refused in the container"
echo "ok: firmware updates are refused"

in_ct 'test -s /data/state/initial-admin-password' || fail "no initial admin password"
token=$(in_ct 'phonix token create smoke-test' | tail -n 1)
case "$token" in phx_*) ;; *) fail "no API token: $token" ;; esac
auth="Authorization: Bearer $token"
code=$(curl -sk -o /dev/null -w '%{http_code}' -H "$auth" -H 'Content-Type: application/json' \
	-d '{"extension":"777","callerid":"LXC test"}' "https://127.0.0.1:$PORT/api/v1/phones")
[ "$code" = 201 ] || fail "creating a phone through the API: HTTP $code"
curl -sk -H "$auth" -X POST "https://127.0.0.1:$PORT/api/v1/apply" | grep -q '"ok":true' || fail "apply failed"
in_ct 'asterisk -rx "pjsip show endpoint 777"' | grep -q 'Endpoint:  777' || fail "phone 777 not in Asterisk"
in_ct 'test ! -e /etc/network/interfaces.priv-new && grep -q "iface lo" /etc/network/interfaces' ||
	fail "PhonixPBX touched /etc/network/interfaces"
echo "ok: phone created and applied through the REST API, network config left alone"

echo "== halting (SIGPWR)"
"$ENGINE" stop -t 60 "$name" >/dev/null
rc=$("$ENGINE" inspect "$name" --format '{{.State.ExitCode}}')
"$ENGINE" logs "$name" 2>&1 | grep -q 'Stopping asterisk' || fail "OpenRC did not stop the services"
[ "$rc" = 0 ] || fail "exit code $rc after halt"
echo "ok: clean halt"
echo "PASS"
