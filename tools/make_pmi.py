#!/usr/bin/env python3
import argparse, csv, math, pathlib
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]

def parse_args():
    ap = argparse.ArgumentParser(description="Build a simple (commander, card) PPMI table from EDHREC CSV.")
    ap.add_argument("--src", default=str(ROOT / "data" / "datasets" / "edhrec_commander_cards.csv"),
                    help="Path to edhrec_commander_cards.csv")
    ap.add_argument("--out", default=str(ROOT / "data" / "model"),
                    help="Output directory (ppmi.tsv, marginals.tsv)")
    ap.add_argument("--top-k-per-commander", type=int, default=400,
                    help="Keep top-K cards per commander by percent before counting")
    ap.add_argument("--min-commanders-per-card", type=int, default=5,
                    help="Only keep cards that appear with >= this many commanders")
    ap.add_argument("--smooth", type=float, default=1.0, help="Additive smoothing for PMI")
    return ap.parse_args()

def read_rows(src_path: pathlib.Path):
    """
    Robust CSV reader:
    - Handles UTF-8 BOM
    - Case/space-insensitive headers (Commander/commanders/etc.)
    - Accepts percent/synergy under several aliases
    """
    rows = []
    if not src_path.exists():
        print(f"[warn] Source not found: {src_path}")
        return rows

    # candidate header names (lowercased & stripped)
    WANT = {
        "commander": ["commander", "cmdr", "commander_name"],
        "card": ["card", "name", "card_name"],
        "percent": ["percent", "p", "%", "pct"],
        "synergy": ["synergy", "synergy_score", "sy"],
    }

    with open(src_path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            print("[warn] CSV has no header row?")
            return rows

        # Normalize header map: lower+strip → original
        headers = { (h or "").strip().lower(): h for h in r.fieldnames }

        def pick(col_aliases):
            for alias in col_aliases:
                if alias in headers:
                    return headers[alias]
            return None

        COL_CMD = pick(WANT["commander"])
        COL_CARD = pick(WANT["card"])
        COL_PCT  = pick(WANT["percent"])
        COL_SYN  = pick(WANT["synergy"])  # optional

        if not (COL_CMD and COL_CARD and COL_PCT):
            print("[warn] Could not find required columns.")
            print("       Detected headers:", r.fieldnames)
            print("       Need commander/card/percent (any common alias).")
            return rows

        for row in r:
            c = (row.get(COL_CMD) or "").strip()
            x = (row.get(COL_CARD) or "").strip()
            if not c or not x:
                continue
            # Guard against a duplicated header line in the middle
            if c.lower() == "commander" and x.lower() == "card":
                continue

            raw_pct = (row.get(COL_PCT) or "").strip()
            raw_pct = raw_pct.replace(",", "")  # just in case
            try:
                pct = float(raw_pct)
            except Exception:
                pct = 0.0

            # synergy is optional; we don't actually use it in PMI here
            rows.append((c, x, pct))

    return rows


def build_counts(rows, top_k_per_commander: int):
    perC = defaultdict(list)
    for c, card, pct in rows:
        perC[c].append((card, pct))
    for c in perC:
        perC[c].sort(key=lambda t: t[1], reverse=True)
        perC[c] = perC[c][:top_k_per_commander]

    Ncx = Counter()
    Nc = Counter()
    Nx = Counter()
    for c, items in perC.items():
        seen = set()
        for card, _pct in items:
            if card in seen: 
                continue
            Ncx[(c, card)] += 1
            Nc[c] += 1
            Nx[card] += 1
            seen.add(card)
    return Ncx, Nc, Nx

def compute_ppmi(Ncx, Nc, Nx, min_cmd_per_card: int, smooth: float):
    keep_cards = {x for x, k in Nx.items() if k >= min_cmd_per_card}
    N = sum(Nc.values()) + smooth
    ppmi = {}
    for (c, x), cx in Ncx.items():
        if x not in keep_cards:
            continue
        cx_s = cx + smooth
        c_s = Nc[c] + smooth
        x_s = Nx[x] + smooth
        p_cx = cx_s / N
        p_c = c_s / N
        p_x = x_s / N
        val = math.log(p_cx / (p_c * p_x))
        if val < 0:
            val = 0.0
        ppmi[(c, x)] = val
    return ppmi, keep_cards

def write_outputs(out_dir: pathlib.Path, ppmi, Nc, Nx):
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv = out_dir / "ppmi.tsv"
    with open(tsv, "w", encoding="utf-8", newline="") as f:
        f.write("commander\tcard\tppmi\n")
        for (c, x), v in sorted(ppmi.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])):
            f.write(f"{c}\t{x}\t{v:.6f}\n")
    marg = out_dir / "marginals.tsv"
    with open(marg, "w", encoding="utf-8", newline="") as f:
        f.write("type\tname\tcount\n")
        for c, v in Nc.items():
            f.write(f"commander\t{c}\t{v}\n")
        for x, v in Nx.items():
            f.write(f"card\t{x}\t{v}\n")
    print(f"[ok] wrote {tsv}")
    print(f"[ok] wrote {marg}")

def main():
    args = parse_args()
    src = pathlib.Path(args.src)
    out_dir = pathlib.Path(args.out)
    print(f"[info] reading: {src}")
    rows = read_rows(src)
    if not rows:
        print("[warn] no rows found; did you run tools/pull_edhrec.py yet?")
        print("       Or check that you're running from the repo root, or pass --src with the correct path.")
        return
    uniq_cmdrs = len({c for c, _, _ in rows})
    uniq_cards = len({x for _, x, _ in rows})
    print(f"[info] rows: {len(rows)}  commanders: {uniq_cmdrs}  cards: {uniq_cards}")

    Ncx, Nc, Nx = build_counts(rows, top_k_per_commander=args.top_k_per_commander)
    print(f"[info] co-occurrences kept: {len(Ncx)}  (after top-{args.top_k_per_commander}/commander)")
    print(f"[info] commanders counted: {len(Nc)}  unique cards counted: {len(Nx)}")

    ppmi, kept_cards = compute_ppmi(Ncx, Nc, Nx, args.min_commanders_per_card, args.smooth)
    print(f"[info] PPMI pairs: {len(ppmi)}  cards passing min {args.min_commanders_per_card} commanders: {len(kept_cards)}")

    write_outputs(out_dir, ppmi, Nc, Nx)

if __name__ == "__main__":
    main()
