#!/usr/bin/env python3
"""Fail CI when no evaluated retrieval configuration meets the quality floor."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("results", type=Path)
parser.add_argument("--min-hit-rate", type=float, default=0.9)
parser.add_argument("--min-mrr", type=float, default=0.75)
args = parser.parse_args()
results = json.loads(args.results.read_text(encoding="utf-8"))
passing = [
    result for result in results
    if result["metrics"]["hit_rate_at_k"] >= args.min_hit_rate
    and result["metrics"]["mrr_at_k"] >= args.min_mrr
]
if not passing:
    raise SystemExit(
        f"Quality gate failed: hit_rate>={args.min_hit_rate}, MRR>={args.min_mrr}"
    )
print(f"Quality gate passed with {len(passing)}/{len(results)} configurations")
