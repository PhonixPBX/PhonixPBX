#!/bin/sh
# Build PhonixPBX images (rootless, inside a podman/docker container).
#
#   image/build.sh [board...]        boards: pc-amd64 rpi-arm64 pc-x86
#                                    lxc-amd64 lxc-arm64 (default: pc-amd64)
#   image/build.sh all
#
# Steps: builder image -> phonix apk (abuild) -> per board: rootfs,
# initramfs, disk image + signed update bundle in out/. Container boards
# (lxc-*) get rootfs + LXC/Incus image tarballs instead.
#
# Environment:
#   PHONIX_VERSION              image version (default: pyproject.toml)
#   PHONIX_KEYS_DIR             keys directory (default image/keys)
#   PHONIX_UPDATE_SIGNING_KEY   ed25519 private key (default $PHONIX_KEYS_DIR/update-signing.pem)
#   PHONIX_ABUILD_KEY           RSA key for package signing (+ .pub next to it)
#   ALPINE_MIRROR                Alpine mirror URL
#   CONTAINER                    podman (default) or docker
#   SKIP_APK=1                   reuse the packages already in out/repo
set -eu
cd "$(dirname "$0")/.."
TOP=$(pwd)
CONTAINER=${CONTAINER:-podman}
BUILDER=phonix-imgbuild:3.24

boards=${*:-pc-amd64}
[ "$boards" = all ] && boards="pc-amd64 rpi-arm64 pc-x86 lxc-amd64 lxc-arm64"
for b in $boards; do
	[ -f "image/profiles/$b.conf" ] || { echo "unknown board $b" >&2; exit 1; }
done

KEYS=${PHONIX_KEYS_DIR:-$TOP/image/keys}
if [ -z "${PHONIX_UPDATE_SIGNING_KEY:-}" ] && [ ! -f "$KEYS/update-signing.pem" ]; then
	echo "WARNING: no update signing key - creating a throwaway development key in $KEYS" >&2
	image/keys.sh "$KEYS"
fi
if [ -n "${PHONIX_UPDATE_SIGNING_KEY:-}" ] && [ ! -f "$KEYS/update-key.pub" ]; then
	mkdir -p "$KEYS"
	openssl pkey -in "$PHONIX_UPDATE_SIGNING_KEY" -pubout -out "$KEYS/update-key.pub"
fi

: "${SOURCE_DATE_EPOCH:=$(git log -1 --format=%ct 2>/dev/null || date +%s)}"

"$CONTAINER" build -q -t "$BUILDER" -f image/Containerfile image >/dev/null

run() {
	# shellcheck disable=SC2046
	"$CONTAINER" run --rm \
		-v "$TOP:/src:z" \
		$( [ "$KEYS" != "$TOP/image/keys" ] && echo "-v $KEYS:/keys:z -e PHONIX_KEYS_DIR=/keys" ) \
		$( [ -n "${PHONIX_UPDATE_SIGNING_KEY:-}" ] && echo "-v $PHONIX_UPDATE_SIGNING_KEY:/run/signing.pem:ro,z -e PHONIX_UPDATE_SIGNING_KEY=/run/signing.pem" ) \
		$( [ -n "${PHONIX_ABUILD_KEY:-}" ] && echo "-v $PHONIX_ABUILD_KEY:/run/abuild.rsa:ro,z -v $PHONIX_ABUILD_KEY.pub:/run/abuild.rsa.pub:ro,z -e PHONIX_ABUILD_KEY=/run/abuild.rsa" ) \
		-e SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
		-e PHONIX_VERSION="${PHONIX_VERSION:-}" \
		-e ALPINE_MIRROR="${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}" \
		"$BUILDER" "$@"
}

[ "${SKIP_APK:-0}" = 1 ] || run /src/image/lib/build-apk.sh
for b in $boards; do
	run /src/image/lib/build-rootfs.sh "$b"
	if grep -q '^CONTAINER=1' "image/profiles/$b.conf"; then
		run /src/image/lib/assemble-container.sh "$b"
	else
		run /src/image/lib/build-initramfs.sh "$b"
		run /src/image/lib/assemble.sh "$b"
	fi
done
ls -l out/
