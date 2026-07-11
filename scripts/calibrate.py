"""Calibration harness: scripted policies across seeds, plus a small baseline grid
tuned on TRAIN seeds and evaluated on held-out EVAL seeds."""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from pibench.api import LabAPI
from pibench.baseline import BaselineConfig, run_baseline
from pibench.world import ApiError, World

TRAIN_SEEDS = [1001, 1002]
EVAL_SEEDS = [101, 102, 103, 104, 105]


def hire_max_no_grants(seed):
    """Pathology check: aggressive hiring, no funding -> should collapse mid-run."""
    w = World(seed)
    api = LabAPI(w)
    while not w.finished:
        if w.month % 12 == 1:
            for a in sorted(api.recruit.applicants(),
                            key=lambda a: -(a["transcript"] + a["letter"]))[:4]:
                try:
                    api.recruit.offer(a["id"])
                except ApiError:
                    break
        active = [s for s in api.students.list() if s["status"] == "active"]
        proj = [p for p in api.projects.list() if p["status"] == "active"]
        busy = {sid for p in proj for sid in p["members"]}
        idle = [s["id"] for s in active if s["id"] not in busy]
        if idle:
            try:
                api.projects.start("reasoning", 2, idle[:3], 3000)
            except ApiError:
                pass
        api.time.next_month()
    return w.summary()


def summarize(name, results):
    imp = [r["impact"] for r in results]
    surv = [r["months_survived"] for r in results]
    coll = sum(r["collapsed"] for r in results)
    print(f"{name:34s} impact mean={np.mean(imp):8.1f} min={min(imp):8.1f} "
          f"max={max(imp):8.1f} | surv={np.mean(surv):5.1f} collapsed={coll}/{len(results)} "
          f"| pubs={np.mean([r['publications'] for r in results]):.1f} "
          f"grants={np.mean([r['grants_won'] for r in results]):.1f}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("all", "patho"):
        print("== pathology policies (EVAL seeds) ==")
        summarize("hire-max-no-grants", [hire_max_no_grants(s) for s in EVAL_SEEDS])

    if which in ("all", "grid"):
        print("== baseline grid (TRAIN seeds) ==")
        grid = list(itertools.product(
            [4, 6],                 # n_target_students
            [True, False],          # use_interview
            [2, 3],                 # tier
            ["news", "fixed"],      # topic rule
        ))
        rows = []
        for n, iv, tier, rule in grid:
            cfg = BaselineConfig(n_target_students=n, use_interview=iv, tier=tier,
                                 topic_rule=rule)
            res = [run_baseline(s, cfg) for s in TRAIN_SEEDS]
            mean = np.mean([r["impact"] for r in res])
            rows.append((mean, n, iv, tier, rule))
            print(f"  n={n} interview={int(iv)} tier={tier} rule={rule:5s} "
                  f"-> mean impact {mean:8.1f} "
                  f"(collapsed {sum(r['collapsed'] for r in res)}/{len(res)})")
        rows.sort(reverse=True)
        best = rows[0]
        print(f"BEST on train: impact={best[0]:.1f} n={best[1]} interview={best[2]} "
              f"tier={best[3]} rule={best[4]}")

    if which in ("all", "eval"):
        print("== tuned baseline on EVAL seeds ==")
        # fill in the best config found by the grid above
        cfg = BaselineConfig(n_target_students=int(os.environ.get("BL_N", 5)),
                             use_interview=os.environ.get("BL_IV", "1") == "1",
                             tier=int(os.environ.get("BL_TIER", 2)),
                             topic_rule=os.environ.get("BL_RULE", "news"))
        summarize("baseline(tuned)", [run_baseline(s, cfg) for s in EVAL_SEEDS])
