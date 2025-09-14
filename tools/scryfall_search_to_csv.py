#!/usr/bin/env python3
import csv, json, pathlib, requests, time, sys

def fetch_all(query, unique="cards", order="name"):
    url = "https://api.scryfall.com/cards/search"
    params = {"q": query, "unique": unique, "order": order}
    ua = {"User-Agent": "mtg-bulk-puller/0.1 (personal use)"}
    cards = []
    while True:
        r = requests.get(url, params=params, headers=ua, timeout=30)
        r.raise_for_status()
        data = r.json()
        cards.extend(data.get("data", []))
        if data.get("has_more"):
            url = data["next_page"]  # already includes params
            params = None
            time.sleep(0.05)
        else:
            break
    return cards

def to_csv(cards, out_path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name","scryfall_id","set","collector_number","type_line","oracle_text","color_identity"])
        for c in cards:
            w.writerow([
                c.get("name",""),
                c.get("id",""),
                c.get("set",""),
                c.get("collector_number",""),
                c.get("type_line",""),
                (c.get("oracle_text") or "").replace("\n"," "),
                "".join(c.get("color_identity") or []),
            ])

if __name__ == "__main__":
    # examples:
    #   python tools/scryfall_search_to_csv.py 't:legendary t:creature' legendary_creatures.csv
    #   python tools/scryfall_search_to_csv.py 'is:commander' commanders.csv
    q = sys.argv[1] if len(sys.argv) > 1 else "is:commander"
    out = sys.argv[2] if len(sys.argv) > 2 else "out.csv"
    cards = fetch_all(q)
    to_csv(cards, out)
    print(f"Wrote {out} with {len(cards)} rows")
