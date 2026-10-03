"""Measure guard LLMs in Ollama on our cases (B6 spike, evidence for ADR-0006).

uv run python scripts/guard_spike.py --models llama-guard3:1b granite3-guardian:2b \
  --cases tests/cases/harmful.yaml --extra tests/cases/injection.yaml \
  --reps 3 --concurrency 4 --out var/guard-spike.json

Truth label: polarity negative = harmful. --extra cases (jailbreaks) are reported separately.
Mode: /api/chat with the server template, as each model card describes.
"""

import argparse
import asyncio
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

OLLAMA = "http://127.0.0.1:11434"


def load(path: str) -> list[dict[str, Any]]:
    return list(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def messages(model: str, case: dict[str, Any]) -> list[dict[str, str]]:
    user = case["request"]["messages"][-1]["content"]
    chat = [{"role": "user", "content": user}]
    if "model_reply" in case:
        chat.append({"role": "assistant", "content": str(case["model_reply"])})
    if model.startswith("granite3-guardian"):
        return [{"role": "system", "content": "harm"}, *chat]
    return chat  # llama-guard: never a system role (the template turns it into "Agent")


def parse(model: str, text: str) -> bool | None:
    """True = unsafe, False = safe, None = unparseable."""
    text = text.strip()
    if model.startswith("granite3-guardian"):
        return {"yes": True, "no": False}.get(text.casefold())
    if text == "safe":
        return False
    if re.fullmatch(r"unsafe\s*\n?\s*S\d+(,\s*S\d+)*", text):
        return True
    return None


async def ask(client: httpx.AsyncClient, model: str, case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    response = await client.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": model,
            "messages": messages(model, case),
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0, "num_predict": 10},
        },
    )
    response.raise_for_status()
    data = response.json()
    text = data["message"]["content"]
    return {
        "id": case["id"],
        "raw": text,
        "unsafe": parse(model, text),
        "ms": (time.perf_counter() - started) * 1000,
        "load_ms": data.get("load_duration", 0) / 1e6,
        "prompt_tokens": data.get("prompt_eval_count"),
    }


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(int(0.95 * len(ordered) + 0.5) - 1, 0)]


async def measure(model: str, cases: list[dict[str, Any]], extra: list[dict[str, Any]],
                  reps: int, concurrency: int) -> dict[str, Any]:  # fmt: skip
    async with httpx.AsyncClient(timeout=120) as client:
        await client.post(f"{OLLAMA}/api/generate", json={"model": model, "keep_alive": 0})
        cold = await ask(client, model, cases[0])
        await ask(client, model, cases[0])  # warm-up, outside the statistics
        runs = [await ask(client, model, c) for _ in range(reps) for c in cases]
        semaphore = asyncio.Semaphore(concurrency)

        async def limited(case: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await ask(client, model, case)

        concurrent = await asyncio.gather(*(limited(c) for c in cases))
        extra_runs = [await ask(client, model, c) for c in extra]

    first = {r["id"]: r for r in runs[: len(cases)]}  # temperature 0: verdict from rep 1

    def group(pred: Any) -> list[dict[str, Any]]:
        return [c for c in cases if pred(c)]

    def hits(selected: list[dict[str, Any]]) -> str:
        unsafe = sum(1 for c in selected if first[c["id"]]["unsafe"])
        return f"{unsafe}/{len(selected)}"

    is_pl = lambda c: "pl" in c.get("tags", [])  # noqa: E731
    is_out = lambda c: "model_reply" in c  # noqa: E731
    neg_in = group(lambda c: c["polarity"] == "negative" and not is_out(c))
    pos_in = group(lambda c: c["polarity"] == "positive" and not is_out(c))
    out = group(is_out)
    out_ok = sum(1 for c in out if first[c["id"]]["unsafe"] == (c["polarity"] == "negative"))
    short = [r["ms"] for r in runs]
    return {
        "model": model,
        "recall_en": hits([c for c in neg_in if not is_pl(c)]),
        "recall_pl": hits([c for c in neg_in if is_pl(c)]),
        "fp_en": hits([c for c in pos_in if not is_pl(c)]),
        "fp_pl": hits([c for c in pos_in if is_pl(c)]),
        "output_correct": f"{out_ok}/{len(out)}",
        "unparseable": sum(1 for r in runs if r["unsafe"] is None),
        "p50_c1_ms": round(statistics.median(short)),
        "p95_c1_ms": round(p95(short)),
        "p95_c4_ms": round(p95([r["ms"] for r in concurrent])),
        "cold_ms": round(cold["ms"]),
        "extra_flagged": f"{sum(1 for r in extra_runs if r['unsafe'])}/{len(extra_runs)}",
        "raw": {r["id"]: r["raw"] for r in runs[: len(cases)]},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--extra", default=None)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", default="var/guard-spike.json")
    args = parser.parse_args()
    cases = load(args.cases)
    extra = [
        c for c in (load(args.extra) if args.extra else [])
        if c["polarity"] == "negative" and c.get("request")
    ][:10]  # fmt: skip
    results = [asyncio.run(measure(m, cases, extra, args.reps, args.concurrency))
               for m in args.models]  # fmt: skip
    columns = [
        "model", "recall_en", "recall_pl", "fp_en", "fp_pl", "output_correct",
        "unparseable", "p50_c1_ms", "p95_c1_ms", "p95_c4_ms", "cold_ms", "extra_flagged",
    ]  # fmt: skip
    print("| " + " | ".join(columns) + " |")
    print("|" + "---|" * len(columns))
    for r in results:
        print("| " + " | ".join(str(r[c]) for c in columns) + " |")
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
