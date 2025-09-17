# src/learned_scorer.py
from __future__ import annotations
import csv, pathlib
from collections import defaultdict

DATA_DIR = pathlib.Path("data")
PPMI_PATH = DATA_DIR / "model" / "ppmi.tsv"
EDHREC_PATH = DATA_DIR / "datasets" / "edhrec_commander_cards.csv"

# Load PPMI
_ppmi = defaultdict(dict)
if PPMI_PATH.exists():
    with open(PPMI_PATH, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            c, card, v = line.rstrip("\n").split("\t")
            _ppmi[c][card] = float(v)

# Load EDHREC percents (normalize to 0..1)
_edh = defaultdict(dict)
if EDHREC_PATH.exists():
    with open(EDHREC_PATH, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            c = row["commander"]
            card = row["card"]
            try:
                p = float(row["percent"]) / 100.0
            except:
                p = 0.0
            # keep the max percent if duplicates
            if p > _edh[c].get(card, 0.0):
                _edh[c][card] = p

def score(commander_name: str, card_name: str, w_ppmi=0.7, w_pct=0.3) -> float:
    """Simple blend: PPMI + EDHREC percent. Return 0..+inf (PPMI) + [0..0.3]."""
    s1 = _ppmi.get(commander_name, {}).get(card_name, 0.0)
    s2 = _edh.get(commander_name, {}).get(card_name, 0.0)
    return w_ppmi * s1 + w_pct * s2
