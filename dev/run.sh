#!/bin/sh
# Run PhonixPBX locally in the Alpine dev container (podman or docker).
#
#   dev/run.sh            start (web UI on http://<host>:8000, SIP on 5060/udp)
#   dev/run.sh --reset    start with a fresh data volume
#
# Host networking is used so SIP/RTP work for softphones on your LAN.
# Configuration and data persist in the "phonix-dev-data" volume.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
ENGINE=${CONTAINER_ENGINE:-podman}
IMAGE=phonix-dev:3.24
VOLUME=phonix-dev-data

if [ "${1:-}" = "--reset" ]; then
	"$ENGINE" volume rm -f "$VOLUME" >/dev/null 2>&1 || true
fi
"$ENGINE" image inspect "$IMAGE" >/dev/null 2>&1 || "$ENGINE" build -t "$IMAGE" -f "$ROOT/dev/Containerfile" "$ROOT/dev"

exec "$ENGINE" run --rm -it --name phonix-dev --network host \
	-e WEB_PORT="${WEB_PORT:-8000}" \
	-v "$ROOT:/src:Z" -v "$VOLUME:/data" \
	"$IMAGE" /src/dev/entrypoint.sh
