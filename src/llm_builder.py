# src/llm_builder.py
import json, sys, math
from typing import List
from .io_utils import load_pool, write_decklist, write_explanations
from .rules import BUCKETS, TARGETS, desired_land_count, is_land, is_creature, within_ci
from .shortlist import shortlist, bucket_of

### 0) LLM call (fill this for your provider/library)
import os, json, time, re
from dotenv import load_dotenv
from openai import OpenAI
_oai_client = None

# Load .env into environment variables
load_dotenv()

# --- Commander profile (LLM-inferred, cached) ---
import os, json, re, pathlib, hashlib
from .io_utils import load_pool
from .rules import within_ci

CACHE_DIR = pathlib.Path("data/cache/commander_profiles")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

JSON_INSTRUCTIONS = """
Return strict JSON only, no commentary. 
Format:
{
  "picks": ["Card A", "Card B", ...],   // exactly the requested number
  "explanation": "Why these were chosen",
  "win_conditions": ["Condition 1", "Condition 2"] // optional, may be empty
}
"""

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+","-", s.lower()).strip("-")

def _profile_path(name: str) -> pathlib.Path:
    return CACHE_DIR / f"{_slug(name)}.json"

def infer_commander_profile(cmdr: dict) -> dict:
    """
    Use LLM once to infer subtypes/mechanics/gameplan from this commander's
    type_line + oracle_text. Cache to data/cache/commander_profiles/.
    """
    p = _profile_path(cmdr["name"])
    if p.exists():
        try:
            return json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            pass

    type_line = cmdr.get("type_line","")
    oracle = cmdr.get("oracle_text","")
    ci = "".join(cmdr.get("color_identity") or [])
    sysmsg = (
        "You are an MTG Commander analyst. Extract structured themes from a commander card. "
        "Be concise and return strict JSON."
    )
    user = f"""
    Commander: {cmdr['name']}
    Type Line: {type_line}
    Oracle Text: {oracle}
    Color Identity: {ci}

Return JSON with keys:
{{
  "preferred_subtypes": ["Angel","Demon","Dragon"],   // empty if none
  "key_mechanics": ["cheat-into-play","tokens","spellslinger","equipment","graveyard","lifegain","artifacts","+1/+1 counters", ...],
  "synergy_keywords": ["haste","flying","attack trigger","proliferate","sacrifice", ...],
  "gameplan": "1-2 sentence summary",
  "exclusions": ["things that DON'T fit, optional"]
}}
Only JSON, no prose.
"""
    out = call_llm(sysmsg, user)
    try:
        data = json.loads(out)
    except Exception:
        data = {
            "preferred_subtypes": [],
            "key_mechanics": [],
            "synergy_keywords": [],
            "gameplan": "",
            "exclusions": []
        }
    json.dump(data, open(p, "w", encoding="utf-8"))
    return data


def _get_oai():
    global _oai_client
    if _oai_client is None:
        _oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _oai_client

def _extract_json(text: str) -> str:
    # Be defensive: grab the first {...} block if the model adds extra text
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else text

def call_llm(system_msg: str, user_msg: str) -> str:
    """
    Returns a JSON string (the model is prompted to return JSON only).
    """
    client = _get_oai()
    # pick a small-but-smart model you have access to
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg + "\n\nReturn ONLY JSON."}
                ],
            )
            text = resp.choices[0].message.content
            # Ensure it's JSON
            text = _extract_json(text)
            # Validate JSON
            json.loads(text)
            return text
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(0.8 * (attempt + 1))


def llm_pick(commander: dict, bucket: str, shortlist_cards: List[dict], need: int) -> dict:
    names = [c["name"] for c in shortlist_cards]
    user = f"""
Commander: {commander['name']}  (CI: {''.join(commander.get('color_identity') or [])})
Bucket: {bucket}
You must pick EXACTLY {need} cards FROM THIS SHORTLIST ONLY (do not invent names):

Shortlist:
{json.dumps(names, ensure_ascii=False, indent=2)}


"""
    sysmsg = "You are a helpful MTG Commander deck assistant. Respect color identity and only choose from the provided shortlist."
    out = call_llm(sysmsg, user).strip()
    # robust parse
    try:
        data = json.loads(out)
        assert isinstance(data.get("picks"), list)
    except Exception:
        # fallback: pick top-N from shortlist
        data = {"picks": names[:need], "explanation": "Fallback to shortlist tops.", "win_conditions": []}
    # hard trim to shortlist & need
    allow = set(names)
    picks = [n for n in data["picks"] if n in allow][:need]
    data["picks"] = picks
    return data

# show deck composition
def _counts(buckets):
    keys = ["creatures","ramp","lands","draw","removal","interaction","finishers"]
    return {k: len(buckets.get(k, [])) for k in keys}



