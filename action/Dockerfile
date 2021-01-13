FROM python:3.9-alpine

RUN \
    apk add --no-cache \
        bash \
        git \
    \
    && pip3 install \
        repository-updater==1.0.0

COPY entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
