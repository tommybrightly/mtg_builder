# src/explain.py
from __future__ import annotations
from typing import List, Dict
import os, json, requests

# --- Local LLM via Ollama (optional) ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b-instruct")

def _ollama_generate(prompt: str) -> str:
    try:
        r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=60)
        if r.status_code == 200:
            data = r.json()
            return data.get("response", "").strip()
    except Exception:
        pass
    return ""

# --- Fallback templated reasons (no LLM required) ---
def template_reason(card: dict, commander: dict, bucket: str) -> str:
    name = card["name"]
    ci = "".join(commander.get("color_identity") or [])
    tags = ", ".join((card.get("tags") or [])[:3]) or "utility"
    if bucket == "ramp":
        return f"{name} accelerates mana and fixes colors for {ci}, smoothing your curve."
    if bucket == "draw":
        return f"{name} provides card advantage to keep threats and answers flowing."
    if bucket == "removal":
        return f"{name} answers problematic permanents efficiently."
    if bucket == "interaction":
        return f"{name} offers stack interaction/protection to preserve your board plan."
    if bucket == "lands":
        return f"{name} supports color fixing and steady development."
    return f"{name} contributes to {tags} and overall cohesion."

def explain_card(card: dict, commander: dict, bucket: str, use_llm: bool) -> str:
    if use_llm:
        prompt = (
            "You are an EDH (Commander) advisor. In one concise sentence, explain why this pick is good for the deck.\n"
            f"Commander: {commander['name']} (CI: {''.join(commander.get('color_identity') or [])})\n"
            f"Bucket: {bucket}\n"
            f"Card: {card['name']} | {card.get('type_line','')} | {card.get('oracle_text','')}\n"
            "Constraints: Color identity respected; singleton; focus on synergy, curve, and role fit.\n"
            "Answer briefly.\n"
        )
        out = _ollama_generate(prompt)
        if out:
            return out
    return template_reason(card, commander, bucket)

# --- Win-con heuristics ---
WINCON_RULES = [
    # (predicate, label, note)
    (lambda names, tags: "Herald of Secret Streams" in names and "counters" in tags, "Unblockable Wide (+1/+1)", "Go-wide counters; finish with unblockable attacks."),
    (lambda names, tags: "Craterhoof Behemoth" in names or "Overwhelming Stampede" in names, "Overrun-style Alpha Strike", "Pump team and swing lethal."),
    (lambda names, tags: "Aetherflux Reservoir" in names, "Storm/Spellslinger Payoff", "Gain life + blast finish."),
    (lambda names, tags: "Laboratory Maniac" in names or "Jace, Wielder of Mysteries" in names, "Self-mill/Draw Out", "Win by emptying your library."),
    (lambda names, tags: "Thassa's Oracle" in names, "Oracle Win", "Demands low library or self-mill combo."),
    (lambda names, tags: "Heliod, Sun-Crowned" in names and "Walking Ballista" in names, "Heliod–Ballista", "Infinite damage with lifegain combo."),
    (lambda names, tags: "tokens" in tags and any(x in names for x in ["Parallel Lives","Doubling Season","Anointed Procession"]), "Go-Wide Tokens", "Tall token armies; swing or sac outlets."),
]

def detect_wincons(deck: List[dict]) -> List[str]:
    names = {c["name"] for c in deck}
    tags = set()
    for c in deck:
        tags.update(c.get("tags") or [])
    found = []
    for pred, label, note in WINCON_RULES:
        try:
            if pred(names, tags):
                found.append(f"{label} — {note}")
        except Exception:
            pass
    # default: if counters tag is heavy, suggest the Ezuri/Scales style line
    if not found and ("counters" in tags):
        found.append("Counters Snowball — scale creatures tall; win through combat advantage.")
    return found or ["General Value Plan — incremental advantage into combat finishers."]
