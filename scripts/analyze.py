"""Aggregate experiment runs and render paper figures.

Reads runs/<exp>/<model>_s<seed>/{result.json, monthly_stats.json, actions.json}
plus baseline/oracle trajectories computed on the fly. Writes PNGs to paper/figs/
and a leaderboard JSON to paper/leaderboard.json.
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGS = os.path.join(ROOT, "paper", "figs")

# validated categorical palette (dataviz reference, light mode), fixed slot order
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
           "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
BASELINE_COLOR = "#52514e"
TEXT = "#0b0b0b"
MUTED = "#52514e"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "#d8d7d2", "axes.labelcolor": TEXT,
    "text.color": TEXT, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "axes.titlesize": 10, "figure.dpi": 150,
})


def load_runs(exp: str) -> dict:
    """-> {model: [{result, stats, actions, seed}]}"""
    out = defaultdict(list)
    for rdir in sorted(glob.glob(os.path.join(ROOT, "runs", exp, "*_s*"))):
        rp = os.path.join(rdir, "result.json")
        if not os.path.exists(rp):
            continue
        with open(rp) as f:
            result = json.load(f)
        stats, actions, evald = [], [], None
        sp = os.path.join(rdir, "monthly_stats.json")
        ap = os.path.join(rdir, "actions.json")
        ep = os.path.join(rdir, "eval.json")
        if os.path.exists(sp):
            stats = json.load(open(sp))
        if os.path.exists(ap):
            actions = json.load(open(ap))
        if os.path.exists(ep):
            evald = json.load(open(ep))
        out[result["model"]].append(dict(result=result, stats=stats,
                                         actions=actions, eval=evald,
                                         seed=result["seed"]))
    return dict(out)


def _mentoring_return(r):
    # hidden per-researcher return to mentoring: grows more if high growth*ability and
    # low independence (dependent students benefit most from the PI's hours)
    return r["growth"] * r["ability"] * (1.0 - r["independence"])


def skill_metrics(runs: dict) -> dict:
    """Four capability axes computed from the hidden eval log (CEO-Bench Fig-12 style)."""
    out = {}
    for model, rr in runs.items():
        alloc_scores, risk_deltas, anticip, quit_rates = [], [], [], []
        for r in rr:
            ev = r.get("eval")
            if not ev:
                continue
            trait = {x["id"]: x for x in ev["researchers"]}
            # 1) mentoring allocation efficiency: share of mentoring hours going to the
            #    above-median-return researchers each month (0.5 = random, ->1 = ideal)
            for rec in ev["monthly_mentoring"]:
                ment = rec["mentoring"]
                if len(ment) < 2:
                    continue
                total_h = sum(v["hours"] for v in ment.values())
                if total_h <= 0:
                    continue
                rets = {sid: _mentoring_return(v) for sid, v in ment.items()}
                med = sorted(rets.values())[len(rets) // 2]
                top_h = sum(v["hours"] for sid, v in ment.items() if rets[sid] >= med)
                alloc_scores.append(top_h / total_h)
            # 2) risk calibration: bolder (higher tier) when the lab can afford variance
            aff = [p["tier"] for p in ev["projects"]
                   if p["runway_at_start"] > 18 and p["idle_at_start"] >= 2]
            con = [p["tier"] for p in ev["projects"]
                   if not (p["runway_at_start"] > 18 and p["idle_at_start"] >= 2)]
            if aff and con:
                risk_deltas.append(np.mean(aff) - np.mean(con))
            # 3) anticipation: did chosen topics get HOTTER after starting (foresight)
            #    vs chase already-hot topics (future_hot - hot_at_start)
            for p in ev["projects"]:
                anticip.append(p["future_hot"] - p["hot_at_start"])
            # 4) ex-ante irreversibility error: PhD hires that quit before graduating
            phds = [x for x in ev["researchers"] if x["role"] == "phd"]
            if phds:
                quit_rates.append(sum(1 for x in phds if x["status"] == "quit") / len(phds))
        out[model] = dict(
            alloc_efficiency=round(float(np.mean(alloc_scores)), 3) if alloc_scores else None,
            risk_calibration=round(float(np.mean(risk_deltas)), 3) if risk_deltas else None,
            anticipation=round(float(np.mean(anticip)), 3) if anticip else None,
            phd_early_quit_rate=round(float(np.mean(quit_rates)), 3) if quit_rates else None,
        )
    return out


def baseline_reference(seeds):
    """Mean cumulative-citation trajectory of the tuned baseline for figure overlay."""
    from pibench.api import LabAPI
    from pibench.baseline import BaselineConfig
    from pibench.world import World
    mats = []
    for s in seeds:
        w = World(s)
        _run_baseline_on(LabAPI(w), w, BaselineConfig())
        mats.append([st["citations"] for st in w.monthly_stats])
    T = max(len(x) for x in mats)
    arr = np.full((len(mats), T), np.nan)
    for i, x in enumerate(mats):
        arr[i, :len(x)] = x
        if len(x) < T:
            arr[i, len(x):] = x[-1] if x else 0
    return list(range(1, T + 1)), np.nanmean(arr, axis=0)


def _run_baseline_on(api, w, cfg):
    """Alias to the single authoritative baseline policy (pibench.baseline).
    Kept as a name so existing callers work; NO duplicated logic here."""
    from pibench.baseline import play_baseline
    play_baseline(api, w, cfg)


def leaderboard(runs: dict) -> list:
    rows = []
    for model, rr in runs.items():
        imps = [r["result"]["impact"] for r in rr]
        rows.append(dict(
            model=model, n_runs=len(rr),
            impact_mean=round(float(np.mean(imps)), 1),
            impact_per_seed={r["seed"]: r["result"]["impact"] for r in rr},
            collapsed=sum(r["result"]["collapsed"] for r in rr),
            survival_mean=round(float(np.mean(
                [r["result"]["months_survived"] for r in rr])), 1),
            pubs_mean=round(float(np.mean(
                [r["result"]["publications"] for r in rr])), 1),
            top_pubs_mean=round(float(np.mean(
                [r["result"]["top_pubs"] for r in rr])), 1),
            grants_mean=round(float(np.mean(
                [r["result"]["grants_won"] for r in rr])), 1),
            graduated_mean=round(float(np.mean(
                [r["result"]["students_graduated"] for r in rr])), 1),
            hindex_mean=round(float(np.mean(
                [r["result"]["h_index"] for r in rr])), 1),
            tokens_mean_m=round(float(np.mean(
                [(r["result"]["usage"]["prompt_tokens"]
                  + r["result"]["usage"]["completion_tokens"]) / 1e6 for r in rr])), 2),
            llm_calls_mean=round(float(np.mean(
                [r["result"]["usage"]["calls"] for r in rr])), 1),
        ))
    rows.sort(key=lambda r: -r["impact_mean"])
    return rows


def fig_trajectories(runs: dict, order: list):
    n = len(order)
    ncols = 4
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.1 * ncols, 2.5 * nrows),
                             sharex=True, sharey=True)
    axes = np.atleast_2d(axes)
    for i, model in enumerate(order):
        ax = axes[i // ncols][i % ncols]
        color = PALETTE[i % len(PALETTE)]
        for r in runs.get(model, []):
            months = [s["month"] for s in r["stats"]]
            budget = [max(100, s["budget"]) for s in r["stats"]]
            ax.plot(months, budget, color=color, lw=1.6, alpha=0.85)
            if r["result"]["collapsed"]:
                ax.plot(months[-1], budget[-1], "x", color=TEXT, ms=7, mew=1.6)
        ax.axhline(600_000, color=MUTED, lw=0.8, ls=(0, (3, 3)), alpha=0.6)
        ax.set_yscale("log")
        ax.set_title(model, color=TEXT)
        ax.grid(True, axis="y", color="#eceae5", lw=0.7)
        ax.set_ylim(100, 3e6)
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")
    for ax in axes[-1]:
        ax.set_xlabel("month")
    axes[0][0].set_ylabel("lab budget (USD, log)")
    fig.suptitle("Lab budget over time — all runs per model (× = collapse; "
                 "dashed = $600K start)", y=1.02, color=TEXT)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_budget_traj.png"), bbox_inches="tight")
    plt.close(fig)


def fig_impact(runs: dict, order: list):
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for i, model in enumerate(order):
        rr = runs.get(model, [])
        if not rr:
            continue
        # mean cumulative citations across seeds (pad collapsed runs at last value)
        T = max(len(r["stats"]) for r in rr)
        mat = np.full((len(rr), T), np.nan)
        for k, r in enumerate(rr):
            cites = [s["citations"] for s in r["stats"]]
            mat[k, :len(cites)] = cites
            if len(cites) < T:
                mat[k, len(cites):] = cites[-1] if cites else 0
        mean = np.nanmean(mat, axis=0)
        color = PALETTE[i % len(PALETTE)]
        ax.plot(range(1, T + 1), mean, color=color, lw=2.0, label=model)
        ax.annotate(model, (T, mean[-1]), xytext=(4, 0),
                    textcoords="offset points", color=color, fontsize=8,
                    va="center")
    try:
        bm, bmean = baseline_reference(sorted({r["seed"] for rr in runs.values() for r in rr}))
        ax.plot(bm, bmean, color=BASELINE_COLOR, lw=1.8, ls=(0, (4, 3)),
                label="rule-based baseline", zorder=1)
        ax.annotate("baseline", (bm[-1], bmean[-1]), xytext=(4, 0),
                    textcoords="offset points", color=BASELINE_COLOR, fontsize=8,
                    va="center")
    except Exception as e:
        print("baseline overlay skipped:", e)
    ax.set_xlabel("month")
    ax.set_ylabel("cumulative citations (mean across seeds)")
    ax.grid(True, axis="y", color="#eceae5", lw=0.7)
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    ax.set_title("Citations accumulate late — the delayed-reward structure", color=TEXT)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_impact_traj.png"), bbox_inches="tight")
    plt.close(fig)


def behavioral_metrics(runs: dict) -> dict:
    out = {}
    for model, rr in runs.items():
        acts = Counter()
        months_total = 0
        offered = 0
        offers_with_prior_interview = 0
        proposals = 0
        pubs = 0
        student_months = 0
        for r in rr:
            months_total += r["result"]["months_survived"]
            pubs += r["result"]["publications"]
            for st in r["stats"]:
                student_months += st["students"]
            # replay actions per run to detect whether each offer was preceded by an
            # interview of that same candidate in the same recruiting season
            interviewed_ids = set()
            for a in r["actions"]:
                acts[a["action"]] += 1
                if a["action"] == "recruit.interview":
                    ids = a["args"].get("ids", [])
                    interviewed_ids.update(ids if isinstance(ids, list) else [ids])
                elif a["action"] == "recruit.offer":
                    offered += 1
                    if a["args"].get("id") in interviewed_ids:
                        offers_with_prior_interview += 1
                elif a["action"] == "grants.propose":
                    proposals += 1
        total_actions = sum(v for k, v in acts.items() if k != "time.next_month")
        grants_won = sum(r["result"]["grants_won"] for r in rr)
        # topic-chasing: rank of chosen topic by CURRENT hotness at start (1=hottest)
        ranks, concs = [], []
        for r in rr:
            ev = r.get("eval")
            if not ev:
                continue
            from pibench.world import World as _W
            from pibench.config import TOPICS as _T
            traj = _W(r["seed"])._hot_traj
            topics_used = []
            for p in ev["projects"]:
                h = traj[min(p["started_month"], len(traj) - 1)]
                order_t = sorted(_T, key=lambda k: -h[k])
                ranks.append(order_t.index(p["topic"]) + 1)
                topics_used.append(p["topic"])
            if topics_used:
                from collections import Counter as _C
                concs.append(sum((v / len(topics_used))**2
                                 for v in _C(topics_used).values()))
        out[model] = dict(
            actions_per_month=round(total_actions / max(1, months_total), 2),
            action_dist=dict(acts.most_common(12)),
            interview_coverage=round(offers_with_prior_interview / max(1, offered), 2),
            n_offers=offered,
            grant_hit_rate=round(grants_won / max(1, proposals), 2),
            n_proposals=proposals,
            pubs_per_student_year=round(12 * pubs / max(1, student_months), 3),
            topic_hot_rank=round(float(np.mean(ranks)), 2) if ranks else None,
            topic_concentration=round(float(np.mean(concs)), 2) if concs else None,
        )
    return out


def export_chart_data(runs: dict, order: list):
    """Emit paper/trajectories.json for the site's web-native interactive charts:
    per-model mean cumulative-citation series over months, per-seed final Impact,
    per-model budget series, plus the baseline citation series."""
    T = 60
    series = []
    for i, model in enumerate(order):
        rr = runs.get(model, [])
        if not rr:
            continue
        cmat = np.full((len(rr), T), np.nan)
        bmat = np.full((len(rr), T), np.nan)
        for k, r in enumerate(rr):
            cites = [s["citations"] for s in r["stats"]]
            budg = [max(1.0, s["budget"]) for s in r["stats"]]
            n = min(T, len(cites))
            cmat[k, :n] = cites[:n]
            bmat[k, :n] = budg[:n]
            if n < T:
                cmat[k, n:] = cites[n - 1] if cites else 0
                bmat[k, n:] = budg[n - 1] if budg else 1
        series.append(dict(
            model=model, colorIndex=i,
            cites=[round(float(x), 1) for x in np.nanmean(cmat, axis=0)],
            budget=[round(float(x)) for x in np.nanmean(bmat, axis=0)],
            seedsImpact=sorted([r["result"]["impact"] for r in rr], reverse=True),
            collapse=sum(r["result"]["collapsed"] for r in rr),
        ))
    baseline_series = None
    try:
        bm, bmean = baseline_reference(sorted({r["seed"] for rr in runs.values() for r in rr}))
        baseline_series = [round(float(x), 1) for x in bmean]
    except Exception as e:
        print("baseline series skipped:", e)
    out = dict(months=list(range(1, T + 1)), series=series, baseline=baseline_series)
    with open(os.path.join(ROOT, "paper", "trajectories.json"), "w") as f:
        json.dump(out, f)
    print("wrote paper/trajectories.json")


def fig_skills(runs: dict, order: list, skills: dict):
    """Four capability axes (CEO-Bench Fig-12 style small multiples)."""
    axes_spec = [
        ("alloc_efficiency", "Mentoring allocation\n(share of hours to high-return students)", False, 0.5),
        ("anticipation", "Topic anticipation\n(future - current hotness at start)", False, 0.0),
        ("phd_early_quit_rate", "PhD attrition\n(share of hires that quit; lower better)", True, None),
        ("risk_calibration", "Risk calibration\n(bolder tier when affordable)", False, 0.0),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.2))
    models = [m for m in order if skills.get(m)]
    x = np.arange(len(models))
    colors = [PALETTE[order.index(m) % len(PALETTE)] for m in models]
    for ax, (key, title, lower_better, ref) in zip(axes, axes_spec):
        vals = [skills[m].get(key) or 0 for m in models]
        ax.bar(x, vals, color=colors, width=0.66, zorder=3)
        for xi, v in zip(x, vals):
            ax.annotate(f"{v:.2f}", (xi, v), ha="center",
                        va="bottom" if v >= 0 else "top", fontsize=7.5, color=TEXT)
        if ref is not None:
            ax.axhline(ref, color=MUTED, lw=0.8, ls=(0, (3, 3)))
        ax.set_xticks(x, models, rotation=40, ha="right", fontsize=7.5)
        ax.set_title(title, fontsize=9, color=TEXT)
        ax.grid(True, axis="y", color="#eceae5", lw=0.7, zorder=0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_skills.png"), bbox_inches="tight")
    plt.close(fig)


def fig_behavior(runs: dict, order: list, behav: dict):
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    models = [m for m in order if m in behav]
    x = np.arange(len(models))
    colors = [PALETTE[order.index(m) % len(PALETTE)] for m in models]

    vals = [behav[m]["actions_per_month"] for m in models]
    axes[0].bar(x, vals, color=colors, width=0.62, zorder=3)
    for xi, v in zip(x, vals):
        axes[0].annotate(f"{v:.1f}", (xi, v), ha="center", va="bottom",
                         fontsize=8, color=TEXT)
    axes[0].set_xticks(x, models, rotation=30, ha="right")
    axes[0].set_ylabel("actions / month")
    axes[0].set_title("Action intensity", color=TEXT)
    axes[0].grid(True, axis="y", color="#eceae5", lw=0.7, zorder=0)

    vals = [behav[m]["pubs_per_student_year"] for m in models]
    axes[1].bar(x, vals, color=colors, width=0.62, zorder=3)
    for xi, v in zip(x, vals):
        axes[1].annotate(f"{v:.2f}", (xi, v), ha="center", va="bottom",
                         fontsize=8, color=TEXT)
    axes[1].set_xticks(x, models, rotation=30, ha="right")
    axes[1].set_ylabel("papers per student-year")
    axes[1].set_title("Conversion: output per student-year", color=TEXT)
    axes[1].grid(True, axis="y", color="#eceae5", lw=0.7, zorder=0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_behavior.png"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp1")
    args = ap.parse_args()
    os.makedirs(FIGS, exist_ok=True)
    runs = load_runs(args.exp)
    if not runs:
        print("no runs found for", args.exp)
        sys.exit(1)
    board = leaderboard(runs)
    order = [r["model"] for r in board]
    with open(os.path.join(ROOT, "paper", "leaderboard.json"), "w") as f:
        json.dump(board, f, indent=2)
    behav = behavioral_metrics(runs)
    with open(os.path.join(ROOT, "paper", "behavior.json"), "w") as f:
        json.dump(behav, f, indent=2)
    skills = skill_metrics(runs)
    with open(os.path.join(ROOT, "paper", "skills.json"), "w") as f:
        json.dump(skills, f, indent=2)
    export_chart_data(runs, order)
    fig_trajectories(runs, order)
    fig_impact(runs, order)
    fig_behavior(runs, order, behav)
    if any(runs[m][0].get("eval") for m in runs):
        fig_skills(runs, order, skills)
    print("leaderboard:")
    for r in board:
        b = behav[r["model"]]
        print(f"  {r['model']:16s} impact={r['impact_mean']:8.1f} "
              f"collapsed={r['collapsed']}/{r['n_runs']} pubs={r['pubs_mean']:5.1f} "
              f"hot_rank={b.get('topic_hot_rank')} tokens={r['tokens_mean_m']}M")
    print("skill axes:")
    for m in order:
        s = skills.get(m, {})
        print(f"  {m:16s} alloc={s.get('alloc_efficiency')} "
              f"anticip={s.get('anticipation')} quit={s.get('phd_early_quit_rate')} "
              f"risk={s.get('risk_calibration')}")
    print("figs ->", FIGS)
