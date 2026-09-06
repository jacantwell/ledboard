# glibc 2.41 satisfies the manylinux_2_28 piomatter wheel; CPython 3.13 matches its cp313 tag.
FROM python:3.13-slim-trixie AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/London \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
# hw extra only resolves on aarch64; on amd64 dev builds it is skipped by its marker.
RUN uv sync --frozen --no-dev --no-install-project --extra hw

COPY ledboard/ ./ledboard/
RUN uv sync --frozen --no-dev --extra hw

RUN useradd -u 1000 -m app && mkdir -p /data && chown app:app /data
USER app
ENV PATH="/opt/venv/bin:$PATH" \
    LEDBOARD_DISPLAY=hw \
    LEDBOARD_HOST=0.0.0.0 \
    LEDBOARD_PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-m", "ledboard.healthcheck"]

ENTRYPOINT ["tini", "--"]
CMD ["ledboard", "daemon"]
