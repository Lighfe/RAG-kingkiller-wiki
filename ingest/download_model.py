"""Download an ONNX embedding model + tokenizer from the Hugging Face Hub.

Adapted from the LLM Zoomcamp course's download.py/embedder.py pattern
(task 8 Part C) rather than reimplemented — same ONNX-candidate probing
and local-cache-if-present logic.

Run: ``uv run python -m ingest.download_model Xenova/bge-small-en-v1.5``
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, list_repo_files

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

ONNX_CANDIDATES = [
    "onnx/model.onnx",
    "onnx/encoder_model.onnx",
    "model.onnx",
]


def download(repo: str, dest: str = "models") -> Path:
    dest_path = Path(dest) / repo
    dest_path.mkdir(parents=True, exist_ok=True)

    files = list_repo_files(repo_id=repo)
    onnx_file = next((c for c in ONNX_CANDIDATES if c in files), None)
    if not onnx_file:
        raise FileNotFoundError(f"No ONNX model found in {repo}")

    for remote, local in [
        ("tokenizer.json", "tokenizer.json"),
        (onnx_file, "model.onnx"),
    ]:
        src = hf_hub_download(repo_id=repo, filename=remote)
        dst = dest_path / local
        if not dst.exists():
            shutil.copy2(src, dst)
            print(f"  saved {dst}")
        else:
            print(f"  exists {dst}")

    onnx_ext = onnx_file + "_data"
    if onnx_ext in files:
        src = hf_hub_download(repo_id=repo, filename=onnx_ext)
        dst = dest_path / "model.onnx_data"
        if not dst.exists():
            shutil.copy2(src, dst)
            print(f"  saved {dst}")
        else:
            print(f"  exists {dst}")

    return dest_path


if __name__ == "__main__":
    repo_arg = sys.argv[1] if len(sys.argv) > 1 else "Xenova/bge-small-en-v1.5"
    download(repo_arg)
