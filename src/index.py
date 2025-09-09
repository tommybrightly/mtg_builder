# src/index.py
from __future__ import annotations
import pathlib
from typing import List
import orjson
import numpy as np

from sentence_transformers import SentenceTransformer

# Try FAISS first; if unavailable, we'll fall back later.
_FAISS_AVAILABLE = True
try:
    import faiss  # type: ignore
except Exception:
    _FAISS_AVAILABLE = False

# Fallback ANN (scikit-learn)
from sklearn.neighbors import NearestNeighbors
import joblib

DATA = pathlib.Path("data")
CARDS = DATA / "cards.jsonl"

EMB_NPY = DATA / "embeddings.npy"
NAMES_JSON = DATA / "embeddings.names"        # stores list of names as JSON
FAISS_IDX = DATA / "embeddings.faiss"         # if FAISS is used
SK_IDX_PKL = DATA / "embeddings_sklearn.pkl"  # if sklearn is used

MODEL_NAME = "intfloat/e5-small-v2"  # fast, solid embeddings


def load_cards() -> List[dict]:
    raw = CARDS.read_bytes().splitlines()
    return [orjson.loads(line) for line in raw]


def blob(c: dict) -> str:
    name = c.get("name", "")
    tl = c.get("type_line", "") or ""
    ot = c.get("oracle_text", "") or ""
    tg = ",".join(c.get("tags", []) or [])
    return f"{name} | {tl} | {ot} | tags:{tg}"


def build():
    assert CARDS.exists(), "data/cards.jsonl not found. Run ingest.py first."

    cards = load_cards()
    texts = [blob(c) for c in cards]
    names = [c["name"] for c in cards]

    print(f"[index] loading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print("[index] encoding cards -> embeddings...")
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    embs = np.asarray(embs, dtype="float32")

    # Save common artifacts
    np.save(EMB_NPY, embs)
    NAMES_JSON.write_bytes(orjson.dumps(names))

    if _FAISS_AVAILABLE:
        print("[index] building FAISS (cosine via inner product on normalized vectors)")
        index = faiss.IndexFlatIP(embs.shape[1])
        index.add(embs)
        faiss.write_index(index, str(FAISS_IDX))
        if SK_IDX_PKL.exists():
            SK_IDX_PKL.unlink(missing_ok=True)
        print(f"[index] wrote {FAISS_IDX}")
    else:
        print("[index] FAISS not available; using scikit-learn NearestNeighbors (cosine).")
        nn = NearestNeighbors(metric="cosine", algorithm="brute")
        nn.fit(embs)
        joblib.dump(nn, SK_IDX_PKL)
        if FAISS_IDX.exists():
            FAISS_IDX.unlink(missing_ok=True)
        print(f"[index] wrote {SK_IDX_PKL}")

    print(f"[index] wrote {EMB_NPY}")
    print(f"[index] wrote {NAMES_JSON}")
    print(f"[index] cards: {len(cards)} | dim: {embs.shape[1]}")


if __name__ == "__main__":
    build()
