"""Experiment driver: models x seeds, parallel subprocesses, resumable.

Usage:
  python3 scripts/run_experiments.py --exp exp1 --models qwen-plus,qwen-turbo \
      --seeds 101,102,103 --months 60 --parallel 6
Skips (model, seed) pairs whose result.json already exists.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_one(model: str, seed: int, months: int, exp: str, max_turns: int) -> dict:
    out = os.path.join(ROOT, "runs", exp, f"{model.replace('/', '_')}_s{seed}")
    result_path = os.path.join(out, "result.json")
    if os.path.exists(result_path):
        with open(result_path) as f:
            r = json.load(f)
        return dict(model=model, seed=seed, skipped=True, impact=r.get("impact"))
    os.makedirs(out, exist_ok=True)
    logf = open(os.path.join(out, "driver.log"), "w")
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "run_agent.py"),
         "--model", model, "--seed", str(seed), "--months", str(months),
         "--max-turns", str(max_turns), "--out", out, "--quiet"],
        stdout=logf, stderr=subprocess.STDOUT, cwd=ROOT)
    logf.close()
    ok = proc.returncode == 0 and os.path.exists(result_path)
    impact = None
    if ok:
        with open(result_path) as f:
            impact = json.load(f).get("impact")
    return dict(model=model, seed=seed, ok=ok, impact=impact,
                minutes=round((time.time() - t0) / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp1")
    ap.add_argument("--models", required=True)
    ap.add_argument("--seeds", default="101,102,103")
    ap.add_argument("--months", type=int, default=60)
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--parallel", type=int, default=6)
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    seeds = [int(s) for s in args.seeds.split(",")]
    jobs = [(m, s) for m in models for s in seeds]
    print(f"{len(jobs)} runs ({len(models)} models x {len(seeds)} seeds), "
          f"parallel={args.parallel}")

    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = {ex.submit(run_one, m, s, args.months, args.exp, args.max_turns): (m, s)
                for m, s in jobs}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            tag = "SKIP" if r.get("skipped") else ("ok" if r.get("ok") else "FAIL")
            print(f"[{len(results)}/{len(jobs)}] {tag} {r['model']} s{r['seed']} "
                  f"impact={r.get('impact')} ({r.get('minutes', '-')} min)", flush=True)

    agg_path = os.path.join(ROOT, "runs", args.exp, "driver_summary.json")
    with open(agg_path, "w") as f:
        json.dump(results, f, indent=2)
    print("summary ->", agg_path)
