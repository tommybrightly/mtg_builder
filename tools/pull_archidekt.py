#!/usr/bin/env python3
"""
Pull EDHREC JSON for a commander and write:
- data/datasets/edhrec_commander_cards.csv  (deckless frequencies)
- data/raw_edhrec/<slug>.json               (raw JSON for caching)

Usage:
  python tools/pull_edhrec.py --commander "Kaalia of the Vast"
  python tools/pull_edhrec.py --batch commanders.txt   # one commander per line
"""
import argparse, csv, json, pathlib, re, time
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_edhrec"
OUT = ROOT / "data" / "datasets" / "edhrec_commander_cards.csv"
RAW.mkdir(parents=True, exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "mtg-commander-builder/0.1 (educational; github.com/tommybrightly)"}

def slugify_commander(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)           # drop punctuation
    s = re.sub(r"\s+", "-", s.strip())       # spaces -> hyphens
    return s

def fetch_edhrec_json(commander: str) -> dict:
    slug = slugify_commander(commander)
    url = f"https://json.edhrec.com/pages/commanders/{slug}.json"
    r = requests.get(url, headers=UA, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    data = r.json()
    (RAW / f"{slug}.json").write_text(json.dumps(data), encoding="utf-8")
    return data

def parse_cards(data: dict):
    # EDHREC structure: data["container"]["json_dict"]["cardlists"] -> lists per section
    jd = (data.get("container") or {}).get("json_dict") or {}
    out = []
    for cl in jd.get("cardlists", []):
        label = cl.get("label", "")
        for c in cl.get("cards", []):
            name = c.get("name")
            sy = c.get("synergy", 0)   # relative synergy %
            pct = c.get("p", 0)        # percent of decks
            if name:
                out.append((name, pct, sy, label))
    return out

def append_rows(commander: str, rows):
    write_header = not OUT.exists()
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["commander", "card", "percent", "synergy", "section"])
        for name, pct, sy, section in rows:
            w.writerow([commander, name, pct, sy, section])

def run_one(commander: str, sleep=0.5):
    data = fetch_edhrec_json(commander)
    rows = parse_cards(data)
    append_rows(commander, rows)
    print(f"[ok] {commander}: {len(rows)} rows")
    time.sleep(sleep)

def parse_cards(data: dict):
    """
    Return rows of (name, percent, synergy, section) from EDHREC JSON.
    Handles multiple shapes: ...json_dict.cardlists[].cards|cardviews[]
    and will recursively scan if needed.
    """
    rows = []

    def add(label, card):
        # handle both {"name","p","synergy"} and nested shapes
        name = card.get("name") or card.get("card", {}).get("name")
        if not name:
            return
        # percent "p" can be number or string
        pct = card.get("p", card.get("percent", 0))
        try:
            pct = float(pct)
        except Exception:
            pct = 0.0
        # synergy can be "synergy" or "synergyScore"
        sy = card.get("synergy", card.get("synergyScore", 0))
        try:
            sy = float(sy)
        except Exception:
            sy = 0.0
        rows.append((name, pct, sy, label or ""))

    # primary path seen in most commanders
    jd = (data.get("container") or {}).get("json_dict") or {}
    cardlists = jd.get("cardlists") or []
    for cl in cardlists:
        label = cl.get("label", "")
        # variant A
        for c in cl.get("cards", []) or []:
            add(label, c)
        # variant B
        for c in cl.get("cardviews", []) or []:
            add(label, c)

    if rows:
        return rows  # got them the easy way

    # Fallback: recursively walk the JSON and harvest any dicts that look like cards
    def walk(node, current_label=""):
        if isinstance(node, dict):
            # keep track of nearest label-like field
            lbl = node.get("label", current_label)
            # candidates that look like cards
            if "name" in node and ("p" in node or "percent" in node):
                add(lbl, node)
            if "name" in node and ("synergy" in node or "synergyScore" in node):
                add(lbl, node)
            for v in node.values():
                walk(v, lbl)
        elif isinstance(node, list):
            for v in node:
                walk(v, current_label)
    walk(data)

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commander")
    ap.add_argument("--batch", help="Text file with one commander per line")
    args = ap.parse_args()

    if args.commander:
        run_one(args.commander)
    elif args.batch:
        for line in pathlib.Path(args.batch).read_text(encoding="utf-8").splitlines():
            name = line.strip()
            if name:
                try:
                    run_one(name)
                except Exception as e:
                    print(f"[warn] {name}: {e}")
    else:
        ap.error("Provide --commander or --batch")

if __name__ == "__main__":
    main()
