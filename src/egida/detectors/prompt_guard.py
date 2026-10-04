"""C07: Llama Prompt Guard 2 86M classifier (BENIGN/MALICIOUS), ONNX in process, no torch.

Model files come from scripts/fetch_models.py. The directory is read once at startup from
EGIDA_MODELS_DIR (default: models/), not from policy params, because the factory
loads the model before any policy exists. Built with Llama (Llama 4 Community License).
"""

import os
import re
import threading
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

import anyio
import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]  # no stubs upstream
from pydantic import BaseModel, ConfigDict, Field
from tokenizers import Tokenizer

from egida.core.models import Category, Finding, Interaction, Side
from egida.core.ports import ScanContext
from egida.core.texts import iter_texts

MODEL_NAME = "prompt-guard-2-86m"
MALICIOUS = 1  # config.json id2label: {"0": "BENIGN", "1": "MALICIOUS"}
# Two passes over each text: model-size windows, and single sentences, so one attack sentence
# inside a long benign document is not diluted (a 512-token window scores it ~0.01).
LONG_WINDOW, LONG_STEP = 510, 446  # content tokens; [CLS] + 510 + [SEP] = 512 = model context
SENTENCE_TOKENS, SENTENCE_MAX = 62, 256
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+|\n+")
CONCURRENT_SCANS, SLOT_POLL_S = 2, 0.05
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


