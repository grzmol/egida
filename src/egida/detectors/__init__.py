"""Detector registry. Owner: Sebastian (Dev B).

Maps a control `kind` (policy `controls[].kind`) to a factory taking `DetectorDeps`.
"""

from __future__ import annotations

from egida.core.ports import DetectorFactory
from egida.detectors.canary import CanaryDetector
from egida.detectors.egress import EgressDetector
from egida.detectors.harmful_content import HarmfulContentDetector
from egida.detectors.injection_heuristics import InjectionHeuristics
from egida.detectors.pii import PiiDetector
from egida.detectors.prompt_guard import PromptGuardDetector
from egida.detectors.secrets import SecretsDetector

__all__ = ["REGISTRY"]

REGISTRY: dict[str, DetectorFactory] = {
    "pii": lambda deps: PiiDetector(),
    "secrets": lambda deps: SecretsDetector(),
    "injection_heuristics": lambda deps: InjectionHeuristics(),
    "prompt_guard": lambda deps: PromptGuardDetector(),
    "egress": lambda deps: EgressDetector(),
    "harmful_content": lambda deps: HarmfulContentDetector(deps.guard),
    "canary": lambda deps: CanaryDetector(),
}
