"""Schema introspection for Egida: which fields a policy section or detector has, how to edit them.

Everything is read from the Pydantic models the proxy itself validates with (`core/policy.py`,
detector `Params`), so a field added there shows up in Egida without changes here; only the
one-line help of the core policy fields is written by hand (`HELP`, a test keeps it complete).
"""

from __future__ import annotations

import types
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Union, get_args, get_origin

import annotated_types
import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

import egida.detectors as detectors_module
from egida.core.policy import (
    AgentSpec,
    BudgetLimits,
    ControlSpec,
    Defaults,
    Limits,
    ModelSpec,
    UpstreamConfig,
)
from egida.core.signatures import SIGNATURE_KIND, FeedDocument, SignatureParams
from egida.detectors import REGISTRY

__all__ = [
    "HELP",
    "SECTION_MODELS",
    "FieldKind",
    "FieldSpec",
    "check",
    "detector_params",
    "feed_rules",
    "fields",
    "help_for",
    "parse_input",
]

FieldKind = Literal["bool", "choice", "int", "float", "text", "multi", "list", "map", "raw"]


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    kind: FieldKind
    model: type[BaseModel]
    choices: tuple[str, ...] = ()  # choice/multi: allowed values; list: the default (known values)
    optional: bool = False  # annotation allows None (ControlSpec.on_error/timeout_ms: inherit)
    required: bool = False
    default: Any = None  # plain python (lists, enum values); None when required


def detector_params() -> dict[str, type[BaseModel]]:
    """Control kind → its `Params` model, for every registered detector and `signature`.

    Read from the detector classes the registry module imports: the factories are never called
    (building `prompt_guard` loads an ONNX model). RuntimeError if a kind has no class.
    """
    found: dict[str, type[BaseModel]] = {}
    for value in vars(detectors_module).values():
        if not isinstance(value, type):
            continue
        kind = getattr(value, "kind", None)
        params = getattr(value, "Params", None)
        if isinstance(kind, str) and isinstance(params, type) and issubclass(params, BaseModel):
            found[kind] = params
    missing = sorted(set(REGISTRY) - set(found))
    if missing:
        raise RuntimeError(
            f"no detector class with kind/Params ClassVars for: {', '.join(missing)}"
        )
    result = {kind: found[kind] for kind in REGISTRY}
    result[SIGNATURE_KIND] = SignatureParams
    return result


# --- classification ---------------------------------------------------------------------


def _strip_annotated(tp: Any) -> Any:
    while get_origin(tp) is Annotated:
        tp = get_args(tp)[0]
    return tp


def _split_optional(tp: Any) -> tuple[Any, bool]:
    tp = _strip_annotated(tp)
    if get_origin(tp) in (Union, types.UnionType):
        args = get_args(tp)
        rest = [a for a in args if a is not type(None)]
        if len(rest) == 1 and len(rest) < len(args):
            return _strip_annotated(rest[0]), True
    return tp, False


def _choices_of(tp: Any) -> tuple[str, ...] | None:
    """Values of a Literal of strings or a StrEnum; None for anything else."""
    tp = _strip_annotated(tp)
    if get_origin(tp) is Literal:
        values = get_args(tp)
        if all(isinstance(v, str) for v in values):
            return tuple(values)
        return None
    if isinstance(tp, type) and issubclass(tp, Enum) and issubclass(tp, str):
        return tuple(member.value for member in tp)
    return None


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    if isinstance(value, Mapping):
        return {_plain(k): _plain(v) for k, v in value.items()}
    return value


def _default(info: FieldInfo) -> Any:
    if info.is_required():
        return None
    if info.default is not PydanticUndefined:
        return _plain(info.default)
    return _plain(info.get_default(call_default_factory=True))


def _classify(info: FieldInfo) -> tuple[FieldKind, tuple[str, ...], bool]:
    tp, optional = _split_optional(info.annotation)
    choices = _choices_of(tp)
    if choices is not None:
        return "choice", choices, optional
    if tp is bool:
        return "bool", (), optional
    simple: dict[Any, FieldKind] = {int: "int", float: "float", str: "text"}
    if tp in simple:
        return simple[tp], (), optional
    origin, args = get_origin(tp), get_args(tp)
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        item = _strip_annotated(args[0])
        item_choices = _choices_of(item)
        if item_choices is not None:
            return "multi", item_choices, optional
        if item is str:
            default = info.default
            known = default if isinstance(default, tuple) and default else ()
            return "list", tuple(str(v) for v in known), optional
    if origin is dict and tuple(_strip_annotated(a) for a in args) == (str, str):
        return "map", (), optional
    return "raw", (), optional