def windows(ids: list[int], size: int, step: int, limit: int) -> tuple[list[list[int]], bool]:
    """Overlapping slices of `ids`; past `limit`, keep head and tail (attacks hide at ends)."""
    chunks = [ids[i : i + size] for i in range(0, max(len(ids) - size, 0) + step, step)]
    chunks = [c for c in chunks if c] or [[]]
    if len(chunks) <= limit:
        return chunks, False
    return chunks[: limit // 2] + chunks[-(limit - limit // 2) :], True


@lru_cache(maxsize=2)
def load_model(root: Path) -> tuple[ort.InferenceSession, Tokenizer]:
    """One session per model directory per process: loading costs ~0.3 s and 300 MB."""
    model, tokenizer_path = root / "model.quant.onnx", root / "tokenizer.json"
    for path in (model, tokenizer_path):
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing; run `make models`")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4  # x2 concurrent scans (CONCURRENT_SCANS) = 8 cores
    session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.no_padding()  # windows are built by hand; the export pads every input to 512
    tokenizer.no_truncation()
    return session, tokenizer


class PromptGuardDetector:
    kind: ClassVar[str] = "prompt_guard"
    Params: ClassVar[type[BaseModel]] = PromptGuardParams

    def __init__(self, model_dir: Path | None = None) -> None:
        root = model_dir or Path(os.environ.get("EGIDA_MODELS_DIR", "models")) / MODEL_NAME
        self._session, self._tokenizer = load_model(root.resolve())
        cls, sep = self._tokenizer.token_to_id("[CLS]"), self._tokenizer.token_to_id("[SEP]")
        if cls is None or sep is None:
            raise ValueError(f"{root}/tokenizer.json has no [CLS]/[SEP] tokens")
        self._cls: int = cls
        self._sep: int = sep
        # Inference slots are taken on the worker thread, so a scan abandoned by its timeout
        # keeps its slot until the ONNX run really ends (anyio's limiter would free it at once).
        self._slots = threading.BoundedSemaphore(CONCURRENT_SCANS)
        # History messages repeat on every agent turn: score each distinct text once.
        self._cached = lru_cache(maxsize=4096)(self._probability)

    def _batch(self, chunks: Sequence[Sequence[int]]) -> float:
        """Max P(MALICIOUS) over one batch of windows (right-padded, masked)."""
        width = max(len(c) for c in chunks) + 2
        ids = np.zeros((len(chunks), width), dtype=np.int64)
        mask = np.zeros((len(chunks), width), dtype=np.int64)
        for row, chunk in enumerate(chunks):
            tokens = [self._cls, *chunk, self._sep]
            ids[row, : len(tokens)] = tokens
            mask[row, : len(tokens)] = 1
        logits = self._session.run(None, {"input_ids": ids, "attention_mask": mask})[0]
        exp = np.exp(logits - logits.max(axis=1, keepdims=True))
        return float((exp[:, MALICIOUS] / exp.sum(axis=1)).max())

    def _probability(self, text: str, max_windows: int) -> tuple[float, int, bool]:
        # tokenizers (Rust) rejects lone surrogates with a generic TypeError; JSON can carry them.
        text = text.encode("utf-8", "replace").decode("utf-8")
        ids = self._tokenizer.encode(text, add_special_tokens=False).ids
        long, long_cut = windows(ids, LONG_WINDOW, LONG_STEP, max_windows)
        best = max(self._batch(long[i : i + 4]) for i in range(0, len(long), 4))
        used, cut = len(long), long_cut
        sentences = [x for x in _SENTENCE_END.split(text) if x.strip()]
        if len(sentences) > 1:
            pieces: list[Sequence[int]] = []
            for encoding in self._tokenizer.encode_batch(sentences, add_special_tokens=False):
                pieces += windows(encoding.ids, SENTENCE_TOKENS, SENTENCE_TOKENS, 4)[0]
            if len(pieces) > SENTENCE_MAX:
                pieces = pieces[: SENTENCE_MAX // 2] + pieces[-SENTENCE_MAX // 2 :]
                cut = True
            # Repeated sentences are scored once; sorting by length keeps batch padding small.
            pieces = sorted({tuple(piece) for piece in pieces}, key=len)
            best = max(best, *(self._batch(pieces[i : i + 64]) for i in range(0, len(pieces), 64)))
            used += len(pieces)
        return best, used, cut

    def malicious_probability(self, text: str, max_windows: int) -> tuple[float, int]:
        """Max P(MALICIOUS) over long and short windows, and the number of windows scored."""
        best, used, _ = self._cached(text, max_windows)
        return best, used

    def _scan(self, ctx: ScanContext, texts: list[tuple[str, str]]) -> list[Finding]:
        params = ctx.params
        if not isinstance(params, PromptGuardParams):
            raise TypeError(f"expected PromptGuardParams, got {type(params).__name__}")
        if ctx.side is not Side.INPUT:
            raise ValueError("prompt_guard classifies inputs only; set `sides: [input]`")
        best, best_target, used, truncated = 0.0, "", 0, False
        for target, text in selected_texts(ctx.interaction, texts, params):
            score, n, cut = self._cached(text, params.max_windows)
            used, truncated = used + n, truncated or cut
            if score >= best:
                best, best_target = score, target
        if not best_target:
            return []
        evidence = f"{best_target} p={best:.2f} windows={used}" + (
            " truncated" if truncated else ""
        )
        return [
            Finding(
                control_id=ctx.control_id,
                category=Category.INJECTION,
                score=best,
                evidence=evidence,
                tags=TAGS,
            )
        ]

    def _scan_in_slot(
        self, ctx: ScanContext, texts: list[tuple[str, str]], abandoned: threading.Event
    ) -> list[Finding]:
        """Waits for a free inference slot; gives up without running if the caller timed out."""
        while not self._slots.acquire(timeout=SLOT_POLL_S):
            if abandoned.is_set():
                return []
        try:
            return [] if abandoned.is_set() else self._scan(ctx, texts)
        finally:
            self._slots.release()

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        texts = list(iter_texts(ctx.interaction, ctx.side))
        abandoned = threading.Event()
        try:
            return await anyio.to_thread.run_sync(
                self._scan_in_slot, ctx, texts, abandoned, abandon_on_cancel=True
            )
        except anyio.get_cancelled_exc_class():
            abandoned.set()
            raise
