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
# The browser scanner's bundle (inventory/browser/README.md, Browser bundle) is built in a stage of
# its own and copied into the shell's dist, where the app serves it at /inventory-bundle/.
#
#   docker build -f docker/release.Dockerfile --build-arg REVISION="$(git rev-parse HEAD)" -t data-director .

# --- The shell ----------------------------------------------------------------------------------

FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS web
WORKDIR /src
# What the shell's build reads: the app's front end, the libraries it links and the app's config.
COPY sdk/browser sdk/browser
COPY inventory/browser inventory/browser
COPY app/config app/config
COPY app/web app/web
WORKDIR /src/app/web
RUN npm ci --no-audit --no-fund --loglevel=error && npm run build

# --- The browser scanner's bundle ---------------------------------------------------------------

# Pyodide, the command's wheel built from this commit, and its dependencies. The build needs uv,
# Python 3.14 and the whole workspace (uv build and uv export read it), so it runs on the uv image
# with Node taken from the shell's stage, and fetches the wheels from the network, each checked
# against the SHA-256 its lock gives. The wheels are kept in the build cache between builds.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS bundle
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
WORKDIR /src
COPY . .
WORKDIR /src/inventory/browser
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/src/inventory/browser/.cache/wheels \
    npm ci --no-audit --no-fund --loglevel=error && npm run bundle

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
FROM python:3.14.10-slim-bookworm@sha256:3fe1a0b6c2d6b2ebb572906cdabeca75aeb558c0c17db5ffefbcf8094871c32b

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
COPY --from=bundle /src/inventory/browser/dist/inventory-bundle /opt/data-director/app/web/dist/inventory-bundle
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
