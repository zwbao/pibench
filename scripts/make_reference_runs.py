"""Run the deterministic baseline and oracle across the eval seeds and dump their
summaries to paper/refs.json (baseline + oracle reference rows for the leaderboard),
AND emit schema-correct run dirs so the analysis/rendering pipeline can be tested
end-to-end before LLM results land.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from pibench.api import LabAPI
from pibench.baseline import BaselineConfig
from pibench.world import World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS = [101, 102, 103]
EVAL_SEEDS = [101, 102, 103, 104, 105, 106, 107, 108]


def run_capture(seed, play):
    w = World(seed)
    play(w)
    return w


def baseline_play(w):
    from scripts_analyze_shim import run_baseline_on
    run_baseline_on(LabAPI(w), w, BaselineConfig())


def summarize(rows):
    imp = [r["impact"] for r in rows]
    return dict(impact_mean=round(float(np.mean(imp)), 1),
                impact_median=round(float(np.median(imp)), 1),
                collapsed=sum(r["collapsed"] for r in rows), n=len(rows),
                pubs=round(float(np.mean([r["publications"] for r in rows])), 1),
                grants=round(float(np.mean([r["grants_won"] for r in rows])), 1))


if __name__ == "__main__":
    # import the baseline loop + oracle
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import analyze as A
    import importlib.util
    spec = importlib.util.spec_from_file_location("oracle_mod",
        os.path.join(ROOT, "scripts", "oracle.py"))
    orc = importlib.util.module_from_spec(spec)
    sys.argv = ["oracle"]
    spec.loader.exec_module(orc)

    base_rows, orc_rows = [], []
    testdir = os.path.join(ROOT, "runs", "exp_ref")
    for seed in EVAL_SEEDS:
        wb = World(seed)
        A._run_baseline_on(LabAPI(wb), wb, BaselineConfig())
        base_rows.append(wb.summary())
        wo = World(seed)
        # replicate oracle loop on this world
        orc.run_oracle.__wrapped__ if hasattr(orc.run_oracle, "__wrapped__") else None
        s = orc.run_oracle(seed)
        orc_rows.append(s)

    refs = dict(baseline=summarize(base_rows), oracle=summarize(orc_rows),
                model_list=["qwen3.7-max", "qwen3.7-plus", "qwen-plus", "deepseek-v3.2",
                            "glm-5.2", "kimi-k2.6", "qwen-turbo"])
    json.dump(refs, open(os.path.join(ROOT, "paper", "refs.json"), "w"), indent=2)
    print("baseline:", refs["baseline"])
    print("oracle:", refs["oracle"])
    print("wrote paper/refs.json")
