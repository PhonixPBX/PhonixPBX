#!/bin/sh
# Build AskoziaPBX images (rootless, inside a podman/docker container).
#
#   image/build.sh [board...]        boards: pc-amd64 rpi-arm64 pc-x86 (default: pc-amd64)
#   image/build.sh all
#
# Steps: builder image -> askozia apk (abuild) -> per board: rootfs,
# initramfs, disk image + signed update bundle in out/.
#
# Environment:
#   ASKOZIA_VERSION              image version (default: pyproject.toml)
#   ASKOZIA_KEYS_DIR             keys directory (default image/keys)
#   ASKOZIA_UPDATE_SIGNING_KEY   ed25519 private key (default $ASKOZIA_KEYS_DIR/update-signing.pem)
#   ASKOZIA_ABUILD_KEY           RSA key for package signing (+ .pub next to it)
#   ALPINE_MIRROR                Alpine mirror URL
#   CONTAINER                    podman (default) or docker
#   SKIP_APK=1                   reuse the packages already in out/repo
set -eu
cd "$(dirname "$0")/.."
TOP=$(pwd)
CONTAINER=${CONTAINER:-podman}
BUILDER=askozia-imgbuild:3.24

boards=${*:-pc-amd64}
[ "$boards" = all ] && boards="pc-amd64 rpi-arm64 pc-x86"
for b in $boards; do
	[ -f "image/profiles/$b.conf" ] || { echo "unknown board $b" >&2; exit 1; }
done

KEYS=${ASKOZIA_KEYS_DIR:-$TOP/image/keys}
if [ -z "${ASKOZIA_UPDATE_SIGNING_KEY:-}" ] && [ ! -f "$KEYS/update-signing.pem" ]; then
	echo "WARNING: no update signing key - creating a throwaway development key in $KEYS" >&2
	image/keys.sh "$KEYS"
fi
if [ -n "${ASKOZIA_UPDATE_SIGNING_KEY:-}" ] && [ ! -f "$KEYS/update-key.pub" ]; then
	mkdir -p "$KEYS"
	openssl pkey -in "$ASKOZIA_UPDATE_SIGNING_KEY" -pubout -out "$KEYS/update-key.pub"
fi

: "${SOURCE_DATE_EPOCH:=$(git log -1 --format=%ct 2>/dev/null || date +%s)}"

"$CONTAINER" build -q -t "$BUILDER" -f image/Containerfile image >/dev/null

run() {
	# shellcheck disable=SC2046
	"$CONTAINER" run --rm \
		-v "$TOP:/src:z" \
		$( [ "$KEYS" != "$TOP/image/keys" ] && echo "-v $KEYS:/keys:z -e ASKOZIA_KEYS_DIR=/keys" ) \
		$( [ -n "${ASKOZIA_UPDATE_SIGNING_KEY:-}" ] && echo "-v $ASKOZIA_UPDATE_SIGNING_KEY:/run/signing.pem:ro,z -e ASKOZIA_UPDATE_SIGNING_KEY=/run/signing.pem" ) \
		$( [ -n "${ASKOZIA_ABUILD_KEY:-}" ] && echo "-v $ASKOZIA_ABUILD_KEY:/run/abuild.rsa:ro,z -v $ASKOZIA_ABUILD_KEY.pub:/run/abuild.rsa.pub:ro,z -e ASKOZIA_ABUILD_KEY=/run/abuild.rsa" ) \
		-e SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
		-e ASKOZIA_VERSION="${ASKOZIA_VERSION:-}" \
		-e ALPINE_MIRROR="${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}" \
		"$BUILDER" "$@"
}

[ "${SKIP_APK:-0}" = 1 ] || run /src/image/lib/build-apk.sh
for b in $boards; do
	run /src/image/lib/build-rootfs.sh "$b"
	run /src/image/lib/build-initramfs.sh "$b"
	run /src/image/lib/assemble.sh "$b"
done
ls -l out/
