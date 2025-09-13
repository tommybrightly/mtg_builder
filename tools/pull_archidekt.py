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
