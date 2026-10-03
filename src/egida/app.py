"""Composition root: the only place that constructs adapters (ADR-0001).

Run: uvicorn egida.app:create_app --factory --host 127.0.0.1 --port 8080
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

from egida.adapters.anthropic_api import router as anthropic_router
from egida.adapters.audit_fanout import FanoutAuditSink
from egida.adapters.audit_jsonl import AuditJsonl
from egida.adapters.budget_memory import InMemoryBudgetStore
from egida.adapters.clock import SystemClock
from egida.adapters.feed_file import FeedFile
from egida.adapters.gemini_api import router as gemini_router
from egida.adapters.http_api import install_error_handlers, router
from egida.adapters.http_common import Runtime
from egida.adapters.metrics_memory import MetricsMemory
from egida.adapters.ollama_client import OllamaClient
from egida.adapters.ollama_guard import OllamaGuardClient
from egida.adapters.policy_file import PolicyFile
from egida.adapters.responses_api import router as responses_router
from egida.adapters.telemetry import TelemetrySink
from egida.adapters.tool_pins_memory import InMemoryToolPinStore
from egida.core.errors import UpstreamError
from egida.core.models import Finding
from egida.core.pipeline import Pipeline
from egida.core.policy import Policy
from egida.core.ports import (
    Clock,
    Detector,
    DetectorDeps,
    GuardModelClient,
    ModelClient,
    ScanContext,
    SupportsWarmUp,
)
from egida.core.signature_detector import SignatureDetector
from egida.core.signatures import SIGNATURE_KIND
from egida.dashboard import build_router
from egida.detectors import REGISTRY

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
    feed_path: Path = Path("signatures/feed.yaml")  # signature feed of known attacks (A5)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            policy_path=Path(os.environ.get("EGIDA_POLICY", "config/policy.yaml")),
            audit_path=Path(os.environ.get("EGIDA_AUDIT", "var/audit.jsonl")),
            guard_url=os.environ.get("EGIDA_GUARD_URL", "http://127.0.0.1:11434"),
            feed_path=Path(os.environ.get("EGIDA_FEED", "signatures/feed.yaml")),
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
            telemetry = TelemetrySink(clock_)
            audit = FanoutAuditSink([AuditJsonl(cfg.audit_path), metrics, telemetry])
            # the feed loads first: its detector must be in param_models before the policy loads
            feed = FeedFile.load_initial(cfg.feed_path, audit, clock_, interval_s=cfg.policy_poll_s)
            if SIGNATURE_KIND in detectors:
                raise RuntimeError(f"detector kind {SIGNATURE_KIND!r} is reserved for the feed")
            detectors[SIGNATURE_KIND] = SignatureDetector(feed)
            param_models = {kind: d.Params for kind, d in detectors.items()}
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
                tool_pins=InMemoryToolPinStore(),
                feed=feed,
            )
            app.state.runtime = Runtime(
                pipeline=pipeline,
                policy=policy,
                feed=feed,
                registered_kinds=tuple(sorted(detectors)),
                telemetry=telemetry,
                audit_path=cfg.audit_path,
            )
            await _warm_up(detectors, policy.current().policy)
            # startup errors (e.g. invalid policy) above propagate unwrapped; only the poller runs
            # inside the task group, which is cancelled on shutdown (no orphan task)
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(policy.run)
                tasks.start_soon(feed.run)
                yield
                tasks.cancel_scope.cancel()

    app = FastAPI(
        title="Egida",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router)
    app.include_router(anthropic_router)
    app.include_router(responses_router)
    app.include_router(gemini_router)
    app.include_router(build_router(metrics, cfg.audit_path))
    install_error_handlers(app)
    return app
