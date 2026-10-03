"""Policy schema v1 (ADR-0003). Validation only; loading from files lives in adapters.

Every model forbids unknown fields: a typo in YAML rejects the policy instead of being ignored.
After `build_policy`, `ControlSpec.params` is an instance of the detector's `Params` model.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    ValidationInfo,
    model_validator,
)

from control_layer.core.errors import PolicyError
from control_layer.core.models import Action, Side

__all__ = [
    "AgentSpec",
    "BudgetLimits",
    "ControlSpec",
    "Defaults",
    "Limits",
    "ModelSpec",
    "OnError",
    "Policy",
    "UpstreamConfig",
    "build_policy",
]

OnError = Literal["block", "allow"]
_PARAM_MODELS = "param_models"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Defaults(_Strict):
    on_error: OnError = "block"
    timeout_ms: PositiveInt = 1500


class Limits(_Strict):
    max_input_chars: PositiveInt = 100_000
    max_messages: PositiveInt = 100
    max_tokens: PositiveInt = 1024


class UpstreamConfig(_Strict):
    base_url: str
    timeout_s: PositiveFloat = 60.0


class ModelSpec(_Strict):
    upstream: str
    price_in_per_1k: NonNegativeFloat = 0.0
    price_out_per_1k: NonNegativeFloat = 0.0


class AgentSpec(_Strict):
    key_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    allowed_models: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()  # () = no tools, ("*",) = any tool
    budget: str


class BudgetLimits(_Strict):
    max_tokens: PositiveInt
    max_cost: NonNegativeFloat
    max_requests: PositiveInt
    window_s: PositiveInt
    max_identical: PositiveInt
    identical_window_s: PositiveInt


class ControlSpec(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]*$")]
    kind: str
    enabled: bool = True
    sides: tuple[Side, ...] = Field(min_length=1)
    action: Action
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    on_error: OnError | None = None
    timeout_ms: PositiveInt | None = None
    params: BaseModel

    @model_validator(mode="before")
    @classmethod
    def _validate_params(cls, data: Any, info: ValidationInfo) -> Any:
        if not isinstance(data, Mapping):
            return data
        param_models = (info.context or {}).get(_PARAM_MODELS)
        if param_models is None:
            raise ValueError("policy must be built with build_policy() (param_models missing)")
        kind = data.get("kind")
        params_model = param_models.get(kind)
        if params_model is None:
            known = ", ".join(sorted(param_models)) or "none registered"
            raise ValueError(f"unknown control kind {kind!r} (known: {known})")
        raw_params = data.get("params", {})
        if isinstance(raw_params, BaseModel):
            return data
        return {**data, "params": params_model.model_validate(raw_params)}


class Policy(_Strict):
    version: PositiveInt
    defaults: Defaults = Defaults()
    limits: Limits = Limits()
    upstreams: dict[str, UpstreamConfig]
    models: dict[str, ModelSpec]
    agents: dict[str, AgentSpec]
    budgets: dict[str, BudgetLimits]
    controls: tuple[ControlSpec, ...] = ()

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        errors: list[str] = []
        seen: set[str] = set()
        for control in self.controls:
            if control.id in seen:
                errors.append(f"controls: duplicate id {control.id!r}")
            seen.add(control.id)
        for name, model in self.models.items():
            if model.upstream not in self.upstreams:
                errors.append(f"models.{name}.upstream: unknown upstream {model.upstream!r}")
        for name, agent in self.agents.items():
            if agent.budget not in self.budgets:
                errors.append(f"agents.{name}.budget: unknown budget {agent.budget!r}")
            for model_name in agent.allowed_models:
                if model_name not in self.models:
                    errors.append(f"agents.{name}.allowed_models: unknown model {model_name!r}")
        if errors:
            raise ValueError("; ".join(errors))
        return self


def build_policy(raw: Mapping[str, object], param_models: Mapping[str, type[BaseModel]]) -> Policy:
    """Validate raw policy data (e.g. from YAML). Raises PolicyError with readable messages."""
    if not isinstance(raw, Mapping):
        raise PolicyError([f"policy root must be a mapping, got {type(raw).__name__}"])
    try:
        return Policy.model_validate(raw, context={_PARAM_MODELS: dict(param_models)})
    except ValidationError as exc:
        raise PolicyError(
            [
                f"{'.'.join(str(part) for part in err['loc']) or '<root>'}: {err['msg']}"
                for err in exc.errors()
            ]
        ) from exc
