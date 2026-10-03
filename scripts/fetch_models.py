"""Download pinned Prompt Guard 2 ONNX exports into models/ and verify sha256 (control C12).

Usage: uv run python scripts/fetch_models.py [--small]

Source: unofficial, non-gated ONNX exports by gravitee-io (Llama 4 Community License),
see docs/research/02-detektory-i-modele.md §1b. Revisions are pinned to commits, so the
model cannot change between runs. Existing files are only verified, never re-downloaded;
a checksum mismatch exits with code 1.
"""

import argparse
import hashlib
import sys
from pathlib import Path

import httpx

MODELS: dict[str, tuple[str, str, dict[str, str]]] = {
    "prompt-guard-2-86m": (
        "gravitee-io/Llama-Prompt-Guard-2-86M-onnx",
        "45a05fbd5337a864edc608f994911f009c37ca57",
        {
            "model.quant.onnx": "3ca25030566076c92c19168a64d6e203e4397cd936f55dd0345b4d3c6fbd9744",
            "tokenizer.json": "870798f0e3bb05c636bf62be904b2d8f48ace4785e9c1d71a8a67bd0586c941d",
            "config.json": "a39ae60b9b718b72bbe3f359ad07ddf6909dcb09ccff936c00a488ceb4e983a6",
            "LICENSE": "90ae4807183070953bd8da5d7be81c4494920fb54c74359383c8a4536bf003c3",
            "NOTICE": "6d70b1303958ace2c652d10ffcb63cdd8436d49bc0e81c97373df4e329fad0c9",
        },
    ),
    "prompt-guard-2-22m": (
        "gravitee-io/Llama-Prompt-Guard-2-22M-onnx",
        "da68d0f6023c7aeaf6b256eec549de295d5e8740",
        {
            "model.quant.onnx": "38c3f03e30a4d5d229aeb7bf638e778322f8179d0ed0d4953eb22f88d8e0cf6b",
            "tokenizer.json": "92c8b45d0b12ae0dd9680fbfe9804503542c377d65838558cd0b48a795385dde",
            "config.json": "db1a6dabb734766632a009e17fa72ac4d110505f4be0651654dafc30002461cc",
            "LICENSE": "90ae4807183070953bd8da5d7be81c4494920fb54c74359383c8a4536bf003c3",
            "NOTICE": "6d70b1303958ace2c652d10ffcb63cdd8436d49bc0e81c97373df4e329fad0c9",
        },
    ),
}
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(client: httpx.Client, url: str, path: Path) -> None:
    part = path.with_name(path.name + ".part")
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with part.open("wb") as f:
            for chunk in response.iter_bytes(1 << 20):
                f.write(chunk)
    part.replace(path)


def fetch(name: str) -> bool:
    repo, revision, files = MODELS[name]
    target = MODELS_DIR / name
    target.mkdir(parents=True, exist_ok=True)
    ok = True
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30, read=300)) as client:
        for filename, expected in files.items():
            path = target / filename
            if not path.exists():
                print(f"downloading {repo}@{revision[:8]}/{filename}")
                download(
                    client, f"https://huggingface.co/{repo}/resolve/{revision}/{filename}", path
                )
            actual = sha256(path)
            if actual != expected:
                print(f"SHA256 MISMATCH {path}\n  expected {expected}\n  actual   {actual}")
                ok = False
            else:
                print(f"ok {path.relative_to(MODELS_DIR.parent)}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--small", action="store_true", help="22M variant (faster, weaker PL)")
    args = parser.parse_args()
    try:
        ok = fetch("prompt-guard-2-22m" if args.small else "prompt-guard-2-86m")
    except httpx.HTTPError as e:
        print(f"download failed: {e}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
