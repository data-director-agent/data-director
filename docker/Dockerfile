# Development images for compose.yaml. They hold only the toolchains: the source is bind-mounted
# and dependencies are installed at start-up into named volumes, so edits show up without a rebuild.
# Both run as uid 1000, so files written into the bind mount belong to the usual first host user.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS python
RUN useradd --create-home --uid 1000 dev \
    && mkdir /venv /uv-cache /workspace \
    && chown dev:dev /venv /uv-cache /workspace
USER dev
WORKDIR /workspace
# The virtual environment lives outside the bind mount, so it never mixes with a host .venv.
ENV UV_PROJECT_ENVIRONMENT=/venv \
    UV_CACHE_DIR=/uv-cache \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS node
# Pre-create the mount point so the node_modules volume is owned by the node user (uid 1000).
RUN mkdir -p /workspace/app/web/node_modules && chown -R node:node /workspace
USER node
WORKDIR /workspace/app/web
