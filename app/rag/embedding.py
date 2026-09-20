from __future__ import annotations

import functools
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # باید با ستون vector(384) در دیتابیس هم‌خوان باشد


@functools.lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """مدل فقط یک بار در طول عمر پروسه لود می‌شود."""
    logger.info("Loading embedding model: %s", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    """متن‌ها را به بردارهای نرمال‌شده تبدیل می‌کند.

    نرمال‌سازی باعث می‌شود فاصله‌ی cosine = ضرب داخلی شود
    (سریع‌تر و سازگار با عملگر <=> در pgvector).
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
    model = get_model()
    return model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).astype(np.float32)
