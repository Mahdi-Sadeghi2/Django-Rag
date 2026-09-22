"""Text embedding using a local sentence-transformers model.

Model choice (documented in README): all-MiniLM-L6-v2 — small, fast on
CPU, 384-dimensional, strong on English retrieval benchmarks, and fully
local (no API key, no cost). The same model MUST be used for both
document indexing and query embedding so they live in one vector space.
"""

from __future__ import annotations

import functools
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Must match the vector(384) column in the chunks table — a mismatch
# would make every INSERT fail on dimension check.
EMBEDDING_DIM = 384


@functools.lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Load the model once per process (lru_cache acts as a singleton).

    Loading takes seconds and ~100MB of RAM; without the cache every
    call to embed_texts would reload it, making both indexing and the
    MCP server unusably slow.
    """
    logger.info("Loading embedding model: %s", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Convert a list of texts into L2-normalized embedding vectors.

    Normalization matters: it makes cosine distance equal to the dot
    product — the fastest similarity computation, and exactly what
    pgvector's <=> operator (vector_cosine_ops) expects. All vectors
    then live on the unit sphere, so similarity is bounded in [-1, 1].

    Returns:
        float32 array of shape (len(texts), EMBEDDING_DIM).
        float32 halves storage/transmission size versus float64 with
        no practical precision loss for similarity search.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
    model = get_model()
    return model.encode(
        texts,
        batch_size=64,            # good CPU throughput/memory trade-off
        show_progress_bar=False,  # server context: keep logs clean
        normalize_embeddings=True,
    ).astype(np.float32)
