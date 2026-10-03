"""State shared by Egida's screens: open policy, run profile, proxy process and the UI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from egida.console.document import DocumentError, PolicyDocument
from egida.console.harnesses.base import HarnessEnv
from egida.console.runner import Proxy, RunProfile, save_profile
from egida.console.widgets import App

__all__ = ["Session"]

_SHOWN_PROBLEMS = 3


@dataclass
class Session:
    doc: PolicyDocument
    profile: RunProfile
    profile_path: Path
    proxy: Proxy
    param_models: Mapping[str, type[BaseModel]]
    app: App | None = None  # set once by screens.build_app (the App needs the root view first)
    harness_env: HarnessEnv = field(default_factory=HarnessEnv.current)

    @property
    def ui(self) -> App:
        if self.app is None:
            raise RuntimeError("Session.app is set by build_app before the first key")
        return self.app

    def errors(self) -> list[str]:
        """Problems of the policy as the proxy would see them ([] = valid, can be saved)."""
        return self.doc.validate(self.param_models)

    def change(self, mutate: Callable[[PolicyDocument], object]) -> bool:
        """Apply one edit to the policy. A refused edit (DocumentError: name taken, entry in use…)
        becomes an error box; an edit that makes a valid policy invalid shows what broke."""
        valid_before = not self.errors()
        try:
            mutate(self.doc)
        except DocumentError as exc:
            self.ui.notify("error", "Not changed", str(exc))
            return False
        problems = self.errors()
        if valid_before and problems:
            more = len(problems) - _SHOWN_PROBLEMS
            body = problems[:_SHOWN_PROBLEMS] + ([f"… and {more} more"] if more > 0 else [])
            self.ui.notify("error", "The policy is now invalid and cannot be saved", body)
        return True

    def open_policy(self, path: Path) -> None:
        """Edit another policy file and make it the one the proxy runs with (saved in the
        profile). DocumentError/ValueError propagate to the caller, nothing changes then."""
        doc = PolicyDocument.open(path)
        self.update_profile(policy=path)
        self.doc = doc

    def update_profile(self, **changes: Any) -> None:
        """Validate and persist run settings. ValueError carries a readable reason (an InputView
        shows it inline); a write failure is a ValueError too."""
        try:
            profile = RunProfile.model_validate(self.profile.model_dump() | changes)
        except ValidationError as exc:
            raise ValueError("; ".join(err["msg"] for err in exc.errors())) from exc
        save_profile(self.profile_path, profile)
        self.profile = profile
