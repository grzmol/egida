"""Composition root: the only place that constructs adapters (ADR-0001).

Run: uvicorn control_layer.app:create_app --factory --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import anyio
import httpx
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from control_layer.adapters.audit_fanout import FanoutAuditSink
from control_layer.adapters.audit_jsonl import AuditJsonl
from control_layer.adapters.budget_memory import InMemoryBudgetStore
from control_layer.adapters.clock import SystemClock
from control_layer.adapters.http_api import Runtime, install_error_handlers, router
from control_layer.adapters.metrics_memory import MetricsMemory
from control_layer.adapters.ollama_client import OllamaClient
from control_layer.adapters.ollama_guard import OllamaGuardClient
from control_layer.adapters.policy_file import PolicyFile
from control_layer.core.errors import UpstreamError
from control_layer.core.models import Finding
from control_layer.core.pipeline import Pipeline
from control_layer.core.policy import Policy
from control_layer.core.ports import (
    Clock,
    Detector,
    DetectorDeps,
    GuardModelClient,
    ModelClient,
    ScanContext,
    SupportsWarmUp,
)
from control_layer.dashboard import build_router
from control_layer.detectors import REGISTRY

__all__ = ["Settings", "create_app"]

log = logging.getLogger(__name__)


class _AnyParams(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class _Unavailable:
    """Stand-in for a detector whose factory failed at startup (e.g. model files missing).

    The app still starts; a control using this kind fails on every scan, so its on_error applies
    (block by default) and the reason shows up as control_error. Restart after fixing.
    """

    kind: ClassVar[str] = "unavailable"
    Params: ClassVar[type[BaseModel]] = _AnyParams

    def __init__(self, kind: str, error: OSError) -> None:
        self._reason = f"detector {kind!r} unavailable: {error}"

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        raise RuntimeError(self._reason)


def _build_detectors(deps: DetectorDeps) -> dict[str, Detector]:
    detectors: dict[str, Detector] = {}
    for kind, factory in REGISTRY.items():
        try:
            detectors[kind] = factory(deps)
        except OSError as exc:  # missing model files etc.; other errors are bugs and propagate
            log.warning("detector %s unavailable: %s", kind, exc)
            detectors[kind] = _Unavailable(kind, exc)
    return detectors


@dataclass(frozen=True, slots=True)
class Settings:
    policy_path: Path
    audit_path: Path
    policy_poll_s: float = 1.0
    guard_url: str = "http://127.0.0.1:11434"  # Ollama native API for guard models (B6)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            policy_path=Path(os.environ.get("CONTROL_LAYER_POLICY", "config/policy.yaml")),
            audit_path=Path(os.environ.get("CONTROL_LAYER_AUDIT", "var/audit.jsonl")),
            guard_url=os.environ.get("CONTROL_LAYER_GUARD_URL", "http://127.0.0.1:11434"),
        )


WARM_UP_TIMEOUT_S = 60


async def _warm_up(detectors: dict[str, Detector], policy: Policy) -> None:
    """Load models of enabled controls before serving, so the first request is not a cold load
    that runs into the control's timeout. A failure only logs: in traffic the control's
    on_error applies (block by default)."""
    for control in policy.controls:
        detector = detectors.get(control.kind)
        if not control.enabled or not isinstance(detector, SupportsWarmUp):
            continue
        try:
            with anyio.fail_after(WARM_UP_TIMEOUT_S):
                await detector.warm_up(control.params)
        except (TimeoutError, UpstreamError) as exc:
            log.warning("warm-up %s failed: %s", control.id, exc)


def create_app(
    settings: Settings | None = None,
    *,
    model_client: ModelClient | None = None,
    guard_client: GuardModelClient | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the app. `model_client`/`guard_client`/`clock` replace Ollama and the system clock
    (offline tests, case runner)."""
    cfg = settings or Settings.from_env()
    metrics = MetricsMemory()  # per app; the dashboard router reads it, the audit fanout feeds it

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        clock_ = clock or SystemClock()
        async with httpx.AsyncClient() as http:
            guard = guard_client or OllamaGuardClient(http, cfg.guard_url)
            detectors = _build_detectors(DetectorDeps(guard=guard))
            param_models = {kind: d.Params for kind, d in detectors.items()}
            audit = FanoutAuditSink([AuditJsonl(cfg.audit_path), metrics])
            policy = PolicyFile(
                cfg.policy_path, param_models, audit, clock_, interval_s=cfg.policy_poll_s
            )
            pipeline = Pipeline(
                policy=policy,
                detectors=detectors,
                model=model_client or OllamaClient(http),
                budgets=InMemoryBudgetStore(),
                audit=audit,
                clock=clock_,
            )
            app.state.runtime = Runtime(
                pipeline=pipeline, policy=policy, registered_kinds=tuple(sorted(detectors))
            )
            await _warm_up(detectors, policy.current().policy)
            # startup errors (e.g. invalid policy) above propagate unwrapped; only the poller runs
            # inside the task group, which is cancelled on shutdown (no orphan task)
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(policy.run)
                yield
                tasks.cancel_scope.cancel()

    app = FastAPI(
        title="AI Control Layer",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router)
    app.include_router(build_router(metrics, cfg.audit_path))
    install_error_handlers(app)
    return app
