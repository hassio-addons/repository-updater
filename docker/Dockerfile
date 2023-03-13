FROM python:3.10-alpine3.17

# Setup base
RUN \
    apk add --no-cache \
        git \
    \
    && pip3 install \
        --no-cache-dir \
        --prefer-binary \
        --find-links "https://wheels.home-assistant.io/musllinux/" \
        repository-updater==1.2.3

# Entrypoint
ENTRYPOINT ["repository-updater"]

# Labels
LABEL \
    maintainer="Franck Nijhof <frenck@addons.community>" \
    org.opencontainers.image.title="Repository Updater" \
    org.opencontainers.image.description="Tool for automatically updating Home Assistant add-on repositories." \
    org.opencontainers.image.vendor="Home Assistant Community Add-ons" \
    org.opencontainers.image.authors="Franck Nijhof <frenck@addons.community>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://addons.community" \
    org.opencontainers.image.source="https://github.com/hassio-addons/repository-updater" \
    org.opencontainers.image.documentation="https://github.com/hassio-addons/repository-updater/blob/master/README.md"
