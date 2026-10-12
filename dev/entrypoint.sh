#!/bin/sh
# Dev container entry point: first boot, generate config, start Asterisk and
# the web UI (auto-reload on code changes in /src).
set -eu
export ASKOZIA_DATA_DIR=/data \
       ASKOZIA_ROOT=/srv/root \
       ASKOZIA_PRIVILEGED=exec \
       ASKOZIA_LIBEXEC_DIR=/src/dev/libexec \
       ASKOZIA_BOOT_DIR=/data/boot \
       ASKOZIA_DEV=1 \
       ASKOZIA_LOG_ASTERISK=/var/log/asterisk/messages
WEB_PORT=${WEB_PORT:-8000}

mkdir -p /srv/root/etc/asterisk /data/boot /data/asterisk /var/lib/asterisk/keys \
         /var/log/asterisk /var/run/asterisk /var/spool/asterisk
askozia firstboot
# /etc/hostname etc. are bind mounts in containers: generate below /srv/root
# and only link the Asterisk configuration into place
if [ ! -L /etc/asterisk ]; then
	rm -rf /etc/asterisk
	ln -s /srv/root/etc/asterisk /etc/asterisk
fi
askozia apply --boot >/dev/null
chown -R asterisk:asterisk /data/asterisk /var/log/asterisk /var/run/asterisk /var/spool/asterisk
chgrp -R asterisk /srv/root/etc/asterisk /data/media /data/tls
chmod 750 /data && chgrp asterisk /data

/src/dev/libexec/priv asterisk-start
askozia monitor >/var/log/askozia-monitor.log 2>&1 &

askozia banner | sed "s#https://\([^/]*\)/#http://\1:$WEB_PORT/#"
echo "  Logs: podman exec -it askozia-dev asterisk -r"
echo
exec askozia web --host 0.0.0.0 --port "$WEB_PORT" --reload
