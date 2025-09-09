# src/retrieve.py
from __future__ import annotations
import pathlib
from typing import List, Tuple
import numpy as np
import orjson
from sentence_transformers import SentenceTransformer

# Detect FAISS
_FAISS_AVAILABLE = True
try:
    import faiss  # type: ignore
except Exception:
    _FAISS_AVAILABLE = False

from sklearn.neighbors import NearestNeighbors
import joblib

DATA = pathlib.Path("data")
CARDS = DATA / "cards.jsonl"
EMB_NPY = DATA / "embeddings.npy"
NAMES_JSON = DATA / "embeddings.names"
FAISS_IDX = DATA / "embeddings.faiss"
SK_IDX_PKL = DATA / "embeddings_sklearn.pkl"

MODEL_NAME = "intfloat/e5-small-v2"

# Load once
_cards = [orjson.loads(line) for line in CARDS.read_bytes().splitlines()]
_name_to_card = {c["name"]: c for c in _cards}
_names: List[str] = orjson.loads(NAMES_JSON.read_bytes())
_embs = np.load(EMB_NPY)

_model = SentenceTransformer(MODEL_NAME)

# Choose index
_faiss = None
_sklearn_nn: NearestNeighbors | None = None
if _FAISS_AVAILABLE and FAISS_IDX.exists():
    _faiss = faiss.read_index(str(FAISS_IDX))
elif SK_IDX_PKL.exists():
    _sklearn_nn = joblib.load(SK_IDX_PKL)
else:
    raise SystemExit("No index found. Run: python src/index.py")

def _cosine_search_sklearn(qvec: np.ndarray, k: int):
    # sklearn returns distances (0..2 for cosine), convert to similarity: 1 - dist
    dists, idxs = _sklearn_nn.kneighbors(qvec, n_neighbors=k, return_distance=True)
    sims = 1.0 - dists[0]
    return list(zip(idxs[0], sims))

def search(query: str, k: int = 15) -> List[Tuple[dict, float]]:
    q = _model.encode([query], normalize_embeddings=True)
    q = q.astype("float32")
    results: List[Tuple[dict, float]] = []

    if _faiss is not None:
        D, I = _faiss.search(q, k)
        for idx, sim in zip(I[0], D[0]):
            name = _names[int(idx)]
            results.append((_name_to_card[name], float(sim)))
    else:
        idx_sims = _cosine_search_sklearn(q, k)
        for idx, sim in idx_sims:
            name = _names[int(idx)]
            results.append((_name_to_card[name], float(sim)))
    return results
