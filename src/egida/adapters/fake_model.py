"""In-memory ModelClient and GuardModelClient for tests and offline case runs (no network)."""

from __future__ import annotations

from collections.abc import Callable

from egida.core.errors import UpstreamError
from egida.core.models import Interaction, Message, Usage
from egida.core.policy import UpstreamConfig
from egida.core.ports import ModelResult

__all__ = ["FakeGuardModelClient", "FakeModelClient"]

_DEFAULT_USAGE = Usage(prompt_tokens=10, completion_tokens=5)


class FakeModelClient:
    """Returns a fixed or computed reply and records what the model would have seen."""

    def __init__(
        self,
        reply: str | Message | Callable[[Interaction], str | Message] = "OK",
        usage: Usage = _DEFAULT_USAGE,
        raise_error: bool = False,
    ) -> None:
        self._reply = reply
        self._usage = usage
        self._raise_error = raise_error
        self.calls = 0
        self.last_interaction: Interaction | None = None

    async def complete(self, interaction: Interaction, upstream: UpstreamConfig) -> ModelResult:
        self.calls += 1
        self.last_interaction = interaction
        if self._raise_error:
            raise UpstreamError(f"fake upstream failure ({upstream.base_url})")
        reply = self._reply(interaction) if callable(self._reply) else self._reply
        message = reply if isinstance(reply, Message) else Message(role="assistant", content=reply)
        return ModelResult(
            message=message,
            usage=self._usage,
            finish_reason="tool_calls" if message.tool_calls else "stop",
        )


class FakeGuardModelClient:
    """Guard model stand-in: fixed or computed answer; records prompts and loaded models."""

    def __init__(
        self, reply: str | Callable[[str], str] = "safe", raise_error: bool = False
    ) -> None:
        self._reply = reply
        self._raise_error = raise_error
        self.prompts: list[str] = []
        self.loaded: list[str] = []

    async def generate(self, model: str, prompt: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        if self._raise_error:
            raise UpstreamError(f"fake guard failure ({model})")
        return self._reply(prompt) if callable(self._reply) else self._reply

    async def load(self, model: str) -> None:
        if self._raise_error:
            raise UpstreamError(f"fake guard failure ({model})")
        self.loaded.append(model)
