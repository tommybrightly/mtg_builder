# src/shortlist.py
from typing import List, Dict, Callable
from .rules import within_ci, bucket_of, is_creature

def shortlist(cmdr, pool: List[dict], bucket: str, k: int) -> List[dict]:
    ci = cmdr.get("color_identity") or []
    def ok(c):
        if not within_ci(c, ci): return False
        if bucket == "creatures": return is_creature(c)
        return bucket_of(c) == bucket
    cands = [c for c in pool if ok(c)]
    # score: prefer lower cmc mildly + tiny boost for on-theme keywords
    import math
    theme = (cmdr["name"] + " " + (cmdr.get("oracle_text") or "")).lower()
    def score(c):
        cmc = float(c.get("cmc") or 10.0)
        txt = (c.get("oracle_text") or "").lower()
        boost = 0
        if "angel" in txt or "demon" in txt or "dragon" in txt: boost += 1.0
        if any(w in txt for w in ["haste","flying","cheat","attack"]): boost += 0.2
        return -cmc + boost
    cands.sort(key=score, reverse=True)
    # keep unique names
    seen=set(); out=[]
    for c in cands:
        if c["name"] in seen: continue
        seen.add(c["name"]); out.append(c)
        if len(out) >= k: break
    return out
