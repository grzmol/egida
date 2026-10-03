"""Detector registry. Owner: Sebastian (Dev B) — created empty by A0.

Maps a control `kind` (policy `controls[].kind`) to a factory taking `DetectorDeps`.
"""

from __future__ import annotations

from control_layer.core.ports import DetectorFactory

__all__ = ["REGISTRY"]

REGISTRY: dict[str, DetectorFactory] = {}
