# Development images for compose.yaml. They hold only the toolchains: the source is bind-mounted
# and dependencies are installed at start-up into named volumes, so edits show up without a rebuild.
# Both run as uid 1000, so files written into the bind mount belong to the usual first host user.
# The production image, which holds the source and its dependencies, is docker/release.Dockerfile.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS python
# The run and project stores are named volumes, which take their owner from these directories when
# Compose creates them; without them they would belong to root and the app could not write.
RUN useradd --create-home --uid 1000 dev \
    && mkdir /venv /uv-cache /workspace /runs /projects \
    && chown dev:dev /venv /uv-cache /workspace /runs /projects
USER dev
WORKDIR /workspace
# The virtual environment lives outside the bind mount, so it never mixes with a host .venv.
ENV UV_PROJECT_ENVIRONMENT=/venv \
    UV_CACHE_DIR=/uv-cache \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

FROM node:25-bookworm-slim@sha256:81db02c4b671288a03915da9534dbd54f96d0e7c24d80ccc54f5b36b2e684370 AS node
# Pre-create the mount point so the node_modules volume is owned by the node user (uid 1000).
RUN mkdir -p /workspace/app/web/node_modules && chown -R node:node /workspace
USER node
WORKDIR /workspace/app/web
