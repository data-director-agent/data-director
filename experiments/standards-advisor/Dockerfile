FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies first, so a source change does not re-resolve them.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN uv pip install --system --no-cache .

COPY config/ ./config/
COPY prompts/ ./prompts/
COPY schemas/ ./schemas/
COPY samples/ ./samples/

# Run records are written to a mount, not into the image.
VOLUME ["/app/runs"]

ENTRYPOINT ["standards-advisor"]
CMD ["--help"]
