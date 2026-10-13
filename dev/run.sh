#!/bin/sh
# SPDX-FileCopyrightText: 2026 The PhonixPBX contributors
# SPDX-License-Identifier: Apache-2.0
# Run PhonixPBX locally in the Alpine dev container (podman or docker).
#
#   dev/run.sh            start (web UI on http://<host>:8000, SIP on 5060/udp)
#   dev/run.sh --reset    start with a fresh data volume
#   dev/run.sh --demo     fill an empty PBX with demo data (for screenshots)
#   dev/console.sh        console menu (phonix tui) of the running container
#
# Host networking is used so SIP/RTP work for softphones on your LAN.
# Configuration and data persist in the "phonix-dev-data" volume.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
ENGINE=${CONTAINER_ENGINE:-podman}
IMAGE=phonix-dev:3.24
VOLUME=phonix-dev-data

DEMO=0
for arg in "$@"; do
	case $arg in
	--reset) "$ENGINE" volume rm -f "$VOLUME" >/dev/null 2>&1 || true ;;
	--demo) DEMO=1 ;;
	*) echo "usage: $0 [--reset] [--demo]" >&2; exit 2 ;;
	esac
done
"$ENGINE" image inspect "$IMAGE" >/dev/null 2>&1 || "$ENGINE" build -t "$IMAGE" -f "$ROOT/dev/Containerfile" "$ROOT/dev"

exec "$ENGINE" run --rm -it --name phonix-dev --network host \
	-e WEB_PORT="${WEB_PORT:-8000}" -e PHONIX_DEMO="$DEMO" \
	-e PHONIX_DATA_DIR=/data -e PHONIX_ROOT=/srv/root -e PHONIX_PRIVILEGED=exec \
	-e PHONIX_LIBEXEC_DIR=/src/dev/libexec -e PHONIX_BOOT_DIR=/data/boot -e PHONIX_DEV=1 \
	-e PHONIX_LOG_ASTERISK=/var/log/asterisk/messages \
	-v "$ROOT:/src:Z" -v "$VOLUME:/data" \
	"$IMAGE" /src/dev/entrypoint.sh
