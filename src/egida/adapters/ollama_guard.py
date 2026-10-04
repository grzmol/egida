"""GuardModelClient on Ollama's native /api/generate (B6, ADR-0006).

Native API, not /v1: only /api/generate has `raw` (our prompt is rendered from the model card,
no server template) and `keep_alive` (-1 keeps the guard model in memory, so the first request
after a pause is not a cold load that runs into the control's timeout).
"""

from __future__ import annotations

from typing import Any

import httpx

from egida.core.errors import UpstreamError

__all__ = ["OllamaGuardClient"]

CLIENT_TIMEOUT_S = 60.0  # upper bound only; the control's timeout_ms (asyncio.wait_for) decides


class OllamaGuardClient:
    """The httpx client is owned by the caller (created and closed in the app lifespan)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, keep_alive: int | str = -1) -> None:
        self._http = http
        self._url = base_url.rstrip("/") + "/api/generate"
        self._keep_alive = keep_alive

    async def generate(self, model: str, prompt: str, max_tokens: int) -> str:
        data = await self._post(
            {
                "model": model,
                "prompt": prompt,
                "raw": True,
                "stream": False,
                "keep_alive": self._keep_alive,
                "options": {"temperature": 0, "num_predict": max_tokens},
            }
        )
        answer = data.get("response") if isinstance(data, dict) else None
        if not isinstance(answer, str):
            raise UpstreamError(f"guard: response without text field: {str(data)[:200]}")
        return answer

    async def load(self, model: str) -> None:
        """A request without `prompt` makes Ollama load the model and keep it for keep_alive."""
        await self._post({"model": model, "keep_alive": self._keep_alive})

    async def _post(self, body: dict[str, Any]) -> Any:
        try:
            response = await self._http.post(self._url, json=body, timeout=CLIENT_TIMEOUT_S)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"guard: HTTP {exc.response.status_code}: {_error_text(exc.response)}"
            ) from exc
        except httpx.TransportError as exc:  # includes timeouts and connection errors
            raise UpstreamError(f"guard: unreachable: {type(exc).__name__}: {exc}") from exc
        except ValueError as exc:
            raise UpstreamError(f"guard: invalid JSON: {exc}") from exc


def _error_text(response: httpx.Response) -> str:
    """Ollama reports problems (e.g. model not pulled) as {"error": "..."}."""
    try:
        data = response.json()
    except ValueError:
        return response.text[:200]
    return str(data.get("error", data))[:200] if isinstance(data, dict) else str(data)[:200]
