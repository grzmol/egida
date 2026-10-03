"""Tool controls on OpenAI tools/tool_calls traffic (A6): C03 allowlist, C09 definition pinning.

Pure functions; the pipeline runs them as fixed stages (like access.model), because they need the
agent's policy. Tool descriptions are attacker-controlled text and never go into evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from control_layer.core.models import Category, Finding, Interaction, ToolDef

__all__ = [
    "C03_TAGS",
    "C09_TAGS",
    "TOOL_NAME_RE",
    "check_duplicate_tools",
    "check_tools_input",
    "check_tools_output",
    "pin_findings",
    "tool_allowed",
    "tool_digest",
]

TOOL_NAME_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
C03_TAGS: Final = ("owasp.llm06-2025", "asi.asi02", "atlas.AML.T0053")
C09_TAGS: Final = ("asi.asi02", "asi.asi04", "atlas.AML.T0110", "atlas.AML.T0109")


def tool_allowed(allowed: Sequence[str], name: str) -> bool:
    """`*` allows any tool; otherwise exact, case-sensitive names (no globs)."""
    return "*" in allowed or name in allowed


def _access(evidence: str) -> Finding:
    return Finding("access.tool", Category.TOOL, 1.0, evidence=evidence, tags=C03_TAGS)


def _named(name: str) -> str:
    return f"tool {name!r}" if TOOL_NAME_RE.fullmatch(name) else "invalid tool name"


def check_tools_input(allowed: Sequence[str], interaction: Interaction) -> Finding | None:
    """Declared tools and tool calls in the history (a forged history counts too)."""
    names = [t.name for t in interaction.tools]
    names += [c.name for m in interaction.messages for c in m.tool_calls]
    for name in names:
        if not TOOL_NAME_RE.fullmatch(name) or not tool_allowed(allowed, name):
            return _access(f"{_named(name)} not in allowed_tools")
    return None


def check_tools_output(allowed: Sequence[str], interaction: Interaction) -> Finding | None:
    """Tool calls the model makes: allowed and declared in this request (no invented tools)."""
    if interaction.output is None:
        return None
    declared = {t.name for t in interaction.tools}
    for call in interaction.output.tool_calls:
        if not TOOL_NAME_RE.fullmatch(call.name):
            return _access("model called an invalid tool name")
        if call.name not in declared:
            return _access(f"model called undeclared tool {call.name!r}")
        if not tool_allowed(allowed, call.name):
            return _access(f"model called tool {call.name!r}, not in allowed_tools")
    return None


def tool_digest(tool: ToolDef) -> str:
    """sha256 of the canonical definition: parameter key order does not matter, any change to
    the description (even a space) does."""
    canonical = json.dumps(
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": json.loads(tool.parameters_json or "{}"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pin(evidence: str) -> Finding:
    return Finding("tool.pin", Category.TOOL, 1.0, evidence=evidence, tags=C09_TAGS)


def check_duplicate_tools(interaction: Interaction) -> Finding | None:
    """Two definitions with one name in a request (shadowing)."""
    counts = Counter(t.name for t in interaction.tools)
    duplicate = next((name for name, n in counts.items() if n > 1), None)
    return _pin(f"{_named(duplicate)} defined more than once") if duplicate else None


def pin_findings(mismatches: Mapping[str, str], current: Mapping[str, str]) -> Finding | None:
    """Rug pull: a pinned tool definition changed (digests only, never the description)."""
    if not mismatches:
        return None
    name = sorted(mismatches)[0]
    return _pin(
        f"{_named(name)} definition changed: pinned {mismatches[name][:12]}, "
        f"got {current[name][:12]}"
    )
