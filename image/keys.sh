#!/bin/sh
# Create the ed25519 key pair that signs AskoziaPBX update bundles.
#
#   image/keys.sh [directory]      (default: image/keys, or $ASKOZIA_KEYS_DIR)
#
# Writes update-signing.pem (private, PKCS#8 - keep it offline / in a CI
# secret, never commit it) and update-key.pub (SubjectPublicKeyInfo PEM).
# The public key is baked into every image as /etc/askozia/update-key.pub;
# images only accept bundles signed with the matching private key.
# Needs OpenSSL >= 1.1.1 (host or the build container).
set -eu
dir=${1:-${ASKOZIA_KEYS_DIR:-$(cd "$(dirname "$0")" && pwd)/keys}}
mkdir -p "$dir"
if [ -e "$dir/update-signing.pem" ]; then
	echo "keys.sh: $dir/update-signing.pem exists, not overwriting" >&2
	exit 1
fi
umask 077
openssl genpkey -algorithm ed25519 -out "$dir/update-signing.pem"
umask 022
openssl pkey -in "$dir/update-signing.pem" -pubout -out "$dir/update-key.pub"
echo "private key: $dir/update-signing.pem (keep secret)"
echo "public key:  $dir/update-key.pub"
