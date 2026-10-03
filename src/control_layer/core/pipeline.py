"""The control pipeline (ADR-0001, ADR-0004).

Fixed stage order: limits → access → budget → input controls → model → output controls →
budget settle → aggregate → audit. One policy snapshot per request. The strictest action wins;
REDACT without spans becomes BLOCK; a failing control applies its `on_error` (fail-closed default).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass

from control_layer.core.audit import AuditEvent, AuditEventType, FindingSummary
from control_layer.core.budget import estimate_tokens, fingerprint, input_chars, usage_cost
from control_layer.core.errors import UpstreamError
from control_layer.core.models import (
    Action,
    Category,
    ControlError,
    Decision,
    Finding,
    Interaction,
    Side,
    Span,
    Usage,
)
from control_layer.core.policy import ControlSpec, Policy
from control_layer.core.ports import (
    AuditSink,
    BudgetRequest,
    BudgetStore,
    Clock,
    Detector,
    ModelClient,
    PolicySnapshot,
    PolicySource,
    ScanContext,
)
from control_layer.core.texts import apply_redactions

__all__ = ["Pipeline", "PipelineResult"]


@dataclass(frozen=True, slots=True)
class PipelineResult:
    interaction: Interaction  # redacted; output is None when blocked before the model
    decision: Decision
    usage: Usage | None
    cost: float | None
    latency_ms: Mapping[str, float]
    policy: PolicySnapshot


@dataclass(slots=True)
class _Judged:
    finding: Finding
    action: Action


@dataclass(slots=True)
class _Run:
    """Mutable per-request state, private to Pipeline.run."""

    judged: list[_Judged] = dataclasses.field(default_factory=list)
    errors: list[ControlError] = dataclasses.field(default_factory=list)
    blocked_by: str | None = None
    latency_ms: dict[str, float] = dataclasses.field(default_factory=dict)

    def block(self, control_id: str) -> None:
        if self.blocked_by is None:
            self.blocked_by = control_id


class Pipeline:
    def __init__(
        self,
        policy: PolicySource,
        detectors: Mapping[str, Detector],
        model: ModelClient,
        budgets: BudgetStore,
        audit: AuditSink,
        clock: Clock,
    ) -> None:
        self._policy = policy
        self._detectors = detectors
        self._model = model
        self._budgets = budgets
        self._audit = audit
        self._clock = clock

    async def run(self, interaction: Interaction) -> PipelineResult:
        snapshot = self._policy.current()
        policy = snapshot.policy
        run = _Run()
        started = self._clock.monotonic()
        usage: Usage | None = None
        cost: float | None = None
        reservation: str | None = None
        settled = False

        try:
            interaction = await self._timed(run, "limits", self._limits(policy, interaction, run))
            if run.blocked_by is None:
                await self._timed(run, "access", self._access(policy, interaction, run))
            if run.blocked_by is None:
                reservation = await self._timed(
                    run, "budget", self._reserve(policy, interaction, run)
                )
            if run.blocked_by is None:
                interaction = await self._controls(policy, interaction, Side.INPUT, run)
            if run.blocked_by is None:
                model_spec = policy.models[interaction.model]
                upstream = policy.upstreams[model_spec.upstream]
                t0 = self._clock.monotonic()
                try:
                    result = await self._model.complete(interaction, upstream)
                except UpstreamError as exc:
                    await self._audit.emit(
                        self._event(snapshot, interaction, "upstream_error", detail=str(exc))
                    )
                    raise
                finally:
                    run.latency_ms["upstream"] = _ms(self._clock.monotonic() - t0)
                usage = result.usage
                cost = usage_cost(model_spec, usage)
                interaction = dataclasses.replace(interaction, output=result.message)
                interaction = await self._controls(policy, interaction, Side.OUTPUT, run)
                if reservation is not None:
                    await self._budgets.settle(reservation, usage, cost)
                    settled = True
        finally:
            if reservation is not None and not settled:
                await self._budgets.release(reservation)

        run.latency_ms["total"] = _ms(self._clock.monotonic() - started)
        decision = Decision(
            action=max((j.action for j in run.judged), default=Action.ALLOW, key=_severity)
            if run.blocked_by is None
            else Action.BLOCK,
            findings=tuple(j.finding for j in run.judged),
            blocked_by=run.blocked_by,
            errors=tuple(run.errors),
        )
        await self._audit.emit(
            dataclasses.replace(
                self._event(snapshot, interaction, "decision"),
                decision=decision.action,
                blocked_by=decision.blocked_by,
                findings=tuple(
                    FindingSummary(
                        control_id=j.finding.control_id,
                        category=j.finding.category,
                        score=j.finding.score,
                        action=j.action,
                        tags=j.finding.tags,
                        evidence=j.finding.evidence,
                    )
                    for j in run.judged
                ),
                usage=usage,
                cost=cost,
                budget=self._budgets.usage(interaction.agent_id),
                latency_ms=dict(run.latency_ms),
            )
        )
        return PipelineResult(
            interaction=interaction,
            decision=decision,
            usage=usage,
            cost=cost,
            latency_ms=dict(run.latency_ms),
            policy=snapshot,
        )

    # --- stages -----------------------------------------------------------------------

    async def _limits(self, policy: Policy, interaction: Interaction, run: _Run) -> Interaction:
        limits = policy.limits
        chars = input_chars(interaction)
        if chars > limits.max_input_chars or len(interaction.messages) > limits.max_messages:
            self._fixed_block(
                run,
                "limit",
                Category.LIMIT,
                f"input {chars} chars / {len(interaction.messages)} messages exceeds "
                f"{limits.max_input_chars} / {limits.max_messages}",
            )
            return interaction
        requested = interaction.max_tokens or limits.max_tokens
        return dataclasses.replace(interaction, max_tokens=min(requested, limits.max_tokens))

    async def _access(self, policy: Policy, interaction: Interaction, run: _Run) -> None:
        agent = policy.agents.get(interaction.agent_id)
        if agent is None:
            self._fixed_block(run, "access.agent", Category.ACCESS, "agent not in policy")
        elif interaction.model not in agent.allowed_models:
            self._fixed_block(
                run, "access.model", Category.ACCESS, f"model {interaction.model!r} not allowed"
            )

    async def _reserve(self, policy: Policy, interaction: Interaction, run: _Run) -> str | None:
        agent = policy.agents[interaction.agent_id]
        model_spec = policy.models[interaction.model]
        max_tokens = interaction.max_tokens or policy.limits.max_tokens
        est_tokens = estimate_tokens(interaction, max_tokens)
        verdict = await self._budgets.reserve(
            BudgetRequest(
                agent_id=interaction.agent_id,
                budget_name=agent.budget,
                limits=policy.budgets[agent.budget],
                est_tokens=est_tokens,
                est_cost=usage_cost(model_spec, Usage(est_tokens - max_tokens, max_tokens)),
                fingerprint=fingerprint(interaction),
                now=self._clock.monotonic(),
            )
        )
        if not verdict.allowed:
            used = verdict.usage
            self._fixed_block(
                run,
                f"budget.{verdict.reason}",
                Category.BUDGET,
                f"{verdict.reason}: tokens {used.tokens}/{used.max_tokens}, cost "
                f"{used.cost:.4f}/{used.max_cost}, requests {used.requests}/{used.max_requests}",
            )
            return None
        return verdict.reservation_id

    async def _controls(
        self, policy: Policy, interaction: Interaction, side: Side, run: _Run
    ) -> Interaction:
        redact_spans: list[Span] = []
        for control in policy.controls:
            if not control.enabled or side not in control.sides:
                continue
            t0 = self._clock.monotonic()
            judged = await self._run_control(policy, control, interaction, side, run)
            run.latency_ms[f"{side.value}:{control.id}"] = _ms(self._clock.monotonic() - t0)
            for item in judged:
                run.judged.append(item)
                if item.action is Action.BLOCK:
                    run.block(control.id)
                elif item.action is Action.REDACT:
                    if not item.finding.spans:
                        run.block(control.id)  # cannot redact what we cannot locate: fail closed
                    redact_spans.extend(item.finding.spans)
            if run.blocked_by is not None:
                return interaction
        if not redact_spans:
            return interaction
        t0 = self._clock.monotonic()
        redacted = apply_redactions(interaction, redact_spans)
        run.latency_ms[f"redact_{side.value}"] = _ms(self._clock.monotonic() - t0)
        return redacted

    async def _run_control(
        self,
        policy: Policy,
        control: ControlSpec,
        interaction: Interaction,
        side: Side,
        run: _Run,
    ) -> list[_Judged]:
        timeout_ms = control.timeout_ms or policy.defaults.timeout_ms
        on_error = control.on_error or policy.defaults.on_error
        error: ControlError | None = None
        findings: list[Finding] = []
        detector = self._detectors.get(control.kind)
        try:
            if detector is None:
                raise LookupError(f"no detector registered for kind {control.kind!r}")
            ctx = ScanContext(interaction, side, control.id, control.params)
            findings = await asyncio.wait_for(detector.scan(ctx), timeout_ms / 1000)
            for finding in findings:
                if finding.control_id != control.id:
                    raise ValueError(f"finding reports control_id {finding.control_id!r}")
                if finding.spans:
                    apply_redactions(interaction, finding.spans)  # validates targets and ranges
        except TimeoutError:
            error = ControlError(control.id, "timeout", f"no result within {timeout_ms} ms")
        except Exception as exc:  # noqa: BLE001 — detector boundary (ADR-0004): never fail open
            error = ControlError(control.id, "exception", f"{type(exc).__name__}: {exc}")

        if error is not None:
            run.errors.append(error)
            await self._audit.emit(
                AuditEvent(
                    type="control_error",
                    ts=self._clock.now(),
                    request_id=interaction.request_id,
                    agent_id=interaction.agent_id,
                    model=interaction.model,
                    detail=f"{control.id} ({side.value}): {error.kind}: {error.message}; "
                    f"on_error={on_error}",
                )
            )
            if on_error == "block":
                run.block(control.id)
            return []

        return [
            _Judged(f, control.action if f.score >= control.threshold else Action.ALLOW)
            for f in findings
        ]

    # --- helpers ----------------------------------------------------------------------

    @staticmethod
    def _fixed_block(run: _Run, control_id: str, category: Category, evidence: str) -> None:
        run.judged.append(
            _Judged(Finding(control_id, category, 1.0, evidence=evidence[:200]), Action.BLOCK)
        )
        run.block(control_id)

    async def _timed[T](self, run: _Run, stage: str, coro: Awaitable[T]) -> T:
        t0 = self._clock.monotonic()
        try:
            return await coro
        finally:
            run.latency_ms[stage] = _ms(self._clock.monotonic() - t0)

    def _event(
        self,
        snapshot: PolicySnapshot,
        interaction: Interaction,
        kind: AuditEventType,
        detail: str | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            type=kind,
            ts=self._clock.now(),
            request_id=interaction.request_id,
            agent_id=interaction.agent_id,
            model=interaction.model,
            policy_version=snapshot.policy.version,
            policy_sha256=snapshot.sha256,
            detail=detail,
        )


def _severity(action: Action) -> int:
    return action.severity


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 3)
