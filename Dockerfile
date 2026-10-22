# The image installs the wheel built from this same commit, not a release
# from PyPI, so the image and the package can never drift apart. Build the
# wheel first, then the image:
#
#   uv build --wheel
#   docker build .
#
# The dependencies are installed from uv.lock with their hashes checked.

FROM ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 AS uv

FROM python:3.14-alpine3.23@sha256:e7cff362a12454395f8dc99607c21a602ea880cdce03538877b90c2ba932b16f

ENV \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_SYSTEM_PYTHON=1

RUN \
    --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=/build/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/build/uv.lock \
    --mount=type=bind,source=dist,target=/build/dist \
    uv export \
        --project /build \
        --frozen \
        --no-dev \
        --no-emit-project \
        --output-file /tmp/requirements.txt \
    && uv pip install --require-hashes --requirements /tmp/requirements.txt \
    && uv pip install --no-deps /build/dist/repository_updater-*.whl \
    && rm /tmp/requirements.txt

# No USER: GitHub requires Docker actions to run as the default root user,
# and this image is the action.
ENTRYPOINT ["repository-updater"]

ARG BUILD_VERSION=dev
LABEL \
    maintainer="Franck Nijhof <opensource@frenck.dev>" \
    org.opencontainers.image.title="Repository Updater" \
    org.opencontainers.image.description="Tool for automatically updating Home Assistant app repositories." \
    org.opencontainers.image.vendor="Home Assistant Community Apps" \
    org.opencontainers.image.authors="Franck Nijhof <opensource@frenck.dev>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/hassio-addons/repository-updater" \
    org.opencontainers.image.source="https://github.com/hassio-addons/repository-updater" \
    org.opencontainers.image.documentation="https://github.com/hassio-addons/repository-updater/blob/main/README.md" \
    org.opencontainers.image.version=${BUILD_VERSION}
