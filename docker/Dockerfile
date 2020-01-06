FROM python:3.8-alpine3.11

# Setup base
RUN \
    apk add --no-cache \
        git=2.24.1-r0 \
    \
    && pip3 install \
        repository-updater==0.3.0

# Entrypoint
ENTRYPOINT ["repository-updater"]

# Labels
LABEL \
    maintainer="Franck Nijhof <frenck@addons.community>" \
    org.label-schema.description="Community Hass.io Add-ons Repository Updater" \
    org.label-schema.name="Repository Updater" \
    org.label-schema.schema-version="1.0" \
    org.label-schema.url="https://github.com/hassio-addons/repository-updater" \
    org.label-schema.usage="https://github.com/hassio-addons/repository-updater/tree/master/README.md" \
    org.label-schema.vcs-url="https://github.com/hassio-addons/repository-updater" \
    org.label-schema.vendor="Community Hass.io Add-ons"
