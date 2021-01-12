FROM python:3.9-alpine3.12

# Setup base
RUN \
    apk add --no-cache \
        git=2.26.2-r0 \
    \
    && pip3 install \
        repository-updater==0.5.1

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
