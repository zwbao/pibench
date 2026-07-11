"""Deep variance-mechanism analysis (zero API cost, via deterministic replay).

Reconstructs every run's full world to extract the drivers of the heavy-tailed
Impact: the exogenous boom the seed makes available vs the endogenous degree to
which a model capitalizes on it (paper volume, top-paper citations) and survives
(collapse, dead-ends). Writes paper/variance.json + paper/figs/fig_variance.png.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pibench.config import TOPICS
from replay import replay

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGS = os.path.join(ROOT, "paper", "figs")
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948",
           "#e87ba4", "#eb6834", "#16a0a0", "#8a6d3b", "#6a5acd", "#c71585"]
TEXT, MUTED = "#0b0b0b", "#52514e"
plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "#d8d7d2", "font.size": 9, "axes.spines.top": False,
    "axes.spines.right": False, "figure.dpi": 150})


def analyze(exp="exp2"):
    dirs = sorted(glob.glob(os.path.join(ROOT, "runs", exp, "*_s[0-9]*")))
    by_model = {}
    boom_by_seed = {}
    rows = []
    for d in dirs:
        name = os.path.basename(d)
        if "_s" not in name or not name.rsplit("_s", 1)[1].isdigit():
            continue
        model = name.rsplit("_s", 1)[0].replace("_", "/", 1) if name.startswith(("anthropic", "openai")) else name.rsplit("_s", 1)[0]
        # fix: model dir uses '/'->'_'; recover exact model from result.json
        res = json.load(open(os.path.join(d, "result.json")))
        model = res["model"]
        seed = res["seed"]
        try:
            w = replay(model, seed, exp)
        except Exception as e:
            print("replay failed", name, e)
            continue
        # exogenous: the biggest boom the world offered (max hotness over all topics/months)
        traj = w._hot_traj[1:w.cfg.months + 1]
        boom_available = max(max(t.values()) for t in traj)
        boom_by_seed[seed] = round(boom_available, 2)
        pubs = list(w.publications.values())
        cites = sorted([p.citations for p in pubs], reverse=True)
        maxcit = cites[0] if cites else 0
        top1 = (cites[0] / sum(cites)) if cites else 0
        # boom CAPTURED: peak hotness any of the agent's published papers was exposed to
        full = w._hot_traj
        peak_captured = 0.0
        for p in pubs:
            rng = range(p.published_month, min(w.cfg.months + 1, len(full)))
            if rng:
                peak_captured = max(peak_captured, max(full[m][p.topic] for m in rng))
        rows.append(dict(
            model=model, seed=seed, impact=res["impact"], collapsed=res["collapsed"],
            pubs=len(pubs), citations=sum(cites), maxcit=maxcit, top1_share=round(top1, 2),
            boom_available=round(boom_available, 2),
            boom_captured=round(peak_captured, 2),
            deadends=len([p for p in w.projects.values() if p.status == "deadend"]),
            quit=len([s for s in w.students.values() if s.status == "quit"]),
        ))
        by_model.setdefault(model, []).append(rows[-1])
    json.dump(dict(runs=rows, boom_by_seed=boom_by_seed),
              open(os.path.join(ROOT, "paper", "variance.json"), "w"), indent=1)
    return rows, by_model, boom_by_seed


def figure(rows, order):
    idx = {m: i for i, m in enumerate(order)}
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))

    # Panel A: Impact vs the boom the agent's papers actually rode (the causal driver)
    for r in rows:
        c = PALETTE[idx.get(r["model"], 0) % len(PALETTE)]
        coll = r["collapsed"]
        ax[0].scatter(r["boom_captured"], max(1, r["impact"]), s=58, color=c,
                      marker="X" if coll else "o",
                      edgecolors="none" if coll else "white", linewidth=0.8, zorder=3)
    ax[0].set_yscale("log")
    ax[0].set_xlabel("boom captured  (peak hotness the agent's papers rode)")
    ax[0].set_ylabel("Impact (log)")
    ax[0].set_title("Impact is driven by riding a hot topic:\ncitations scale with the hotness your papers land in", fontsize=9.5)
    ax[0].grid(True, color="#eceae5", lw=0.7)

    # Panel B: on the two boom seeds, paper volume converts the boom into Impact
    boom_rows = [r for r in rows if r["boom_available"] > 2.5]
    for r in boom_rows:
        c = PALETTE[idx.get(r["model"], 0) % len(PALETTE)]
        ax[1].scatter(r["pubs"], max(1, r["impact"]), s=54, color=c,
                      marker="x" if r["collapsed"] else "o", edgecolor="white",
                      linewidth=0.8, zorder=3)
    ax[1].set_yscale("log")
    ax[1].set_xlabel("papers published (throughput)")
    ax[1].set_ylabel("Impact (log)")
    ax[1].set_title("On boom worlds, Impact is bought with volume:\nproductive labs capitalize, timid ones leave it on the table", fontsize=9.5)
    ax[1].grid(True, color="#eceae5", lw=0.7)

    # shared legend
    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=PALETTE[idx[m] % len(PALETTE)],
                          markersize=7, label=m.split("/")[-1]) for m in order]
    handles.append(plt.Line2D([0], [0], marker="x", color=MUTED, linestyle="", markersize=7, label="collapsed"))
    fig.legend(handles=handles, loc="lower center", ncol=7, frameon=False, fontsize=7.2,
               bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_variance.png"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    rows, by_model, boom = analyze()
    order = [m for m, _ in sorted(by_model.items(),
             key=lambda kv: -np.mean([r["impact"] for r in kv[1]]))]
    figure(rows, order)
    print("boom available by seed (exogenous):", boom)
    print(f"\n{'model':30s} {'impact(3seeds)':>18s} {'pubs':>10s} {'maxcit':>10s} {'collapse'}")
    for m in order:
        rr = by_model[m]
        imps = "/".join(f"{r['impact']:.0f}" for r in sorted(rr, key=lambda r: -r["impact"]))
        pubs = "/".join(str(r["pubs"]) for r in sorted(rr, key=lambda r: -r["impact"]))
        mx = "/".join(str(r["maxcit"]) for r in sorted(rr, key=lambda r: -r["impact"]))
        coll = sum(r["collapsed"] for r in rr)
        print(f"{m:30s} {imps:>18s} {pubs:>10s} {mx:>10s}  {coll}/3")
    print("\nwrote paper/variance.json + paper/figs/fig_variance.png")
