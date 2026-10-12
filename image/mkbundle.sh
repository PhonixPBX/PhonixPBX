#!/bin/sh
# Create a signed PhonixPBX update bundle.
#
#   mkbundle.sh <board> <version> <payload-dir> <signing-key.pem> <output.update>
#
# <payload-dir> contains rootfs.squashfs, vmlinuz, initramfs and, for the
# Raspberry Pi, boot.tar (device trees + overlays). The bundle is an
# uncompressed tar: manifest.json {version, board, files: {name: sha256}},
# manifest.sig (raw 64 byte ed25519 signature over manifest.json) and the
# payload files. Needs OpenSSL >= 3.0 and python3.
set -eu
[ $# -eq 5 ] || { echo "usage: $0 <board> <version> <payload-dir> <key.pem> <out.update>" >&2; exit 64; }
board=$1 version=$2 dir=$3 key=$4 out=$5
: "${SOURCE_DATE_EPOCH:=$(date +%s)}"

files="rootfs.squashfs vmlinuz initramfs"
[ -f "$dir/boot.tar" ] && files="$files boot.tar"
for f in $files; do
	[ -f "$dir/$f" ] || { echo "mkbundle: missing $dir/$f" >&2; exit 1; }
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM
# shellcheck disable=SC2086
python3 - "$board" "$version" "$dir" $files >"$tmp/manifest.json" <<'PY'
import hashlib, json, sys
board, version, directory, *names = sys.argv[1:]
files = {}
for name in names:
    h = hashlib.sha256()
    with open(f"{directory}/{name}", "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    files[name] = h.hexdigest()
json.dump({"version": version, "board": board, "files": files}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
PY
openssl pkeyutl -sign -rawin -inkey "$key" -in "$tmp/manifest.json" -out "$tmp/manifest.sig"
[ "$(wc -c <"$tmp/manifest.sig")" -eq 64 ] || { echo "mkbundle: unexpected signature size" >&2; exit 1; }
# verify with the public half before shipping
openssl pkey -in "$key" -pubout -out "$tmp/pub.pem"
openssl pkeyutl -verify -rawin -pubin -inkey "$tmp/pub.pem" -in "$tmp/manifest.json" \
	-sigfile "$tmp/manifest.sig" >/dev/null

for f in $files; do ln -s "$(cd "$dir" && pwd)/$f" "$tmp/$f"; done
# shellcheck disable=SC2086
tar -C "$tmp" --dereference --format=ustar --owner=0 --group=0 --numeric-owner \
	--mtime="@$SOURCE_DATE_EPOCH" -cf "$out.tmp" manifest.json manifest.sig $files
mv "$out.tmp" "$out"
echo "bundle: $out ($version, $board)"
