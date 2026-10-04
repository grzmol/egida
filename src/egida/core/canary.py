"""C22 system-prompt canary: token format and injection (B7).

The pipeline adds a random token to the first system message right before the model call (after
input controls, so neither `secrets` nor C06 inspect our own text) when an enabled `canary`
control scans the output. The `canary` detector reads the token back from the system message
with CANARY_RE and blocks an output that contains it. The token never leaves the pipeline.
"""

from __future__ import annotations

import dataclasses
import re
import secrets
from typing import Final

from egida.core.models import Interaction

__all__ = ["CANARY_KIND", "CANARY_PREFIX", "CANARY_RE", "inject_canary", "new_canary"]

CANARY_KIND: Final = "canary"
CANARY_PREFIX: Final = "cl-canary-"
CANARY_RE: Final = re.compile(r"cl-canary-[0-9a-f]{16}")


def new_canary() -> str:
    return CANARY_PREFIX + secrets.token_hex(8)


def inject_canary(interaction: Interaction, token: str) -> Interaction:
    """Prefix the first system message with an HTML comment holding `token`; no system message,
    no change (there is no prompt to leak)."""
    if not CANARY_RE.fullmatch(token):
        raise ValueError(f"not a canary token: {token!r}")
    for i, message in enumerate(interaction.messages):
        if message.role == "system":
            marked = dataclasses.replace(message, content=f"<!-- {token} -->\n{message.content}")
            messages = (*interaction.messages[:i], marked, *interaction.messages[i + 1 :])
            return dataclasses.replace(interaction, messages=messages)
    return interaction
