#!/usr/bin/env python3
"""
scripts/prepare_eval_data.py
Pobiera próbki publicznych zbiorów danych do pomiaru FP/FN i przygotowuje pliki w formacie JSONL.
Właściciel: Kamil (Dev C), zadanie K2.

Zbiory:
- deepset/prompt-injections (split: test, ~116 wierszy, attack/benign)
- Lakera/gandalf_ignore_instructions (split: train, pierwsze 150, attack)
- JailbreakBench/JBB-Behaviors (splits: harmful, benign, 100+100, attack/benign)
- Paul/XSTest (split: train, tylko label == 'safe', benign)
- docs/eval/pl-manual.yaml -> pl-manual.jsonl (20 attack + 20 benign PL, bez sieci)

Wszystkie pliki wyjściowe lądują w var/eval/*.jsonl (poza gitem).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Obsługa httpx z fallbackiem na urllib (stdlib)
try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

import urllib.error
import urllib.request


HF_ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"
USER_AGENT = "froggers-eval-data-prep/1.0"
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


def fetch_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pobiera JSON z endpointu z ponawianiem prób (3 próby) i timeoutem 30s."""
    query = ""
    if params:
        query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}{query}"

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if httpx is not None:
                with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
                    resp = client.get(full_url)
                    resp.raise_for_status()
                    return resp.json()
            else:
                req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                    data = response.read().decode("utf-8")
                    return json.loads(data)
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt}/{MAX_RETRIES}] Błąd pobierania {full_url}: {exc}. Ponawiam za {RETRY_BACKOFF}s...", file=sys.stderr)
                time.sleep(RETRY_BACKOFF)

    print(f"[BŁĄD KRYTYCZNY] Nie udało się pobrać {full_url} po {MAX_RETRIES} próbach: {last_error}", file=sys.stderr)
    sys.exit(1)


