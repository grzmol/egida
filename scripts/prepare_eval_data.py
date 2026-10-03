#!/usr/bin/env python3
"""Sample public datasets for FP/FN measurement into var/eval/*.jsonl (outside git).

Owner: Kamil (Dev C), task K2. Sources and licences: docs/eval/SOURCES.md.

- deepset/prompt-injections        split test, all rows (~116), attack/benign
- Lakera/gandalf_ignore_instructions split train, first 150, attack
- JailbreakBench/JBB-Behaviors      config behaviors, harmful 100 + benign 100
- Paul/XSTest                       split train, only label == "safe", benign
- docs/eval/pl-manual.yaml          Polish manual cases, no network

Run: uv run python scripts/prepare_eval_data.py [--only deepset,jbb] [--out-dir var/eval]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100  # datasets-server maximum page size
RETRIES = 3
BACKOFF_S = 2.0


def fetch_rows(client: httpx.Client, dataset: str, config: str, split: str, limit: int) -> list:
    """Up to `limit` rows of one split, paged; retries transient errors, exits after RETRIES."""
    rows: list[dict[str, Any]] = []
    while len(rows) < limit:
        params = {
            "dataset": dataset,
            "config": config,
            "split": split,
            "offset": len(rows),
            "length": min(PAGE, limit - len(rows)),
        }
        for attempt in range(1, RETRIES + 1):
            try:
                resp = client.get(ROWS_URL, params=params)
                resp.raise_for_status()
                batch = [r["row"] for r in resp.json().get("rows", [])]
                break
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                if attempt == RETRIES:
                    sys.exit(f"[ERROR] {dataset}/{split} offset {len(rows)}: {exc}")
                print(f"[RETRY {attempt}/{RETRIES}] {dataset}: {exc}", file=sys.stderr)
                time.sleep(BACKOFF_S)
        if not batch:
            break
        rows.extend(batch)
    return rows


def record(rid: str, text: str, label: str, source: str, licence: str, lang: str = "en") -> dict:
    return {"id": rid, "text": text, "label": label, "lang": lang, "source": source,
            "license": licence}  # fmt: skip


def deepset(client: httpx.Client) -> list[dict[str, Any]]:
    ds = "deepset/prompt-injections"
    rows = fetch_rows(client, ds, "default", "test", 200)
    return [
        record(
            f"deepset-test-{i:04d}",
            r["text"],
            "attack" if r.get("label") == 1 else "benign",
            ds,
            "apache-2.0",
        )  # fmt: skip
        for i, r in enumerate(rows)
    ]


def gandalf(client: httpx.Client) -> list[dict[str, Any]]:
    ds = "Lakera/gandalf_ignore_instructions"
    rows = fetch_rows(client, ds, "default", "train", 150)
    return [
        record(f"gandalf-train-{i:04d}", r["text"], "attack", ds, "MIT") for i, r in enumerate(rows)
    ]


def jbb(client: httpx.Client) -> list[dict[str, Any]]:
    ds = "JailbreakBench/JBB-Behaviors"
    out = []
    for split, label in (("harmful", "attack"), ("benign", "benign")):
        rows = fetch_rows(client, ds, "behaviors", split, 100)
        out += [
            record(f"jbb-{split}-{i:04d}", r["Goal"], label, ds, "MIT") for i, r in enumerate(rows)
        ]
    return out


def xstest(client: httpx.Client) -> list[dict[str, Any]]:
    ds = "Paul/XSTest"
    safe = [r for r in fetch_rows(client, ds, "default", "train", 500) if r.get("label") == "safe"]
    return [
        record(f"xstest-train-{i:04d}", r["prompt"], "benign", ds, "CC-BY-4.0")
        for i, r in enumerate(safe)
    ]


def pl_manual(path: Path) -> list[dict[str, Any]]:
    items = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        record(
            i["id"],
            i["text"],
            i["label"],
            i.get("source", "froggers-manual"),
            i.get("license", "własne"),
            i.get("lang", "pl"),
        )  # fmt: skip
        for i in items
    ]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomic: a crash never leaves half a file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), "utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare FP/FN evaluation samples.")
    parser.add_argument("--only", default="deepset,gandalf,jbb,xstest,pl-manual")
    parser.add_argument("--out-dir", default="var/eval")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = root / args.out_dir
    selected = {s.strip().lower() for s in args.only.split(",") if s.strip()}
    headers = {"User-Agent": "froggers-eval-data-prep/1.0"}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        sources = {
            "deepset": lambda: deepset(client),
            "gandalf": lambda: gandalf(client),
            "jbb": lambda: jbb(client),
            "xstest": lambda: xstest(client),
            "pl-manual": lambda: pl_manual(root / "docs" / "eval" / "pl-manual.yaml"),
        }
        for name in selected - sources.keys():
            sys.exit(f"[ERROR] unknown source {name!r}; choose from {', '.join(sources)}")
        for name, load in sources.items():
            if name not in selected:
                continue
            records = load()
            write_jsonl(out_dir / f"{name}.jsonl", records)
            attacks = sum(r["label"] == "attack" for r in records)
            print(f"{name:<10} total {len(records):>4}  attack {attacks:>4}  "
                  f"benign {len(records) - attacks:>4}")  # fmt: skip


if __name__ == "__main__":
    main()
