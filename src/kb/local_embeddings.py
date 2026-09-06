# -*- coding: utf-8 -*-
"""Lazy, local BAAI/bge-m3 dense embedding adapter.

The module deliberately imports ``sentence_transformers`` only when vectors are
actually requested.  Validation commands can therefore run without downloading
the model and without a CLOVA credential.
"""
from __future__ import annotations

import math
import os
from collections.abc import Iterable, Sequence
from typing import Protocol

MODEL_LABEL = "bge-m3"
MODEL_ID = "BAAI/bge-m3"
MODEL_REVISION = "b28ce2a6fcc9c75ef1c0619575d0ec19af760082"
DIMENSION = 1024


class EmbeddingProvider(Protocol):
    """Small interface used by the vector builder and synthetic tests."""

    model_label: str
    model_id: str
    model_revision: str
    dimension: int

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...

    def token_count(self, text: str) -> int: ...


def validate_vector(vector: Sequence[float], dimension: int = DIMENSION) -> list[float]:
    values = [float(value) for value in vector]
    if len(values) != dimension:
        raise ValueError(f"임베딩 차원 {len(values)} != {dimension}")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("임베딩에 NaN 또는 무한대가 포함됨")
    norm = math.sqrt(sum(value * value for value in values))
    if not 0.999 <= norm <= 1.001:
        raise ValueError(f"정규화되지 않은 임베딩 norm={norm:.6f}")
    return values


class BgeM3Embedder:
    """SentenceTransformers-based local dense encoder.

    CPU is the safe default because the current build host exposes no NVIDIA
    runtime.  ``EMBEDDING_DEVICE`` and ``EMBEDDING_BATCH_SIZE`` may be supplied
    by an operator without changing the data contract.
    """

    model_label = MODEL_LABEL
    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    dimension = DIMENSION

    def __init__(
        self,
        *,
        device: str | None = None,
        batch_size: int | None = None,
        show_progress: bool = True,
    ) -> None:
        self.device = device or os.environ.get("EMBEDDING_DEVICE", "cpu")
        configured_batch = batch_size or int(os.environ.get("EMBEDDING_BATCH_SIZE", "8"))
        if configured_batch < 1:
            raise ValueError("EMBEDDING_BATCH_SIZE는 1 이상이어야 함")
        self.batch_size = configured_batch
        self.show_progress = show_progress
        self._encoder = None

    def _load(self):
        if self._encoder is not None:
            return self._encoder
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised on deployment host
            raise RuntimeError(
                "로컬 BGE-M3 적재에는 sentence-transformers가 필요합니다. "
                "통합 담당자가 고정 버전 의존성을 추가해야 합니다."
            ) from exc
        kwargs: dict[str, object] = {
            "revision": self.model_revision,
            "device": self.device,
        }
        if cache_folder := os.environ.get("EMBEDDING_CACHE_DIR"):
            kwargs["cache_folder"] = cache_folder
        self._encoder = SentenceTransformer(self.model_id, **kwargs)
        return self._encoder

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        normalized = [str(text).strip() for text in texts]
        if any(not text for text in normalized):
            raise ValueError("빈 문자열은 임베딩할 수 없음")
        rows = self._load().encode(
            normalized,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=self.show_progress,
        )
        return [validate_vector(row) for row in rows]

    def token_count(self, text: str) -> int:
        tokenizer = self._load().tokenizer
        encoded = tokenizer(str(text), add_special_tokens=True, truncation=False)
        return len(encoded["input_ids"])


def batched(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    if size < 1:
        raise ValueError("batch size는 1 이상이어야 함")
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]
