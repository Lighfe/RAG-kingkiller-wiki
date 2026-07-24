"""Local ONNX embedding inference (task 8 Part C).

Adapted from the LLM Zoomcamp course's embedder.py pattern — same
tokenizers + ONNX Runtime shape — with one correctness fix: the course's
example model (all-MiniLM-L6-v2) uses mean pooling, but bge-small-en-v1.5
was trained with CLS-token pooling (`1_Pooling/config.json` on the model
card: pooling_mode_cls_token=true, pooling_mode_mean_tokens=false) — using
mean pooling here would silently hand it worse embeddings than the model
was built for. ``pooling`` is therefore a parameter, not hardcoded.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

# BGE v1.5's own model card recommends prefixing queries (not passages)
# with this instruction for the retrieval task — asymmetric, so applied
# only on the query/question side.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# bge-small-en-v1.5's max_seq_length (sentence_bert_config.json on the
# model card) — a handful of chunks in this corpus exceed it (D05/D16:
# oversized paragraphs stay unsplit, up to 1,114 words), and the model's
# fixed 512-position embedding table hard-errors on longer input rather
# than degrading gracefully, so truncation must be explicit.
MAX_SEQ_LENGTH = 512


class Embedder:
    def __init__(self, path: str = "models/Xenova/bge-small-en-v1.5", pooling: str = "cls"):
        if pooling not in ("cls", "mean"):
            raise ValueError(f"unknown pooling mode: {pooling!r}")
        self.pooling = pooling
        path = Path(path)
        self.tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=MAX_SEQ_LENGTH)
        self.session = ort.InferenceSession(
            str(path / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.input_names = {inp.name for inp in self.session.get_inputs()}

    def encode(self, text: str, normalize: bool = True) -> np.ndarray:
        return self.encode_batch([text], normalize=normalize)[0]

    def encode_batch(self, texts: list[str], normalize: bool = True) -> np.ndarray:
        self.tokenizer.enable_padding()
        encoded = self.tokenizer.encode_batch(texts)
        feed = {}
        if "input_ids" in self.input_names:
            feed["input_ids"] = np.array([e.ids for e in encoded], dtype=np.int64)
        if "attention_mask" in self.input_names:
            feed["attention_mask"] = np.array(
                [e.attention_mask for e in encoded], dtype=np.int64
            )
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.array(
                [e.type_ids for e in encoded], dtype=np.int64
            )
        hidden = self.session.run(None, feed)[0]

        if self.pooling == "cls":
            pooled = hidden[:, 0, :]
        else:
            mask = feed["attention_mask"][..., None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1)

        if normalize:
            pooled = pooled / np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled
