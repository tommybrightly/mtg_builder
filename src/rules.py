# src/rules.py
from typing import List, Dict

DEFAULT_BUCKET_TARGETS = {
    "lands": 37,
    "ramp": 10,
    "draw": 10,
    "removal": 9,
    "interaction": 5,
    "finishers": 2,  # not used heavily in this minimal v1
}

def within_color_identity(card, commander_ci):
    ci = set(commander_ci or [])
    return set(card.get("color_identity") or []).issubset(ci)

def legal_in_commander(card):
    return (card.get("is_commander_legal", True) is True)

def bucket_of(card):
    """Very simple bucket from tags/type_line."""
    tl = (card.get("type_line") or "")
    tags = set(card.get("tags") or [])
    if "Land" in tl:
        return "lands"
    if "ramp" in tags:
        return "ramp"
    if "draw" in tags:
        return "draw"
    if "removal" in tags:
        return "removal"
    if "interaction" in tags:
        return "interaction"
    return None

def average_cmc(cards):
    vals = [c.get("cmc") for c in cards if isinstance(c.get("cmc"), (int, float))]
    return (sum(vals) / len(vals)) if vals else 0.0
