# PhonixPBX OCI container image (ghcr.io/phonixpbx/phonix), linux/amd64 + linux/arm64.
#
#   podman build -t phonix .        (or: docker build -f Containerfile -t phonix .)
#   podman run -d --name phonix --network host -v phonix-data:/data phonix
#
# Same Alpine release, packages and file layout as the appliance images
# (image/), without OpenRC: /usr/libexec/phonix/entrypoint starts and
# supervises Asterisk, the web interface (user phonix, unix socket), the
# security monitor and nginx (TLS on 443). Privileged actions of the web
# process go through doas to a container-specific root helper. All state is
# in the /data volume. See docs/INSTALL.md, "Container image".
#
# This file is at the top of the repository because the build context must
# be the repository root (Python package + system/ files); .dockerignore
# keeps the context small.
ARG ALPINE_VERSION=3.24

# --- build the phonix wheel and install it into a staging root ---------------
FROM docker.io/library/alpine:${ALPINE_VERSION} AS build
RUN apk add --no-cache python3 py3-gpep517 py3-setuptools py3-wheel py3-installer
WORKDIR /src
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY phonix ./phonix
RUN gpep517 build-wheel --wheel-dir /dist --output-fd 3 3>&1 >&2 \
    && python3 -m installer --destdir /staging /dist/*.whl

# --- runtime ------------------------------------------------------------------
FROM docker.io/library/alpine:${ALPINE_VERSION}
ARG TARGETARCH=amd64
ARG PHONIX_VERSION=

# fixed ids, identical to the appliance and LXC images (build-rootfs.sh), so a
# /data volume can move between them; the package scripts keep existing ones
RUN addgroup -S -g 102 asterisk \
    && adduser -S -D -H -u 101 -h /var/lib/asterisk -s /sbin/nologin -G asterisk -g asterisk asterisk \
    && addgroup -S -g 104 nginx \
    && adduser -S -D -H -u 103 -h /var/lib/nginx -s /sbin/nologin -G nginx -g nginx nginx \
    && addgroup -S -g 200 phonix \
    && adduser -S -D -H -u 200 -h /data -s /sbin/nologin -G phonix -g phonix phonix \
    && addgroup phonix asterisk

# runtime dependencies: packaging/apk/phonix/APKBUILD minus everything that
# belongs to the host (kernel, chrony, ssh, file system tools, OpenRC)
RUN apk add --no-cache \
        asterisk asterisk-sounds-en asterisk-sounds-moh asterisk-srtp asterisk-opus asterisk-speex \
        python3 py3-fastapi uvicorn py3-pydantic py3-sqlalchemy py3-alembic py3-jinja2 \
        py3-argon2-cffi py3-itsdangerous py3-python-multipart py3-babel py3-defusedxml \
        py3-cryptography py3-zstandard py3-httpx \
        nginx msmtp nftables sox doas su-exec tini logrotate lego \
        tzdata ca-certificates-bundle iproute2 curl \
    && rm -f /etc/nginx/http.d/default.conf \
    && sed -i 's/^worker_processes .*/worker_processes 1;/' /etc/nginx/nginx.conf \
    && grep -q '^worker_processes 1;' /etc/nginx/nginx.conf

COPY --from=build /staging/ /
COPY system/ /tmp/system/
RUN set -eu; S=/tmp/system; L=/usr/libexec/phonix; \
    install -Dm755 "$S/container/entrypoint" "$L/entrypoint"; \
    install -Dm755 "$S/container/priv" "$L/priv"; \
    install -Dm755 "$S/container/healthcheck" "$L/healthcheck"; \
    install -Dm755 "$S/libexec/notify" "$L/notify"; \
    install -Dm400 "$S/doas.d/phonix.conf" /etc/doas.d/phonix.conf; \
    install -Dm644 "$S/nginx/phonix.conf" /usr/share/phonix/nginx-phonix.conf; \
    install -Dm644 "$S/logrotate.d/phonix" /etc/logrotate.d/phonix; \
    install -Dm755 "$S/periodic/phonix-cert" /etc/periodic/daily/phonix-cert; \
    install -Dm755 "$S/periodic/phonix-update" /etc/periodic/daily/phonix-update; \
    install -Dm644 "$S/rootfs/etc/nftables.nft" /etc/nftables.nft; \
    rm -rf "$S"; \
    pyver=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")'); \
    ln -s "../../lib/python$pyver/site-packages/phonix/web/static" /usr/share/phonix/static; \
    test -f /usr/share/phonix/static/img/favicon.svg; \
    rm -rf /etc/asterisk; \
    install -d -m 0750 -o phonix -g asterisk /etc/asterisk /etc/phonix; \
    echo "oci-$TARGETARCH" > /etc/phonix/board; \
    version=${PHONIX_VERSION:-$(python3 -c 'import phonix; print(phonix.__version__)')}; \
    printf 'PHONIX_VERSION="%s"\nPHONIX_BOARD="oci-%s"\nPHONIX_CONTAINER="1"\n' "$version" "$TARGETARCH" \
        > /usr/share/phonix/image-info; \
    rm -rf /var/spool/asterisk; ln -s /data/spool /var/spool/asterisk; \
    install -d -m 0700 /var/lib/phonix; \
    phonix --version

ENV PHONIX_DATA_DIR=/data \
    PHONIX_BOOT_DIR=/data/import \
    PHONIX_PRIVILEGED=doas \
    PHONIX_LIBEXEC_DIR=/usr/libexec/phonix \
    PHONIX_AMI_HOST=127.0.0.1 \
    PHONIX_AMI_PORT=5038

VOLUME /data
# web (80 redirects to 443), SIP udp/tcp, SIP TLS, IAX2, RTP
EXPOSE 80/tcp 443/tcp 5060/udp 5060/tcp 5061/tcp 4569/udp 10000-20000/udp
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD ["/usr/libexec/phonix/healthcheck"]
ENTRYPOINT ["/sbin/tini", "--", "/usr/libexec/phonix/entrypoint"]

LABEL org.opencontainers.image.title="PhonixPBX" \
      org.opencontainers.image.description="Asterisk 22 PBX with web interface (successor of AskoziaPBX)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/PhonixPBX/PhonixPBX"