def fields(model: type[BaseModel], *, skip: Collection[str] = ()) -> list[FieldSpec]:
    """Editable description of every field of `model` (declaration order), minus `skip`."""
    specs: list[FieldSpec] = []
    for name, info in model.model_fields.items():
        if name in skip:
            continue
        kind, choices, optional = _classify(info)
        specs.append(
            FieldSpec(
                name=name,
                kind=kind,
                model=model,
                choices=choices,
                optional=optional,
                required=info.is_required(),
                default=_default(info),
            )
        )
    return specs


# --- validation ---------------------------------------------------------------------------


@cache
def _adapter(model: type[BaseModel], name: str) -> TypeAdapter[Any]:
    info = model.model_fields[name]
    annotation: Any = info.annotation
    if annotation is BaseModel:
        # ControlSpec.params: the concrete Params model depends on `kind`; here only its shape
        annotation = dict[str, Any]
    if info.metadata:
        return TypeAdapter(Annotated[annotation, *info.metadata])
    return TypeAdapter(annotation)


def _alone(model: type[BaseModel], name: str) -> bool:
    """The model can be built from this one field: every other field has a default."""
    others = (info for other, info in model.model_fields.items() if other != name)
    return all(not info.is_required() for info in others)


def _message(exc: ValidationError, strip: int = 0) -> str:
    error = exc.errors()[0]
    msg = str(error["msg"]).removeprefix("Value error, ")
    loc = ".".join(str(part) for part in error["loc"][strip:])
    return f"{loc}: {msg}" if loc else msg


def check(spec: FieldSpec, value: Any) -> Any:
    """Validate one value of `spec`'s field; the normalized plain value or ValueError(readable).

    Applies the field's type and constraints and, when the model can be built from that field
    alone, the model's own validators too (e.g. regexes that must compile). A field typed as
    bare `BaseModel` (ControlSpec.params) only has to be a mapping: validate its keys with
    `fields(detector_params()[kind])`.
    """
    try:
        validated = _adapter(spec.model, spec.name).validate_python(value)
    except ValidationError as exc:
        raise ValueError(_message(exc)) from exc
    if _alone(spec.model, spec.name):
        try:
            built = spec.model.model_validate({spec.name: value})
        except ValidationError as exc:
            raise ValueError(_message(exc, strip=1)) from exc
        validated = getattr(built, spec.name)
    return _plain(validated)


def parse_input(spec: FieldSpec, text: str) -> Any:
    """One input line → value of `spec`, then `check`. ValueError(readable) on bad input.

    An empty line means None for optional fields (inherit the default); raw and collection
    fields take a YAML value (`[a, b]`, `{k: v}`, `42`).
    """
    stripped = text.strip()
    if not stripped and spec.optional:
        return check(spec, None)
    value: Any
    if spec.kind == "int":
        try:
            value = int(stripped)
        except ValueError as exc:
            raise ValueError("Enter a whole number") from exc
    elif spec.kind == "float":
        try:
            value = float(stripped)
        except ValueError as exc:
            raise ValueError("Enter a number") from exc
    elif spec.kind in ("text", "choice"):
        if not stripped and spec.required:
            raise ValueError("Enter a value, it is required")
        value = stripped
    else:
        try:
            value = yaml.safe_load(stripped)
        except yaml.YAMLError as exc:
            raise ValueError("Enter a valid YAML value, e.g. 42, text, [a, b] or {k: v}") from exc
    return check(spec, value)


# --- help -----------------------------------------------------------------------------------

SECTION_MODELS: Final[Mapping[str, type[BaseModel]]] = types.MappingProxyType(
    {
        "defaults": Defaults,
        "limits": Limits,
        "upstreams": UpstreamConfig,
        "models": ModelSpec,
        "agents": AgentSpec,
        "budgets": BudgetLimits,
        "controls": ControlSpec,
    }
)

