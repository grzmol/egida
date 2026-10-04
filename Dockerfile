# syntax=docker/dockerfile:1
# Egida image. Owner: Maciej (Dev D). Spec: docs/tasks/grzegorz/A7-compose-i-audyt-dlugu.md §2.
# Pattern from the uv Docker guide: dependency layer separate from the project layer.

# Both stages must use the same image: .venv symlinks to the base image's interpreter.
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --no-editable
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS final
ARG UID=10001
RUN adduser --disabled-password --gecos "" --home "/nonexistent" \
    --shell "/sbin/nologin" --no-create-home --uid "${UID}" appuser
WORKDIR /app
# The venv, config and signature feed belong to root: appuser cannot change code, policy or rules.
COPY --from=build /app/.venv /app/.venv
COPY config /app/config
COPY signatures /app/signatures
# /app/var is the only writable directory (audit log).
RUN mkdir -p /app/var && chown appuser:appuser /app/var
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    EGIDA_POLICY=/app/config/policy.yaml \
    EGIDA_FEED=/app/signatures/feed.yaml \
    EGIDA_AUDIT=/app/var/audit.jsonl
USER appuser
EXPOSE 8080
# 0.0.0.0 only inside the container, otherwise the published port is unreachable.
# Exec form so SIGTERM reaches uvicorn and the lifespan closes its resources.
CMD ["uvicorn", "egida.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
