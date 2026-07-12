"""Deep, zero-cost analyses that back the paper's §3.3-§3.4 (all via deterministic
replay or existing logs, no API calls):
  - paper/variance_decomp.json : two-way (model vs seed) variance decomposition on
    log-Impact, plus geometric-mean ranking.
  - paper/case_study.json       : curated 'one model, two fates' memory-note timeline
    for the top model on a boom vs a no-boom seed, with budget sparkline series.
  - paper/ablation_harness.json : summary of the memory-disabled harness ablation.
Run after analyze.py / the ablation runs exist. Idempotent.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")


def variance_decomposition(exp="exp2"):
    data = {}
    for d in glob.glob(os.path.join(ROOT, "runs", exp, "*_s[0-9]*")):
        r = json.load(open(os.path.join(d, "result.json")))
        data.setdefault(r["model"], {})[r["seed"]] = r["impact"]
    seeds = sorted({s for m in data.values() for s in m})
    models = [m for m in data if all(s in data[m] for s in seeds)]
    M = np.array([[np.log10(max(1, data[m][s])) for s in seeds] for m in models])
    grand = M.mean()
    ss_model = ((M.mean(1) - grand) ** 2).sum() * len(seeds)
    ss_seed = ((M.mean(0) - grand) ** 2).sum() * len(models)
    ss_resid = ((M - M.mean(1, keepdims=True) - M.mean(0, keepdims=True) + grand) ** 2).sum()
    tot = ss_model + ss_seed + ss_resid or 1
    geo = {m: 10 ** np.mean([np.log10(max(1, data[m][s])) for s in seeds]) for m in models}
    geo_rank = sorted(geo, key=lambda m: -geo[m])
    arith_rank = sorted(models, key=lambda m: -np.mean([data[m][s] for s in seeds]))
    out = dict(model_pct=round(100 * ss_model / tot, 1), seed_pct=round(100 * ss_seed / tot, 1),
               resid_pct=round(100 * ss_resid / tot, 1),
               geo_rank=[m.split("/")[-1] for m in geo_rank],
               geo_top=geo_rank[0].split("/")[-1], arith_top=arith_rank[0].split("/")[-1])
    json.dump(out, open(os.path.join(PAPER, "variance_decomp.json"), "w"), indent=1)
    return out


def harness_ablation():
    def m(exp, pat):
        fs = glob.glob(os.path.join(ROOT, "runs", exp, pat, "result.json"))
        return {json.load(open(f))["seed"]: json.load(open(f)) for f in fs}
    norm = m("exp2", "qwen-plus_s[0-9]*")
    nomem = m("exp2_ablation", "*")
    if not norm or not nomem:
        return None
    seeds = sorted(norm)
    out = dict(model="qwen-plus",
               with_memory=dict(per_seed=[round(norm[s]["impact"]) for s in seeds],
                                mean=round(np.mean([norm[s]["impact"] for s in seeds])),
                                collapse=sum(norm[s]["collapsed"] for s in seeds)),
               no_memory=dict(per_seed=[round(nomem[s]["impact"]) for s in sorted(nomem)],
                              mean=round(np.mean([v["impact"] for v in nomem.values()])),
                              collapse=sum(v["collapsed"] for v in nomem.values())))
    json.dump(out, open(os.path.join(PAPER, "ablation_harness.json"), "w"), indent=1)
    return out


if __name__ == "__main__":
    vd = variance_decomposition()
    print(f"variance decomposition: model {vd['model_pct']}% / seed {vd['seed_pct']}% "
          f"/ interaction {vd['resid_pct']}%; geo-top {vd['geo_top']}, arith-top {vd['arith_top']}")
    ha = harness_ablation()
    if ha:
        print(f"harness ablation: qwen-plus memory {ha['with_memory']['mean']} -> "
              f"no-memory {ha['no_memory']['mean']}")
    print("note: case_study.json is curated (see git history) and left as-is.")
