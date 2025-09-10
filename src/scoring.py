# src/scoring.py
from __future__ import annotations
from typing import List, Dict, Tuple
from collections import Counter
import math

BUCKET_WEIGHTS = {
    "ramp": 1.0,
    "draw": 1.0,
    "removal": 0.8,
    "interaction": 0.7,
    "finishers": 1.2,
    "lands": 1.0,
}

# target counts are provided by builder; we score deviations
def bucket_score(actual: Dict[str, int], target: Dict[str, int]) -> float:
    s = 0.0
    for b, t in target.items():
        if t <= 0: 
            continue
        a = actual.get(b, 0)
        d = abs(a - t) / max(1, t)
        s += BUCKET_WEIGHTS.get(b, 1.0) * (1.0 - min(1.0, d))  # 1 = perfect, 0 = far off
    return s / max(1, len(target))

def avg_cmc(cards: List[dict]) -> float:
    vals = [c.get("cmc") for c in cards if isinstance(c.get("cmc"), (int, float))]
    return sum(vals)/len(vals) if vals else 0.0

def curve_score(cards: List[dict]) -> float:
    # Heuristic: 2.2–3.2 is healthy unless ramp is high.
    a = avg_cmc(cards)
    if a == 0: 
        return 0.5
    if 2.2 <= a <= 3.2: 
        return 1.0
    # soft penalty outward
    return max(0.0, 1.0 - abs(a - 2.7)/1.5)

def tag_counter(cards: List[dict]) -> Counter:
    cc = Counter()
    for c in cards:
        for t in (c.get("tags") or []):
            cc[t] += 1
    return cc

def synergy_score(cards: List[dict], commander_tags: List[str]) -> float:
    tags = tag_counter(cards)
    if not tags: 
        return 0.5
    # reward overlap with commander-ish themes and coherent top tags
    top = tags.most_common(5)
    overlap = sum(v for k,v in top if k in set(commander_tags or []))
    diversity_penalty = max(0.0, (len(top) - overlap) * 0.05)
    raw = min(1.2, (sum(v for _,v in top) / max(1, len(cards))) * 2.0 + overlap*0.1)
    return max(0.0, min(1.0, raw - diversity_penalty))

def color_demand(cards: List[dict]) -> Dict[str, int]:
    # crude: count color identity of nonlands as demand
    need = Counter()
    for c in cards:
        if "Land" in (c.get("type_line") or ""):
            continue
        for col in c.get("color_identity") or []:
            need[col] += 1
    return dict(need)

def mana_score(deck: List[dict]) -> float:
    # rough check: if you have basics of the CI colors, call it decent
    lands = [c for c in deck if "Land" in (c.get("type_line") or "")]
    nonlands = [c for c in deck if c not in lands]
    need = color_demand(nonlands)
    have = Counter()
    for l in lands:
        n = l.get("name")
        if n in ("Forest","Island","Swamp","Mountain","Plains"):
            m = {"Forest":"G","Island":"U","Swamp":"B","Mountain":"R","Plains":"W"}[n]
            have[m] += 1
        # you could detect duals here; for now assume fine if there are any nonbasics
    basics = sum(have.values())
    if not need: 
        return 0.8
    cover = sum(min(have[k], max(1, need.get(k,0))) for k in need.keys()) / sum(max(1, v) for v in need.values())
    # clamp
    return max(0.0, min(1.0, 0.4 + 0.6*cover))

def score_deck(deck: List[dict], bucket_counts: Dict[str,int], targets: Dict[str,int], commander_tags: List[str]) -> Tuple[float, Dict[str,float]]:
    s_bucket = bucket_score(bucket_counts, targets)
    s_curve = curve_score([c for c in deck if "Land" not in (c.get("type_line") or "")])
    s_synergy = synergy_score(deck, commander_tags)
    s_mana = mana_score(deck)
    # weights tuned for sanity
    total = 0.35*s_bucket + 0.25*s_curve + 0.25*s_synergy + 0.15*s_mana
    breakdown = {"buckets": s_bucket, "curve": s_curve, "synergy": s_synergy, "mana": s_mana}
    return float(total), breakdown