def build_deck(commander_name: str, pool_path="data/pool.json"):
    pool = load_pool(pool_path)
    cmdr = next((c for c in pool if c["name"] == commander_name),
                {"name": commander_name, "color_identity": [], "type_line": "Legendary Creature", "oracle_text": ""})

    # ensure commander colors if missing (you can keep your Scryfall fill here if you have it)
    if not cmdr.get("color_identity"):
        cmdr["color_identity"] = cmdr.get("color_identity", [])

    profile = infer_commander_profile(cmdr)  # <--- NEW

    used = set([cmdr["name"]])
    buckets = {b: [] for b in BUCKETS}
    explanations = []

    for b in ["creatures","ramp","draw","removal","interaction","finishers"]:
        need = TARGETS[b]
        sl = shortlist(cmdr, [c for c in pool if c["name"] not in used], b, k=max(need*4, 30), profile=profile)
        if not sl:
            continue

        # Include profile context in the user message to the LLM
        names = [c["name"] for c in sl]
        user = f"""
    Commander: {cmdr['name']} (CI: {''.join(cmdr.get('color_identity') or [])})
    Commander profile: {json.dumps(profile, ensure_ascii=False)}
    Bucket: {b}
    Pick EXACTLY {need} cards from this shortlist only:
    {json.dumps(names, ensure_ascii=False, indent=2)}
    {JSON_INSTRUCTIONS}
    """
        sysmsg = (
            "You are an MTG Commander deck assistant.\n"
            "- NEVER pick cards outside color identity (already filtered in shortlist).\n"
            "- ONLY pick from the shortlist; do not invent names.\n"
            "- Use the commander profile to prefer synergistic choices.\n"
            "- Choose creatures with high power and toughness over low power and toughness\n"
            "- Output JSON ONLY."
        )
        out = call_llm(sysmsg, user)
        try:
            data = json.loads(out)
            picks = set(data.get("picks") or [])
        except Exception:
            picks = set(names[:need])
            data = {"explanation": "Fallback to shortlist tops.", "win_conditions": []}

        chosen = [c for c in sl if c["name"] in picks][:need]
        for p in chosen: used.add(p["name"])
        buckets[b] = chosen
        if data.get("explanation"): explanations.append(f"### {b.capitalize()}\n{data['explanation']}")
        if data.get("win_conditions") and b in ("creatures","finishers"):
            explanations.append("- Win cons: " + "; ".join(data["win_conditions"]))

    # lands heuristic from curve + ramp
    nonlands = [c for b in BUCKETS if b!="lands" for c in buckets[b]]
    avg_cmc = (sum(float(c.get("cmc") or 0) for c in nonlands)/len(nonlands)) if nonlands else 2.8
    ramp_ct = len(buckets.get("ramp",[]))
    target_lands = desired_land_count(avg_cmc, ramp_ct)

    lands = [c for c in pool if is_land(c) and c["name"] not in used and within_ci(c, cmdr.get("color_identity"))]
    lands = lands[:target_lands]
    for p in lands: used.add(p["name"])
    buckets["lands"] = lands

    # flatten and top-up with best creatures/draw if under 100
    deck = [cmdr] + [c for b in BUCKETS for c in buckets.get(b,[])]
    if len(deck) < 100:
        need = 100 - len(deck)
        fillers = [c for c in pool if c["name"] not in used and not is_land(c) and within_ci(c, cmdr.get("color_identity"))]
        fillers.sort(key=lambda c: (0 if is_creature(c) else 1, float(c.get("cmc") or 10.0)))
        fillers = fillers[:need]
        deck += fillers

    # after computing `fillers` and before `deck += fillers`
    for c in fillers:
        if "Land" in (c.get("type_line") or ""):
            b = "lands"
        elif "Creature" in (c.get("type_line") or ""):
            b = "creatures"
        else:
            b = bucket_of(c) or "interaction"  # sensible default bucket for misc
        buckets[b] = buckets.get(b, []) + [c]



    # write files
    deck_path = write_decklist(cmdr["name"], deck, out_dir="data")
    exp_path  = write_explanations(cmdr["name"], "\n\n".join(explanations) or "Builder v1 explanations.", out_dir="data")

    # printing composition
    print("[comp]", _counts(buckets) | {"total": len(deck)})
    return deck_path, exp_path
    



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python -m src.llm_builder "Commander Name" [pool.json]')
        sys.exit(1)
    name = sys.argv[1]
    poolp = sys.argv[2] if len(sys.argv) >= 3 else "data/pool.json"
    dp, ep = build_deck(name, poolp)
    print()
    print(f"[ok] wrote {dp}")
    print(f"[ok] wrote {ep}")
