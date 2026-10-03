"""C07: Llama Prompt Guard 2 86M classifier (BENIGN/MALICIOUS), ONNX in process, no torch.

Model files come from scripts/fetch_models.py. The directory is read once at startup from
CONTROL_LAYER_MODELS_DIR (default: models/), not from policy params, because the factory
loads the model before any policy exists. Built with Llama (Llama 4 Community License).
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

import anyio
import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]  # no stubs upstream
from pydantic import BaseModel, ConfigDict, Field
from tokenizers import Tokenizer

from control_layer.core.models import Category, Finding, Interaction
from control_layer.core.ports import ScanContext
from control_layer.core.texts import iter_texts

MODEL_NAME = "prompt-guard-2-86m"
MALICIOUS = 1  # config.json id2label: {"0": "BENIGN", "1": "MALICIOUS"}
WINDOW_TOKENS, WINDOW_OVERLAP = 512, 64  # 512 = model context; overlap catches split phrases
TAGS = ("owasp.llm01-2025", "asi.asi01", "atlas.AML.T0051")
_MESSAGE = re.compile(r"messages\[(\d+)\]\.content")
_TOOL_DESCRIPTION = re.compile(r"tools\[\d+\]\.description")


class PromptGuardParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_windows: int = Field(default=16, ge=1)  # per text; longer input is stopped by C17
    roles: tuple[Literal["system", "user", "assistant", "tool"], ...] = ("system", "user", "tool")
    scan_tool_descriptions: bool = True


def selected_texts(
    interaction: Interaction, texts: list[tuple[str, str]], params: PromptGuardParams
) -> list[tuple[str, str]]:
    """Message contents of the chosen roles and, optionally, tool descriptions."""
    chosen = []
    for target, text in texts:
        message = _MESSAGE.fullmatch(target)
        if message:
            keep = interaction.messages[int(message.group(1))].role in params.roles
        else:
            keep = params.scan_tool_descriptions and bool(_TOOL_DESCRIPTION.fullmatch(target))
        if keep and text.strip():
            chosen.append((target, text))
    return chosen


@lru_cache(maxsize=2)
def load_model(root: Path) -> tuple[ort.InferenceSession, Tokenizer]:
    """One session per model directory per process: loading costs ~0.3 s and 300 MB."""
    model, tokenizer_path = root / "model.quant.onnx", root / "tokenizer.json"
    for path in (model, tokenizer_path):
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing; run `make models`")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4  # x2 concurrent scans (limiter) = 8 cores
    session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.no_padding()  # the export pads to 512; short prompts run 20x faster
    tokenizer.enable_truncation(WINDOW_TOKENS, stride=WINDOW_OVERLAP)
    return session, tokenizer


class PromptGuardDetector:
    kind: ClassVar[str] = "prompt_guard"
    Params: ClassVar[type[BaseModel]] = PromptGuardParams

    def __init__(self, model_dir: Path | None = None) -> None:
        root = model_dir or Path(os.environ.get("CONTROL_LAYER_MODELS_DIR", "models")) / MODEL_NAME
        self._session, self._tokenizer = load_model(root.resolve())
        self._limiter: anyio.CapacityLimiter | None = None

    def malicious_probability(self, text: str, max_windows: int) -> tuple[float, int]:
        """Max P(MALICIOUS) over overlapping token windows, and the number of windows scored."""
        first = self._tokenizer.encode(text)
        windows = [first, *first.overflowing]
        if len(windows) > max_windows:  # keep head and tail: attacks hide at either end
            windows = windows[: max_windows // 2] + windows[-(max_windows - max_windows // 2) :]
        best = 0.0
        for window in windows:
            feed = {
                "input_ids": np.array([window.ids], dtype=np.int64),
                "attention_mask": np.array([window.attention_mask], dtype=np.int64),
            }
            logits = self._session.run(None, feed)[0][0]
            exp = np.exp(logits - logits.max())
            best = max(best, float(exp[MALICIOUS] / exp.sum()))
        return best, len(windows)

    def _scan(self, ctx: ScanContext, texts: list[tuple[str, str]]) -> list[Finding]:
        params = ctx.params
        if not isinstance(params, PromptGuardParams):
            raise TypeError(f"expected PromptGuardParams, got {type(params).__name__}")
        best, best_target, windows = 0.0, "", 0
        for target, text in selected_texts(ctx.interaction, texts, params):
            score, used = self.malicious_probability(text, params.max_windows)
            windows += used
            if score >= best:
                best, best_target = score, target
        if not best_target:
            return []
        return [
            Finding(
                control_id=ctx.control_id,
                category=Category.INJECTION,
                score=best,
                evidence=f"{best_target} p={best:.2f} windows={windows}",
                tags=TAGS,
            )
        ]

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        if self._limiter is None:
            self._limiter = anyio.CapacityLimiter(2)
        texts = list(iter_texts(ctx.interaction, ctx.side))
        return await anyio.to_thread.run_sync(
            self._scan, ctx, texts, limiter=self._limiter, abandon_on_cancel=True
        )
