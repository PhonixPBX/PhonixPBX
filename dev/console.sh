#!/bin/sh
# Open the console menu (phonix tui) of the running dev container.
# Extra arguments run another phonix command instead, e.g. dev/console.sh banner
set -eu
ENGINE=${CONTAINER_ENGINE:-podman}
[ $# -gt 0 ] || set -- tui
exec "$ENGINE" exec -it \
	-e PHONIX_DATA_DIR=/data -e PHONIX_ROOT=/srv/root -e PHONIX_PRIVILEGED=exec \
	-e PHONIX_LIBEXEC_DIR=/src/dev/libexec -e PHONIX_BOOT_DIR=/data/boot -e PHONIX_DEV=1 \
	phonix-dev phonix "$@"
