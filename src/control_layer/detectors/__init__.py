"""Detector registry. Owner: Sebastian (Dev B).

Maps a control `kind` (policy `controls[].kind`) to a factory taking `DetectorDeps`.
"""

from __future__ import annotations

from control_layer.core.ports import DetectorFactory
from control_layer.detectors.egress import EgressDetector
from control_layer.detectors.injection_heuristics import InjectionHeuristics
from control_layer.detectors.pii import PiiDetector
from control_layer.detectors.prompt_guard import PromptGuardDetector
from control_layer.detectors.secrets import SecretsDetector

__all__ = ["REGISTRY"]

REGISTRY: dict[str, DetectorFactory] = {
    "pii": lambda deps: PiiDetector(),
    "secrets": lambda deps: SecretsDetector(),
    "injection_heuristics": lambda deps: InjectionHeuristics(),
    "prompt_guard": lambda deps: PromptGuardDetector(),
    "egress": lambda deps: EgressDetector(),
}
