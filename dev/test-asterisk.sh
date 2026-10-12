#!/bin/sh
# Run the Asterisk/SIPp integration tests inside the Alpine dev container.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
ENGINE=${CONTAINER_ENGINE:-podman}
"$ENGINE" image exists askozia-dev:3.24 2>/dev/null || "$ENGINE" build -t askozia-dev:3.24 -f "$ROOT/dev/Containerfile" "$ROOT/dev"
exec "$ENGINE" run --rm -v "$ROOT:/src:Z" -w /src askozia-dev:3.24 \
    python3 -m pytest -p no:cacheprovider -m asterisk tests/integration -v "$@"
