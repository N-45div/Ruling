FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Dependencies first, so code changes reuse this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY web ./web
# The precedent index is built from the archive by `ruling-desk precedents` before deploying.
COPY data/precedents ./data/precedents
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "ruling.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
