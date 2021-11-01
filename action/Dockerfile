FROM python:3.10-alpine3.14

# Setup base
RUN \
    apk add --no-cache \
        bash \
        git \
    \
    && pip3 install \
        --no-cache-dir \
        --prefer-binary \
        --find-links "https://wheels.home-assistant.io/alpine-3.14/${BUILD_ARCH}/" \
        repository-updater==1.2.0

COPY entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
