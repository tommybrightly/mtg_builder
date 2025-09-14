#!/usr/bin/env python3
"""
Find commanders that are missing EDHREC JSON in data/raw_edhrec/.
Optionally kick off fetching just those.

Usage:
  # just list missing and write to data/datasets/edhrec_missing.txt
  python tools/edhrec_missing.py --list --from commanders.txt

  # list and immediately fetch the missing ones (respects caching in pull_edhrec.py)
  python tools/edhrec_missing.py --fetch --from commanders.txt --sleep 1.0
"""
import argparse, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_edhrec"
OUT = ROOT / "data" / "datasets"
OUT.mkdir(parents=True, exist_ok=True)

def slugify_commander(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s

def read_names(path: pathlib.Path):
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", required=True, help="Text file with one commander per line (e.g., commanders.txt)")
    ap.add_argument("--list", action="store_true", help="Only list missing; do not fetch")
    ap.add_argument("--fetch", action="store_true", help="Fetch missing immediately via tools/pull_edhrec.py")
    ap.add_argument("--sleep", type=float, default=0.8, help="Sleep between fetches (passed through)")
    args = ap.parse_args()

    src = pathlib.Path(args.source)
    if not src.exists():
        print(f"[error] file not found: {src}")
        sys.exit(1)

    names = read_names(src)
    missing = []
    for n in names:
        slug = slugify_commander(n)
        if not (RAW / f"{slug}.json").exists():
            missing.append(n)

    missing_path = OUT / "edhrec_missing.txt"
    missing_path.write_text("\n".join(missing), encoding="utf-8")

    print(f"[ok] total commanders in list: {len(names)}")
    print(f"[ok] missing jsons: {len(missing)}")
    print(f"[ok] wrote missing list -> {missing_path}")

    if args.fetch and missing:
        # call your existing puller in batch mode using the missing file
        cmd = [sys.executable, str(ROOT / "tools" / "pull_edhrec.py"), "--batch", str(missing_path), "--sleep", str(args.sleep)]
        print(f"[run] {' '.join(cmd)}")
        res = subprocess.run(cmd, cwd=str(ROOT))
        if res.returncode != 0:
            sys.exit(res.returncode)

if __name__ == "__main__":
    main()
