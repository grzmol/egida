"""Composition root: the only place that constructs adapters (ADR-0001).

Run: uvicorn control_layer.app:create_app --factory --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI

from control_layer.adapters.audit_fanout import FanoutAuditSink
from control_layer.adapters.audit_jsonl import AuditJsonl
from control_layer.adapters.budget_passthrough import PassthroughBudgetStore
from control_layer.adapters.clock import SystemClock
from control_layer.adapters.http_api import Runtime, install_error_handlers, router
from control_layer.adapters.ollama_client import OllamaClient
from control_layer.adapters.policy_static import StaticPolicySource, load_policy_file
from control_layer.core.pipeline import Pipeline
from control_layer.core.ports import Clock, DetectorDeps, ModelClient
from control_layer.detectors import REGISTRY

__all__ = ["Settings", "create_app"]


@dataclass(frozen=True, slots=True)
class Settings:
    policy_path: Path
    audit_path: Path

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            policy_path=Path(os.environ.get("CONTROL_LAYER_POLICY", "config/policy.yaml")),
            audit_path=Path(os.environ.get("CONTROL_LAYER_AUDIT", "var/audit.jsonl")),
        )


def create_app(
    settings: Settings | None = None,
    *,
    model_client: ModelClient | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the app. `model_client`/`clock` replace Ollama/system clock (offline tests, runner)."""
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        clock_ = clock or SystemClock()
        async with httpx.AsyncClient() as http:
            deps = DetectorDeps()
            detectors = {kind: factory(deps) for kind, factory in REGISTRY.items()}
            param_models = {kind: d.Params for kind, d in detectors.items()}
            policy = StaticPolicySource(
                load_policy_file(cfg.policy_path, param_models, clock_.now())
            )
            audit = FanoutAuditSink([AuditJsonl(cfg.audit_path)])
            pipeline = Pipeline(
                policy=policy,
                detectors=detectors,
                model=model_client or OllamaClient(http),
                budgets=PassthroughBudgetStore(),
                audit=audit,
                clock=clock_,
            )
            app.state.runtime = Runtime(pipeline=pipeline, policy=policy)
            yield

    app = FastAPI(
        title="AI Control Layer",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router)
    install_error_handlers(app)
    return app
