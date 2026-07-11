"""Run one PIBench episode with an LLM agent.

Usage: python3 scripts/run_agent.py --model qwen-plus --seed 101 [--months 60]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pibench.harness.llm import load_env, resolve_provider
from pibench.harness.runner import run_episode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--months", type=int, default=60)
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    env = load_env(ROOT)
    api_key, base_url = resolve_provider(args.model, env)
    out = args.out or os.path.join(
        ROOT, "runs", f"{args.model.replace('/', '_')}_s{args.seed}_{int(time.time())}")
    t0 = time.time()
    result = run_episode(
        model=args.model, seed=args.seed, out_dir=out,
        api_key=api_key, base_url=base_url,
        months=args.months, max_turns=args.max_turns,
        temperature=args.temperature, verbose=not args.quiet)
    mins = (time.time() - t0) / 60
    print(f"\nDONE in {mins:.1f} min -> {out}")
    for k in ("impact", "citations", "projected", "h_index", "publications",
              "top_pubs", "grants_won", "students_graduated", "months_survived",
              "collapsed", "final_budget"):
        print(f"  {k}: {result[k]}")
    print(f"  tokens: {result['usage']}")
