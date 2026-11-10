# The production image (#223): the app, its built shell and every in-tree agent, with locked
# dependencies and no toolchain. One image serves every service; the command picks which:
#
#   docker run … ghcr.io/data-director-agent/data-director                   # the app (default)
#   docker run … ghcr.io/data-director-agent/data-director dd-advisor-quality serve --host 0.0.0.0 --port 8102 --public-url …
#
# CI builds and publishes it (.github/workflows/images.yml); deploy/README.md, "Container images",
# says how to run it. The development images, which hold only toolchains, are in docker/Dockerfile.
#
# dd_app finds app/config and app/web/dist beside its own source, and the repository advisor builds
# its registry beside its package, so the workspace is installed editable in its source tree, as
# deploy/deploy.sh builds a release, and is copied whole into the final stage at the same path.
#
#   docker build -f docker/release.Dockerfile --build-arg REVISION="$(git rev-parse HEAD)" -t data-director .

# --- The shell ----------------------------------------------------------------------------------

FROM node:25-bookworm-slim@sha256:81db02c4b671288a03915da9534dbd54f96d0e7c24d80ccc54f5b36b2e684370 AS web
WORKDIR /src
# What the shell's build reads: the app's front end, the libraries it links and the app's config.
COPY sdk/browser sdk/browser
COPY inventory/browser inventory/browser
COPY app/config app/config
COPY app/web app/web
WORKDIR /src/app/web
RUN npm ci --no-audit --no-fund --loglevel=error && npm run build

# --- The workspace ------------------------------------------------------------------------------

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS build
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/data-director
COPY . .
# Every workspace member, from uv.lock, without the development tooling.
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
# Sources that agents build outside git, such as the repository advisor's re3data registry
# (dd-sources, sdk/src/dd_sdk/sources.py). What they are built from stays in the build cache.
RUN --mount=type=cache,target=/root/.cache/dd-sources \
    .venv/bin/dd-sources prepare --cache-dir /root/.cache/dd-sources

# --- The image ----------------------------------------------------------------------------------

# The Python the uv image is built on, so the virtual environment's interpreter is at the same path.
FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d

ARG REVISION=""
ARG VERSION=""
ARG PACKAGE_VERSIONS=""
LABEL org.opencontainers.image.title="Data Director" \
      org.opencontainers.image.description="The Data Director app and its agents (RDA Data Director Agentic AI Blueprint)" \
      org.opencontainers.image.source="https://github.com/data-director-agent/data-director" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.version="${VERSION}" \
      org.data-director.package-versions="${PACKAGE_VERSIONS}"

# Not root. Runs and projects are written under /runs and /projects, which take this owner when
# a named volume is first mounted on them.
RUN useradd --system --uid 10001 --user-group --home-dir /nonexistent --no-create-home dd \
    && mkdir /runs /projects \
    && chown dd:dd /runs /projects

COPY --from=build /opt/data-director /opt/data-director
COPY --from=web /src/app/web/dist /opt/data-director/app/web/dist
# The commit the app reports as its build (dd_app.about, GET /api/about).
RUN printf '%s\n' "${REVISION}" > /opt/data-director/REVISION

ENV PATH=/opt/data-director/.venv/bin:$PATH \
    DD_REVISION=${REVISION} \
    DD_APP_HOST=0.0.0.0 \
    DD_APP_PORT=7860 \
    DD_RUNS_DIR=/runs \
    DD_PROJECTS_DIR=/projects \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER dd
WORKDIR /opt/data-director
EXPOSE 7860
CMD ["data-director"]
