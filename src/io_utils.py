# src/io_utils.py
import json, os
from typing import List

def load_pool(path="data/pool.json") -> List[dict]:
    return json.load(open(path,"r",encoding="utf-8"))

def write_decklist(commander_name: str, cards: list, out_dir="data"):
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in ("-","_") else "_" for ch in commander_name)
    deck_path = os.path.join(out_dir, f"deck_{safe}.txt")
    with open(deck_path,"w",encoding="utf-8") as f:
        for c in cards:
            f.write(f"1 {c['name']}\n")
    return deck_path

def write_explanations(commander_name: str, content: str, out_dir="data"):
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in ("-","_") else "_" for ch in commander_name)
    path = os.path.join(out_dir, f"deck_{safe}_explanations.md")
    open(path,"w",encoding="utf-8").write(content)
    return path
