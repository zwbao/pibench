"""Ablations that isolate which world mechanics create the difficulty.

We run the tuned rule-based baseline (deterministic, no LLM) across seeds under
config variants that switch off one source of difficulty at a time, and also vary
the horizon. Each variant reports mean Impact and collapse rate. This mirrors
CEO-Bench's difficulty-knob ablations but on the mechanics unique to PI-Bench.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from pibench.api import LabAPI
from pibench.baseline import BaselineConfig, run_baseline
from pibench.config import POOLS, WorldConfig
from pibench.world import World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_SEEDS = [101, 102, 103, 104, 105, 106, 107, 108]


def base_cfg(**over) -> WorldConfig:
    c = WorldConfig()
    for k, v in over.items():
        setattr(c, k, v)
    return c


def run_variant(cfg_over: dict, months=60, mutate=None) -> list:
    """Run the baseline policy under a config variant across seeds."""
    out = []
    for s in EVAL_SEEDS:
        c = base_cfg(months=months, **cfg_over)
        if mutate:
            mutate(c)
        # run_baseline builds its own World; we replicate it with a custom cfg
        w = World(s, c)
        api = LabAPI(w)
        _play_baseline(api, w)
        out.append(w.summary())
    return out


def _play_baseline(api, w):
    """Authoritative baseline policy (no duplicated logic)."""
    from pibench.baseline import play_baseline
    play_baseline(api, w)


def _play_ambitious(api, w, mentor_hours=6.0):
    """An aggressive PI: hire to 8, tier-3 projects, heavy mentoring, many proposals.
    This policy genuinely competes for the 100h attention budget, so the attention
    ablation bites here even though it does not for the conservative baseline."""
    from pibench.baseline import hottest_topic, _safe
    while not w.finished:
        m = w.month
        if m % 12 == 1:
            active = [s for s in api.students.list() if s["status"] == "active"]
            want = max(0, 8 - len(active))
            apps = sorted(api.recruit.applicants(),
                          key=lambda a: -(a["transcript"] + a["letter"]))
            _safe(api.recruit.interview, [a["id"] for a in apps[:want + 2]])
            for a in apps[:want + 1]:
                _safe(api.recruit.offer, a["id"])
        active = [s for s in api.students.list() if s["status"] == "active"]
        if active:
            _safe(api.students.set_mentoring, {s["id"]: mentor_hours for s in active})
        proj = [p for p in api.projects.list() if p["status"] == "active"]
        busy = {sid for p in proj for sid in p["members"]}
        idle = [s["id"] for s in active if s["id"] not in busy]
        topic = hottest_topic(api, "reasoning")
        for i in range(0, len(idle), 2):
            _safe(api.projects.start, topic, 3, idle[i:i + 2], 2500)
        for d in api.papers.drafts():
            if d["status"] == "available":
                _safe(api.papers.polish, d["id"], 10)
                rej = {s["venue"] for s in api.papers.submissions()
                       if s["draft"] == d["id"] and s["status"] == "reject"}
                for v in [x for x in ["NAIC", "CLAR", "W-SHOP"] if x not in rej] or ["W-SHOP"]:
                    if _safe(api.papers.submit, d["id"], v):
                        break
        pubs = api.papers.publications()
        for call in api.grants.calls():
            evid = [p["id"] for p in pubs][:4]
            _safe(api.grants.propose, call["id"], topic, 25, evid)
        for e in api.events.pending():
            _safe(api.events.respond, e["id"],
                  "support" if e["kind"] == "student_crisis" else "accept")
        api.time.next_month()


def run_ambitious(cfg_over, months=60):
    out = []
    for s in EVAL_SEEDS:
        w = World(s, base_cfg(months=months, **cfg_over))
        _play_ambitious(LabAPI(w), w)
        out.append(w.summary())
    return out


def summarize(name, rows):
    imp = [r["impact"] for r in rows]
    coll = sum(r["collapsed"] for r in rows)
    return dict(variant=name, impact_mean=round(float(np.mean(imp)), 1),
                impact_median=round(float(np.median(imp)), 1),
                collapsed=coll, n=len(rows),
                pubs=round(float(np.mean([r["publications"] for r in rows])), 1),
                grants=round(float(np.mean([r["grants_won"] for r in rows])), 1))


if __name__ == "__main__":
    results = []
    print("Running deterministic ablations (baseline policy, %d seeds)...\n" % len(EVAL_SEEDS))

    # default
    results.append(summarize("default (60mo)", run_variant({})))
    # frozen field: no drift, no booms/busts -> stationary world
    results.append(summarize("no non-stationarity",
                             run_variant(dict(hot_ou_sigma=0.0, p_boom=0.0, p_bust=0.0))))
    # no scooping pressure
    results.append(summarize("no scooping", run_variant(dict(scoop_base=0.0))))
    # unlimited attention (money-only, like a single-resource sim)
    results.append(summarize("unlimited attention",
                             run_variant(dict(attention_budget=1e6, service_tax_hours=0.0))))
    # short horizon
    results.append(summarize("short horizon (12mo)", run_variant({}, months=12)))
    results.append(summarize("mid horizon (30mo)", run_variant({}, months=30)))

    # attention constraint: the dual-resource point only bites an AMBITIOUS lab
    results.append(summarize("ambitious, 100h attention", run_ambitious({})))
    results.append(summarize("ambitious, unlimited attention",
                             run_ambitious(dict(attention_budget=1e6, service_tax_hours=0.0))))

    print(f"{'variant':24s} {'impact_mean':>12s} {'median':>8s} {'collapsed':>10s} "
          f"{'pubs':>6s} {'grants':>7s}")
    for r in results:
        print(f"{r['variant']:24s} {r['impact_mean']:12.1f} {r['impact_median']:8.1f} "
              f"{r['collapsed']:>7d}/{r['n']} {r['pubs']:6.1f} {r['grants']:7.1f}")
    json.dump(results, open(os.path.join(ROOT, "paper", "ablations.json"), "w"), indent=2)
    print("\nsaved -> paper/ablations.json")
