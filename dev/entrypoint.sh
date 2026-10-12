#!/bin/sh
# Dev container entry point: first boot, generate config, start Asterisk and
# the web UI (auto-reload on code changes in /src).
set -eu
export PHONIX_DATA_DIR=/data \
       PHONIX_ROOT=/srv/root \
       PHONIX_PRIVILEGED=exec \
       PHONIX_LIBEXEC_DIR=/src/dev/libexec \
       PHONIX_BOOT_DIR=/data/boot \
       PHONIX_DEV=1 \
       PHONIX_LOG_ASTERISK=/var/log/asterisk/messages
WEB_PORT=${WEB_PORT:-8000}

mkdir -p /srv/root/etc/asterisk /data/boot /data/asterisk /var/lib/asterisk/keys \
         /var/log/asterisk /var/run/asterisk /var/spool/asterisk
phonix firstboot
# /etc/hostname etc. are bind mounts in containers: generate below /srv/root
# and only link the Asterisk configuration into place
if [ ! -L /etc/asterisk ]; then
	rm -rf /etc/asterisk
	ln -s /srv/root/etc/asterisk /etc/asterisk
fi
phonix apply --boot >/dev/null
chown -R asterisk:asterisk /data/asterisk /var/log/asterisk /var/run/asterisk /var/spool/asterisk
chgrp -R asterisk /srv/root/etc/asterisk /data/media /data/tls
chmod 750 /data && chgrp asterisk /data

/src/dev/libexec/priv asterisk-start
phonix monitor >/var/log/phonix-monitor.log 2>&1 &

phonix banner | sed "s#https://\([^/]*\)/#http://\1:$WEB_PORT/#"
echo "  Logs: podman exec -it phonix-dev asterisk -r"
echo
exec phonix web --host 0.0.0.0 --port "$WEB_PORT" --reload
