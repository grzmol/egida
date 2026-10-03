# syntax=docker/dockerfile:1
# AI Control Layer image. Owner: Maciej (Dev D). Spec: docs/tasks/grzegorz/A7-compose-i-audyt-dlugu.md §2.
# Pattern from the uv Docker guide: dependency layer separate from the project layer.

# Both stages must use the same image: .venv symlinks to the base image's interpreter.
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
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
# The venv and config belong to root: appuser cannot change code or policy.
COPY --from=build /app/.venv /app/.venv
COPY config /app/config
# /app/var is the only writable directory (audit log).
RUN mkdir -p /app/var && chown appuser:appuser /app/var
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    CONTROL_LAYER_POLICY=/app/config/policy.yaml \
    CONTROL_LAYER_AUDIT=/app/var/audit.jsonl
USER appuser
EXPOSE 8080
# 0.0.0.0 only inside the container, otherwise the published port is unreachable.
# Exec form so SIGTERM reaches uvicorn and the lifespan closes its resources.
CMD ["uvicorn", "control_layer.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
