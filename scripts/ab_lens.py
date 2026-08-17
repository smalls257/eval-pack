#!/usr/bin/env python3
# scripts/ab_lens.py
"""Prep + size an A/B for a skeleton lens: build skeleton + report ingest sizes.
The verdict comparison is run by dispatching the lens against each transcript path this prints."""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_views  # noqa

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", type=Path)   # raw full transcript.jsonl (has turnId)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--tool-result-trunc-len", type=int, default=400)
    args = ap.parse_args(argv)
    build_views.main([str(args.transcript), str(args.out_dir), "skeleton",
                      "--tool-result-trunc-len", str(args.tool_result_trunc_len)])
    raw = args.transcript.stat().st_size
    skel = (args.out_dir / "skeleton.jsonl").stat().st_size
    print("FULL  bytes={:,}  ~tokens={:,}".format(raw, raw//4))
    print("SKEL  bytes={:,}  ~tokens={:,}  ({:.1f}x smaller)".format(skel, skel//4, raw/skel))
    print("A/B: dispatch verification-rigor twice —")
    print("  full:     TRANSCRIPT={}".format(args.transcript))
    print("  skeleton: TRANSCRIPT={}/skeleton.jsonl  RAW_TRANSCRIPT={}".format(args.out_dir, args.transcript))
    return 0

if __name__ == "__main__":
    sys.exit(main())
