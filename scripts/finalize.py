"""One-shot final regeneration: reference rows (baseline + oracle on 3 and 8 seeds),
skill-axis + behavior analysis, figures, and the paper HTML. Run after an experiment
completes: python3 scripts/finalize.py --exp exp2
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from pibench.api import LabAPI
from pibench.baseline import BaselineConfig
from pibench.world import World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def summ(rows):
    imp = [r["impact"] for r in rows]
    return dict(impact_mean=round(float(np.mean(imp)), 1),
                impact_median=round(float(np.median(imp)), 1),
                per_seed=[r["impact"] for r in rows],
                collapsed=sum(r["collapsed"] for r in rows), n=len(rows),
                pubs=round(float(np.mean([r["publications"] for r in rows])), 1),
                grants=round(float(np.mean([r["grants_won"] for r in rows])), 1))


def compute_refs(seeds3, seeds8):
    import analyze as A
    import importlib.util
    spec = importlib.util.spec_from_file_location("orc",
        os.path.join(ROOT, "scripts", "oracle.py"))
    orc = importlib.util.module_from_spec(spec)
    sys.argv = ["orc"]
    spec.loader.exec_module(orc)

    def run(seeds):
        base, orac = [], []
        for s in seeds:
            wb = World(s)
            A._run_baseline_on(LabAPI(wb), wb, BaselineConfig())
            base.append(wb.summary())
            orac.append(orc.run_oracle(s))
        return summ(base), summ(orac)

    b3, o3 = run(seeds3)
    b8, o8 = run(seeds8)
    return dict(baseline=b3, oracle=o3, baseline_broad=b8, oracle_broad=o8,
                seeds=seeds3, broad_seeds=seeds8,
                model_list=None)  # filled by analyze from the board


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp2")
    args = ap.parse_args()
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

    print("computing reference rows (baseline + oracle)...")
    refs = compute_refs([101, 102, 103], list(range(101, 109)))
    # model_list from the leaderboard after analyze; set a sensible default now
    json.dump(refs, open(os.path.join(ROOT, "paper", "refs.json"), "w"), indent=2)
    print(f"  baseline 3-seed {refs['baseline']['impact_mean']} | 8-seed {refs['baseline_broad']['impact_mean']}")
    print(f"  oracle   3-seed {refs['oracle']['impact_mean']} | 8-seed {refs['oracle_broad']['impact_mean']}")

    print("running analysis...")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "analyze.py"),
                    "--exp", args.exp], cwd=ROOT, check=True)

    # patch model_list into refs from the freshly written leaderboard
    board = json.load(open(os.path.join(ROOT, "paper", "leaderboard.json")))
    refs["model_list"] = [r["model"] for r in board]
    json.dump(refs, open(os.path.join(ROOT, "paper", "refs.json"), "w"), indent=2)

    # deep variance analysis (replay-based) — writes variance.json + fig_variance.png
    print("variance mechanism analysis...")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "variance.py")],
                   cwd=ROOT, check=True)
    # note: variance_decomp.json, case_study.json, ablation_harness.json are produced by
    # their own analysis steps (see scripts/); regenerate them if the run set changes.

    print("deep analyses (variance decomposition, harness ablation)...")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "deep_analysis.py")],
                   cwd=ROOT, check=True)

    print("building paper...")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_paper.py")],
                   cwd=ROOT, check=True)
    print("building site...")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_site.py")],
                   cwd=ROOT, check=True)
    print("done -> paper/index.html + site/index.html")
