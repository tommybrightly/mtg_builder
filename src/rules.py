# src/rules.py
from typing import List, Dict

BUCKETS = ["creatures","ramp","draw","removal","interaction","finishers"]
TARGETS = {"lands": 36, "creatures": 28, "ramp": 10, "draw": 10, "removal": 8, "interaction": 4, "finishers": 2}

def within_ci(card, commander_ci):
    return set(card.get("color_identity") or []).issubset(set(commander_ci or []))

def is_creature(c): return "Creature" in (c.get("type_line") or "")
def is_land(c):     return "Land" in (c.get("type_line") or "")

def bucket_of(c):
    txt = (c.get("oracle_text") or "").lower()
    tl  = (c.get("type_line") or "")
    if is_land(c): return "lands"
    if "Creature" in tl: return "creatures"
    if "add {": return "ramp"
    if "mana" in txt and ("artifact" in tl or "ramp" in txt): return "ramp"
    if "draw a card" in txt or "card draw" in txt: return "draw"
    if "destroy target" in txt or "exile target" in txt: return "removal"
    if "counter target" in txt or "hexproof until end" in txt: return "interaction"
    return None

def desired_land_count(avg_cmc: float, ramp_count: int) -> int:
    base = 36
    if avg_cmc >= 3.4: base += 2
    if avg_cmc <= 2.6: base -= 2
    if ramp_count >= 10: base -= 2
    elif ramp_count <= 6: base += 2
    return max(32, min(39, base))
