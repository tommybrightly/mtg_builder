# src/shortlist.py
from typing import List, Dict
from .rules import within_ci, bucket_of, is_creature

def shortlist(cmdr: dict, pool: List[dict], bucket: str, k: int, profile: dict | None = None) -> List[dict]:
    ci = cmdr.get("color_identity") or []
    def ok(c):
        if not within_ci(c, ci): return False
        if bucket == "creatures": return is_creature(c)
        return bucket_of(c) == bucket

    cands = [c for c in pool if ok(c)]
    if not cands: return []

    # profile-driven boosts (commander-agnostic)
    subtypes = set((profile or {}).get("preferred_subtypes") or [])
    mech = set((profile or {}).get("key_mechanics") or [])
    keys = set((profile or {}).get("synergy_keywords") or [])

    def score(c):
        cmc = float(c.get("cmc") or 10.0)
        tl  = (c.get("type_line") or "").lower()
        txt = (c.get("oracle_text") or "").lower()
        s = -cmc * 0.2  # mild preference for cheaper
        # subtype boost (creatures)
        if is_creature(c):
            for st in subtypes:
                if st.lower() in tl: s += 1.2
        # mechanics/keywords boost (any)
        for m in mech:
            if m.lower() in txt or m.lower() in tl: s += 0.4
        for w in keys:
            if w.lower() in txt: s += 0.25
        return s

    cands.sort(key=score, reverse=True)
    seen, out = set(), []
    for c in cands:
        if c["name"] in seen: continue
        seen.add(c["name"]); out.append(c)
        if len(out) >= k: break
    return out