HELP: Final[Mapping[str, str]] = types.MappingProxyType(
    {
        "policy.version": "Policy version reported by /healthz, the policy API and every audit "
        "record; raise it on each change.",
        "defaults.on_error": "What a control does when it fails or times out: block (fail-closed) "
        "or allow.",
        "defaults.timeout_ms": "Milliseconds a control may run before it counts as failed and "
        "on_error applies.",
        "limits.max_input_chars": "Most characters of input text per request; a longer request "
        "is blocked.",
        "limits.max_messages": "Most messages per request; a request with more is blocked.",
        "limits.max_tokens": "Cap on completion tokens: a larger requested max_tokens is clamped, "
        "and it is used when none is requested.",
        "upstreams.base_url": "OpenAI-compatible base URL of the model server; requests go to "
        "<base_url>/chat/completions.",
        "upstreams.timeout_s": "Seconds to wait for the upstream's answer before the request "
        "fails.",
        "models.upstream": "Upstream (from upstreams) that serves this model.",
        "models.price_in_per_1k": "Cost of 1000 prompt tokens, counted against budgets' max_cost.",
        "models.price_out_per_1k": "Cost of 1000 completion tokens, counted against budgets' "
        "max_cost.",
        "agents.key_sha256": "SHA-256 of the agent's API key (64 lowercase hex); the key itself "
        "is never stored.",
        "agents.allowed_models": "Models (from models) this agent may call.",
        "agents.allowed_tools": "Tools the agent may declare or call: empty = no tools, * = any "
        "tool.",
        "agents.budget": "Budget (from budgets) whose limits apply; usage is counted per agent.",
        "budgets.max_tokens": "Most tokens (prompt + completion) an agent may use per window_s.",
        "budgets.max_cost": "Most cost (model prices × tokens) an agent may spend per window_s.",
        "budgets.max_requests": "Most requests an agent may send per window_s.",
        "budgets.window_s": "Length in seconds of the sliding window for max_tokens, max_cost "
        "and max_requests.",
        "budgets.max_identical": "Identical requests allowed within identical_window_s before "
        "the agent is blocked as a loop.",
        "budgets.identical_window_s": "Seconds during which identical requests count toward "
        "max_identical.",
        "controls.id": "Unique control name shown in audit records and blocked_by: lowercase "
        "letters, digits, _ . -.",
        "controls.kind": "Detector this control runs; it decides which params are available.",
        "controls.enabled": "Off keeps the control in the policy but skips it.",
        "controls.sides": "What it scans: input (the request) and/or output (the model's answer).",
        "controls.action": "What a finding at or above threshold does: allow (audit only), "
        "redact the match, or block.",
        "controls.threshold": "Lowest finding score (0-1) that triggers the action; lower scores "
        "are only audited.",
        "controls.on_error": "This control's on_error; empty = inherit defaults.on_error.",
        "controls.timeout_ms": "This control's timeout in ms; empty = inherit defaults.timeout_ms.",
        "controls.params": "Detector-specific settings for this control's kind.",
    }
)

_KIND_LABELS: Final[Mapping[str, str]] = {
    "bool": "on/off",
    "choice": "choice",
    "int": "whole number",
    "float": "number",
    "text": "text",
    "multi": "multi-choice",
    "list": "list",
    "map": "map label → value",
    "raw": "YAML value",
}

_BOUNDS: Final = (
    (annotated_types.Ge, "ge", "≥"),
    (annotated_types.Gt, "gt", ">"),
    (annotated_types.Le, "le", "≤"),
    (annotated_types.Lt, "lt", "<"),
)


def _show(value: Any) -> str:
    if value is None or value == [] or value == {}:
        return "none"
    if isinstance(value, bool):
        return "on" if value else "off"
    if value == "":
        return "empty"
    if isinstance(value, list):
        return ", ".join(_show(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_show(v)}" for k, v in value.items())
    return str(value)


def _bounds(spec: FieldSpec) -> str:
    parts: list[str] = []
    for item in spec.model.model_fields[spec.name].metadata:
        for bound_type, attr, sign in _BOUNDS:
            if isinstance(item, bound_type):
                parts.append(f"{sign} {getattr(item, attr)}")
    return " ".join(parts)


def help_for(section: str, spec: FieldSpec) -> str:
    """`HELP["<section>.<field>"]`, else generated, e.g. "whole number ≥ 8 · default: 32"."""
    known = HELP.get(f"{section}.{spec.name}")
    if known is not None:
        return known
    label = _KIND_LABELS[spec.kind]
    bounds = _bounds(spec)
    head = f"{label} {bounds}" if bounds else label
    if spec.optional:
        head += " or empty"
    tail = "required" if spec.required else f"default: {_show(spec.default)}"
    return f"{head} · {tail}"


# --- signature feed -------------------------------------------------------------------------


def feed_rules(path: Path) -> list[tuple[str, str]]:
    """(rule id, title) of every rule of the signature feed at `path`, in file order.

    [] when the file cannot be read or is not a valid feed (the screens then offer free text).
    """
    try:
        document = FeedDocument.model_validate(yaml.safe_load(path.read_bytes()))
    except (OSError, yaml.YAMLError, ValidationError):
        return []
    return [(rule.id, rule.title) for rule in document.rules]