def atomic_write_jsonl(dest_path: Path, records: list[dict[str, Any]]) -> None:
    """Zapisuje listę rekordów do pliku tymczasowego, a następnie atomowo podmienia docelowy plik."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(temp_path, dest_path)


def process_deepset() -> list[dict[str, Any]]:
    """Pobiera deepset/prompt-injections (split test, 116 wierszy)."""
    dataset = "deepset/prompt-injections"
    config = "default"
    split = "test"
    records: list[dict[str, Any]] = []

    data = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": split, "offset": 0, "length": 100})
    rows = data.get("rows", [])
    data2 = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": split, "offset": 100, "length": 100})
    rows.extend(data2.get("rows", []))

    for idx, r in enumerate(rows):
        row = r["row"]
        label = "attack" if row.get("label") == 1 else "benign"
        records.append({
            "id": f"deepset-test-{idx:04d}",
            "text": row["text"],
            "label": label,
            "lang": "en",
            "source": dataset,
            "license": "apache-2.0",
        })
    return records


def process_gandalf() -> list[dict[str, Any]]:
    """Pobiera Lakera/gandalf_ignore_instructions (split train, pierwsze 150 wierszy, wszystkie to attack)."""
    dataset = "Lakera/gandalf_ignore_instructions"
    config = "default"
    split = "train"
    records: list[dict[str, Any]] = []

    data1 = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": split, "offset": 0, "length": 100})
    rows = data1.get("rows", [])
    data2 = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": split, "offset": 100, "length": 50})
    rows.extend(data2.get("rows", []))

    for idx, r in enumerate(rows[:150]):
        row = r["row"]
        records.append({
            "id": f"gandalf-train-{idx:04d}",
            "text": row["text"],
            "label": "attack",
            "lang": "en",
            "source": dataset,
            "license": "MIT",
        })
    return records


def process_jbb() -> list[dict[str, Any]]:
    """Pobiera JailbreakBench/JBB-Behaviors (config behaviors, harmful 100 + benign 100)."""
    dataset = "JailbreakBench/JBB-Behaviors"
    config = "behaviors"
    records: list[dict[str, Any]] = []

    # harmful (attack)
    harmful_data = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": "harmful", "offset": 0, "length": 100})
    for idx, r in enumerate(harmful_data.get("rows", [])):
        row = r["row"]
        records.append({
            "id": f"jbb-harmful-{idx:04d}",
            "text": row["Goal"],
            "label": "attack",
            "lang": "en",
            "source": dataset,
            "license": "MIT",
        })

    # benign (benign)
    benign_data = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": "benign", "offset": 0, "length": 100})
    for idx, r in enumerate(benign_data.get("rows", [])):
        row = r["row"]
        records.append({
            "id": f"jbb-benign-{idx:04d}",
            "text": row["Goal"],
            "label": "benign",
            "lang": "en",
            "source": dataset,
            "license": "MIT",
        })

    return records


def process_xstest() -> list[dict[str, Any]]:
    """Pobiera Paul/XSTest (split train, filtruje tylko label == 'safe' -> benign)."""
    dataset = "Paul/XSTest"
    config = "default"
    split = "train"
    records: list[dict[str, Any]] = []

    # XSTest ma 450 wierszy
    rows: list[dict[str, Any]] = []
    for offset in range(0, 500, 100):
        data = fetch_json(HF_ROWS_ENDPOINT, {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": 100})
        batch = data.get("rows", [])
        if not batch:
            break
        rows.extend(batch)

    out_idx = 0
    for r in rows:
        row = r["row"]
        if row.get("label") == "safe":
            records.append({
                "id": f"xstest-train-{out_idx:04d}",
                "text": row["prompt"],
                "label": "benign",
                "lang": "en",
                "source": dataset,
                "license": "CC-BY-4.0",
            })
            out_idx += 1

    return records


def process_pl_manual(yaml_path: Path) -> list[dict[str, Any]]:
    """Parsuje docs/eval/pl-manual.yaml i zwraca rekordy ewaluacyjne bez zapytań sieciowych."""
    if not yaml_path.exists():
        print(f"[BŁĄD] Plik {yaml_path} nie istnieje!", file=sys.stderr)
        sys.exit(1)

    records: list[dict[str, Any]] = []
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            items = yaml.safe_load(f)
    except ImportError:
        # Awaryjny prosty parser dla pl-manual.yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        items = []
        current: dict[str, Any] = {}
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if line_str.startswith("- id:"):
                if current:
                    items.append(current)
                current = {"id": line_str.split(":", 1)[1].strip()}
            elif ":" in line_str and current:
                k, v = line_str.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                current[k] = v
        if current:
            items.append(current)

    for item in items:
        records.append({
            "id": item["id"],
            "text": item["text"],
            "label": item["label"],
            "lang": item.get("lang", "pl"),
            "source": item.get("source", "froggers-manual"),
            "license": item.get("license", "własne"),
        })
    return records


def print_summary(results: dict[str, list[dict[str, Any]]]) -> None:
    print("\n" + "=" * 60)
    print("PODSUMOWANIE POBRANYCH ZBIORÓW EWALUACYJNYCH (var/eval/)")
    print("=" * 60)
    total_attacks = 0
    total_benign = 0
    for name, records in results.items():
        attacks = sum(1 for r in records if r["label"] == "attack")
        benign = sum(1 for r in records if r["label"] == "benign")
        total_attacks += attacks
        total_benign += benign
        print(f"📁 {name:<18} | Łącznie: {len(records):>4} | Ataki: {attacks:>4} | Niewinne: {benign:>4}")
    print("-" * 60)
    print(f"SUMA WSZYSTKICH PRÓBEK:  | Łącznie: {total_attacks + total_benign:>4} | Ataki: {total_attacks:>4} | Niewinne: {total_benign:>4}")
    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pobieranie i przygotowanie zbiorów ewaluacyjnych FP/FN.")
    parser.add_argument(
        "--only",
        type=str,
        default="deepset,gandalf,jbb,xstest,pl-manual",
        help="Przecinkowa lista zbiorów do pobrania (np. 'deepset,jbb')",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="var/eval",
        help="Katalog wyjściowy dla plików JSONL",
    )
    args = parser.parse_args()

    selected = {s.strip().lower() for s in args.only.split(",") if s.strip()}
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / args.out_dir
    pl_yaml_path = repo_root / "docs" / "eval" / "pl-manual.yaml"

    results: dict[str, list[dict[str, Any]]] = {}

    if "deepset" in selected:
        print("[1/5] Pobieranie deepset/prompt-injections (split: test)...")
        records = process_deepset()
        atomic_write_jsonl(out_dir / "deepset.jsonl", records)
        results["deepset.jsonl"] = records

    if "gandalf" in selected:
        print("[2/5] Pobieranie Lakera/gandalf_ignore_instructions (split: train, 150 wierszy)...")
        records = process_gandalf()
        atomic_write_jsonl(out_dir / "gandalf.jsonl", records)
        results["gandalf.jsonl"] = records

    if "jbb" in selected:
        print("[3/5] Pobieranie JailbreakBench/JBB-Behaviors (harmful + benign, 200 wierszy)...")
        records = process_jbb()
        atomic_write_jsonl(out_dir / "jbb.jsonl", records)
        results["jbb.jsonl"] = records

    if "xstest" in selected:
        print("[4/5] Pobieranie Paul/XSTest (split: train, tylko label == 'safe')...")
        records = process_xstest()
        atomic_write_jsonl(out_dir / "xstest.jsonl", records)
        results["xstest.jsonl"] = records

    if "pl-manual" in selected:
        print("[5/5] Przetwarzanie docs/eval/pl-manual.yaml...")
        records = process_pl_manual(pl_yaml_path)
        atomic_write_jsonl(out_dir / "pl-manual.jsonl", records)
        results["pl-manual.jsonl"] = records

    print_summary(results)


if __name__ == "__main__":
    main()
