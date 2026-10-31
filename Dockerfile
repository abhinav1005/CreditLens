# FastAPI assistant (+ labeling/promote routes for the web UI).
#   docker compose up        (see docker-compose.yml)
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH"

# Dependencies first, so code edits don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY evals ./evals
COPY data ./data
COPY prompts ./prompts
COPY policy ./policy
COPY config ./config
COPY contracts ./contracts
COPY config.yaml ./
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["uvicorn", "assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]
