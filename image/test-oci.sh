#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Smoke test of the OCI container image (Containerfile).
#
#   image/test-oci.sh [image]          (default: localhost/phonix:test)
#
# Runs the image with a fresh data volume and published ports, waits until
# https://localhost:<port>/login answers 200, the health check passes and
# Asterisk runs, checks that the web process runs as user phonix, creates a
# phone through the REST API (bearer token from "phonix token create" in the
# container) and applies it, then stops the container with
# SIGTERM and checks the exit code. Environment: CONTAINER (podman, docker),
# PORT (host port for 443, default 28443), TIMEOUT (300).
set -eu
ENGINE=${CONTAINER:-podman}
PORT=${PORT:-28443}
TIMEOUT=${TIMEOUT:-300}
image=${1:-localhost/phonix:test}
name=phonix-oci-test-$$
volume=phonix-oci-test-$$

cleanup() {
	"$ENGINE" rm -f "$name" >/dev/null 2>&1 || true
	"$ENGINE" volume rm -f "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

fail() {
	echo "FAIL: $*" >&2
	"$ENGINE" logs "$name" 2>&1 | tail -n 60 >&2 || true
	exit 1
}

echo "== starting $image"
"$ENGINE" run -d --name "$name" -v "$volume:/data" \
	-p "127.0.0.1:$PORT:443" -p "127.0.0.1:$((PORT + 1)):5060/udp" "$image" >/dev/null

t=0
until [ "$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$PORT/login")" = 200 ]; do
	t=$((t + 5))
	[ $t -lt "$TIMEOUT" ] || fail "no web interface after ${TIMEOUT}s"
	"$ENGINE" inspect "$name" --format '{{.State.Running}}' | grep -q true || fail "container exited"
	sleep 5
done
echo "ok: https://127.0.0.1:$PORT/login answers 200 after ~${t}s"
"$ENGINE" exec "$name" asterisk -rx "core show version" | grep -q '^Asterisk 22' || fail "Asterisk is not running"
echo "ok: Asterisk 22 running"
"$ENGINE" exec "$name" /usr/libexec/phonix/healthcheck >/dev/null || fail "health check fails"
echo "ok: health check"
[ "$("$ENGINE" exec "$name" sh -c 'ps -o user,args | grep "[p]honix web" | cut -d" " -f1')" = phonix ] ||
	fail "web process does not run as user phonix"
echo "ok: web process runs as phonix"
"$ENGINE" exec "$name" cat /etc/phonix/board | grep -q '^oci-' || fail "board is not oci-*"

# the entrypoint prints the banner only after the web socket is up, so the
# web interface can answer before the password is in the log
t=0
until pw=$("$ENGINE" logs "$name" 2>&1 | sed -n 's/.*Initial login: admin \/ \([^ ]*\).*/\1/p' | tail -n 1) &&
	[ -n "$pw" ]; do
	t=$((t + 1))
	[ $t -lt 60 ] || fail "no initial admin password in the container log"
	sleep 1
done
echo "ok: initial admin password in the log"
token=$("$ENGINE" exec "$name" phonix token create smoke-test | tail -n 1)
case "$token" in phx_*) ;; *) fail "no API token: $token" ;; esac
auth="Authorization: Bearer $token"
code=$(curl -sk -o /dev/null -w '%{http_code}' -H "$auth" -H 'Content-Type: application/json' \
	-d '{"extension":"777","callerid":"OCI test"}' "https://127.0.0.1:$PORT/api/v1/phones")
[ "$code" = 201 ] || fail "creating a phone through the API: HTTP $code"
curl -sk -H "$auth" -X POST "https://127.0.0.1:$PORT/api/v1/apply" | grep -q '"ok":true' || fail "apply failed"
"$ENGINE" exec "$name" asterisk -rx "pjsip show endpoint 777" | grep -q 'Endpoint:  777' ||
	fail "phone 777 not in Asterisk"
echo "ok: phone created and applied through the REST API"

echo "== stopping (SIGTERM)"
"$ENGINE" stop -t 20 "$name" >/dev/null
rc=$("$ENGINE" inspect "$name" --format '{{.State.ExitCode}}')
"$ENGINE" logs "$name" 2>&1 | tail -n 1 | grep -q 'phonix: stopped' || fail "no clean shutdown"
[ "$rc" = 0 ] || fail "exit code $rc after SIGTERM"
echo "ok: clean shutdown"
echo "PASS"
