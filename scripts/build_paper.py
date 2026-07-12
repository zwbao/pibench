"""Build the PI-Bench paper as a single self-contained HTML artifact.

Reads paper/leaderboard.json, behavior.json, ablations.json and the PNG figures in
paper/figs/, embeds figures as data URIs, renders the leaderboard table, and writes
paper/index.html. Design is inlined; data and prose live in this script so the page
regenerates deterministically as results land.
"""
import base64
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")


def load(name, default):
    p = os.path.join(PAPER, name)
    if os.path.exists(p):
        return json.load(open(p))
    return default


def img_data_uri(fname):
    p = os.path.join(PAPER, "figs", fname)
    if not os.path.exists(p):
        return None
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    return f"data:image/png;base64,{b64}"


def fig(fname, caption, num):
    uri = img_data_uri(fname)
    if not uri:
        return (f'<figure class="fig"><div class="fig-missing">[figure {num}: {fname} '
                f'— run analyze.py]</div><figcaption><b>Figure {num}.</b> {caption}'
                f'</figcaption></figure>')
    return (f'<figure class="fig"><img src="{uri}" alt="Figure {num}: {caption}">'
            f'<figcaption><b>Figure {num}.</b> {caption}</figcaption></figure>')


def money(x):
    return f"${x/1000:.0f}k" if abs(x) < 1e6 else f"${x/1e6:.2f}M"


def leaderboard_table(board, baseline_row, oracle_row):
    if not board:
        return '<p class="muted">[leaderboard pending experiment completion]</p>'
    head = ("<tr><th>Model</th><th class='num'>Impact (mean)</th>"
            "<th class='num'>per-seed</th><th class='num'>collapse</th>"
            "<th class='num'>pubs</th><th class='num'>top</th>"
            "<th class='num'>grants</th><th class='num'>grad</th>"
            "<th class='num'>survival</th><th class='num'>tokens</th></tr>")
    rows = []
    best = max((r["impact_mean"] for r in board), default=1) or 1
    for r in board:
        seeds = " / ".join(str(round(v)) for v in r["impact_per_seed"].values())
        bar = int(60 * r["impact_mean"] / best)
        rows.append(
            f"<tr><td class='model'>{r['model']}</td>"
            f"<td class='num impact'><span class='bar' style='--w:{bar}px'></span>"
            f"{r['impact_mean']:.0f}</td>"
            f"<td class='num tiny'>{seeds}</td>"
            f"<td class='num'>{r['collapsed']}/{r['n_runs']}</td>"
            f"<td class='num'>{r['pubs_mean']:.1f}</td>"
            f"<td class='num'>{r['top_pubs_mean']:.1f}</td>"
            f"<td class='num'>{r['grants_mean']:.1f}</td>"
            f"<td class='num'>{r['graduated_mean']:.1f}</td>"
            f"<td class='num'>{r['survival_mean']:.0f}</td>"
            f"<td class='num tiny'>{r['tokens_mean_m']:.2f}M</td></tr>")
    ref = []
    if baseline_row:
        ref.append(
            f"<tr class='ref'><td class='model'>rule-based baseline</td>"
            f"<td class='num'>{baseline_row['impact_mean']:.0f}</td>"
            f"<td class='num tiny'>—</td><td class='num'>{baseline_row['collapsed']}"
            f"/{baseline_row['n']}</td><td class='num'>{baseline_row['pubs']:.1f}</td>"
            f"<td class='num'>—</td><td class='num'>{baseline_row['grants']:.1f}</td>"
            f"<td class='num'>—</td><td class='num'>—</td><td class='num tiny'>no LLM</td></tr>")
    if oracle_row:
        ref.append(
            f"<tr class='ref'><td class='model'>oracle (informed reference)</td>"
            f"<td class='num'>{oracle_row['impact_mean']:.0f}</td>"
            f"<td class='num tiny'>—</td><td class='num'>{oracle_row['collapsed']}"
            f"/{oracle_row['n']}</td><td class='num'>{oracle_row['pubs']:.1f}</td>"
            f"<td class='num'>—</td><td class='num'>—</td><td class='num'>—</td>"
            f"<td class='num'>—</td><td class='num tiny'>full-info policy</td></tr>")
    return (f"<div class='table-wrap'><table class='board'>{head}"
            f"{''.join(rows)}{''.join(ref)}</table></div>")


def ablation_table(ab):
    if not ab:
        return '<p class="muted">[ablations pending]</p>'
    rows = []
    for r in ab:
        rows.append(f"<tr><td>{r['variant']}</td>"
                    f"<td class='num'>{r['impact_mean']:.0f}</td>"
                    f"<td class='num'>{r['impact_median']:.0f}</td>"
                    f"<td class='num'>{r['collapsed']}/{r['n']}</td>"
                    f"<td class='num'>{r['pubs']:.1f}</td></tr>")
    return ("<div class='table-wrap'><table class='board small'>"
            "<tr><th>World variant</th><th class='num'>Impact mean</th>"
            "<th class='num'>median</th><th class='num'>collapse</th>"
            "<th class='num'>pubs</th></tr>" + "".join(rows) + "</table></div>")


# ---------------------------------------------------------------- prose builders
def results_prose(board, baseline_row, oracle_row, refs=None):
    if not board:
        return "<p class='muted'>[results prose pending experiment completion]</p>"
    refs = refs or {}
    top = board[0]
    bot = board[-1]
    b = baseline_row["impact_mean"] if baseline_row else 0
    n_beat = sum(1 for r in board if baseline_row and r["impact_mean"] > b)
    orc = oracle_row["impact_mean"] if oracle_row else 0
    orc_broad = refs.get("oracle_broad", {}).get("impact_mean", orc)
    b_broad = refs.get("baseline_broad", {}).get("impact_mean", b)
    top_seeds = list(top["impact_per_seed"].values())
    orc_seeds = refs.get("oracle", {}).get("per_seed", [])
    ceil = refs.get("ceiling_per_paper", 3300)
    # everything below is stated on the SAME matched three seeds {101,102,103}
    n_beat_below = sum(1 for r in board if baseline_row and r["impact_mean"] <= b)
    return f"""<p>Table 1 summarizes the benchmark; all model, baseline, and oracle numbers
are on the same three seeds {{101, 102, 103}} (we report broader eight-seed baseline and
oracle estimates only as a stability check, clearly labelled). Impact spans a wide range —
from <b>{top['model']}</b> at {top['impact_mean']:.0f} down to {bot['model']} at
{bot['impact_mean']:.0f}, a {top['impact_mean']/max(1,bot['impact_mean']):.0f}-fold gap
between the extremes. The tiers are broad but not clean: adjacent models overlap well within
seed variance (qwen3.7-max 2091/549/132 vs gpt-5.6-sol 1997/452/370). {n_beat_below} of the
{len(board)} models fail to beat even the non-LLM baseline ({b:.0f}) on these worlds.</p>
<p><b>The scores are dominated by variance, and the variance is structure, not noise.</b>
{top['model']}'s three runs scored {', '.join(f'{round(v)}' for v in top_seeds)} — a single
seed contributes most of its average — and the privileged-information oracle shows the same
signature ({', '.join(f'{round(v)}' for v in orc_seeds)}): a boom world admits a score in the
thousands, the no-boom world barely twenty. We trace this to its mechanism in the next subsection: most of
a lab's Impact comes from catching a topic <i>boom</i>, a rare high-magnitude event, so the
payoff is heavy-tailed, much as real academic impact is; Figure 1 shows those citations arriving only in the final years. With three seeds the ranking of
adjacent models is genuinely unsettled and a single run is not evidence of a robust strategy —
a caution for any long-horizon benchmark that reports one number.</p>
<p><b>The oracle is a reference, not a ceiling — and headroom is large.</b> Our "oracle"
plays with full access to hidden abilities, the future hotness trajectory, and latent quality,
but through a <i>fixed heuristic</i>; it is a strong informed-play reference, not a proven
optimum, and indeed {top['model']} exceeds it on all three seeds by riding the boom harder
(though it, too, collapses to {min(top_seeds):.0f} on the no-boom world). The real ceiling is
far higher and can be read straight off the citation mechanics: on the boom seed a single
optimally-timed top-venue paper accrues about 3,300 projected citations — nearly the entire
score of the best actual run — and a productive lab can place many such papers, putting a loose,
friction-free upper bound in the tens of thousands (Appendix). The best observed run ({max(top_seeds):.0f})
and the informed oracle ({max(orc_seeds) if orc_seeds else 0:.0f}) both capture a small
fraction of it; no agent plays reliably, and the highest-value move — anticipating a boom
rather than chasing it (§4) — is absent in every model. The benchmark is far from
saturated.</p>"""


def behavior_prose(behav, board):
    if not behav or not board:
        return "<p class='muted'>[behavior prose pending]</p>"
    top = board[0]["model"]
    # find a model that is highly active but low-impact (the "busy but unproductive" case)
    ranked = sorted(board, key=lambda r: -behav[r["model"]]["actions_per_month"])
    busy_low = None
    for r in board[len(board)//2:]:  # a lower-half model
        if behav[r["model"]]["actions_per_month"] >= 2.8:
            busy_low = r["model"]
            break
    tb, db = behav[top], behav.get(busy_low, {}) if busy_low else {}
    busy_clause = ""
    if busy_low:
        busy_clause = (f" <b>{busy_low}</b> is a sharp counterexample: it takes "
            f"{db['actions_per_month']:.1f} actions a month — as many as {top} — yet "
            f"converts only {db['pubs_per_student_year']:.2f} papers per student-year "
            f"against {top}'s {tb['pubs_per_student_year']:.2f}, and finishes near the "
            f"bottom of the table. Activity is not the bottleneck; turning it into "
            f"published work is.")
    corr = behav.get("_corr", {})
    rc = corr.get("conversion_impact_spearman")
    ra = corr.get("activity_impact_spearman")
    corr_clause = (f" Across the twelve models both correlate with Impact — action intensity at "
                   f"Spearman ρ={ra:.2f}, conversion at ρ={rc:.2f} — and the two are themselves "
                   f"collinear, so neither is cleanly 'the' bottleneck." if rc is not None else "")
    return f"""<p>Two quantitative axes (Figure 3) sharpen this.{corr_clause} The informative
signal is in the exceptions: {busy_low if busy_low else 'the busiest low scorer'} is as active
as {top} — {db.get('actions_per_month', 0):.1f} actions a month — yet converts only
{db.get('pubs_per_student_year', 0):.2f} papers per student-year against {top}'s
{tb['pubs_per_student_year']:.2f} and finishes near the bottom. Activity without conversion is
a distinct failure mode; the qualitative divide above — reasoning about hidden state versus
thrashing on the API — is what separates the labs that turn actions into cited papers from
those that do not.</p>"""


def ablation_prose(ab):
    if not ab:
        return "<p class='muted'>[ablation prose pending]</p>"
    by = {r["variant"]: r for r in ab}
    d = by.get("default (60mo)", {}).get("impact_mean", 0)
    h12 = by.get("short horizon (12mo)", {}).get("impact_mean", 0)
    h30 = by.get("mid horizon (30mo)", {}).get("impact_mean", 0)
    ns = by.get("no non-stationarity", {}).get("impact_mean", 0)
    return f"""<p>Running the deterministic rule-based baseline under modified world
configurations isolates where the difficulty comes from (Table 2). The clearest signal
is the <b>horizon</b>: shrinking the run from 60 to 30 to 12 months collapses baseline
Impact from {d:.0f} to {h30:.0f} to {h12:.0f}. This is the delayed-reward structure made
visible — citations accrue over years, so a short-horizon lab publishes too late to earn
almost anything, no matter how well it is run. A benchmark that ended at month 12 would
measure something else entirely.</p>
<p>Turning off <b>non-stationarity</b> (freezing topic hotness, no booms or busts) roughly
halves mean Impact ({d:.0f} → {ns:.0f}): in PI-Bench the drifting field is as much
opportunity as hazard — much of the upside comes from committing to a topic before it
booms, and a frozen world removes that lever. Removing the <b>attention</b> cap, by contrast,
barely moves the baseline (Table 2) — but that is because the conservative baseline stays
small; attention binds for agents that actually build a lab, as §4 shows (the top model
runs at the ceiling half the time). And an <b>ambitious</b> policy that hires to capacity and
runs only tier-3 projects bankrupts the lab on most seeds: ambition must be paid for out of a
runway the agent has to protect.</p>"""


def headline(board, baseline_row, oracle_row):
    if not board:
        return ("current models struggle to sustain a productive lab", "—", "—", "—")
    top = board[0]
    b = baseline_row["impact_mean"] if baseline_row else 0
    n_beat = sum(1 for r in board if baseline_row and r["impact_mean"] > b)
    return (top["model"], f"{top['impact_mean']:.0f}", str(n_beat), str(len(board)))


def chasing_prose(behav, board):
    if not behav or not board or not any(behav[r["model"]].get("topic_hot_rank")
                                         for r in board):
        return "<p class='muted'>[topic-behavior analysis pending re-run with eval logs]</p>"
    order = [r["model"] for r in board]
    rows = [(m, behav[m].get("topic_hot_rank"), behav[m].get("topic_concentration"))
            for m in order if behav[m].get("topic_hot_rank")]
    chasers = [m for m, hr, _ in rows if hr and hr < 3.2]
    coldish = sorted(rows, key=lambda t: -(t[1] or 0))
    cold_name = coldish[0][0] if coldish else "—"
    return f"""<p>A recurring question about real PIs is whether they chase fashionable
topics or sit on a cold bench betting on long-term value. Both appear in the traces, but
asymmetrically. Most capable models are <b>trend-chasers</b>: {', '.join(chasers[:4])} pick,
on average, close to the current hottest topic (hot-rank near 2 of 8) — sensible, since hot
topics earn more citations. The clearest <b>cold-bench</b> profile is {cold_name}, which
commits to a couple of less-fashionable topics and posts the lowest-variance, never-boom-
never-crash record. But <b>no model does the genuinely contrarian move</b>: entering a topic
while it is still cold and riding it up. A boom's onset is a partly exogenous jump that no
observable-only policy can perfectly foresee — so we do not claim full forecastability — but
its early, rising phase is visible in the preprint feed and the crowding lag before the news
makes it obvious, and the oracle exploits exactly that window. Every model instead enters
topics that are <i>already</i> hot (and therefore crowded and prone to scooping); the
anticipation axis (below) runs near zero for all of them. Reacting to observed hotness is
strictly worse than entering the rising phase early, which is where the most durable Impact
lives.</p>"""


def decomp_prose(dc):
    if not dc:
        return ""
    geo = dc.get("geo_rank", [])
    return f"""<p><b>Can three seeds rank models at all?</b> On the arithmetic mean the answer
looks bleak — one boom seed dominates — but the arithmetic mean of a heavy-tailed quantity is
the wrong summary. On the log scale, which matches the multiplicative reward, a two-way
variance decomposition over the 36 runs attributes <b>{dc['model_pct']:.0f}% of the variance to
the model</b> (skill), {dc['seed_pct']:.0f}% to the seed (luck), and {dc['resid_pct']:.0f}% to
their interaction — models are more separable than the raw spread suggests. The choice of
summary even moves the crown: by geometric mean the order is {', '.join(geo[:3])}, so
<b>{dc.get('geo_top')}</b> leads and the arithmetic winner {dc.get('arith_top')} (whose runs
have the largest log-scale spread) drops to third. We therefore read the leaderboard as a
robust separation of broad tiers plus a warning that the top ranks turn on how one weights the
boom seed; the eight-seed grid that would tighten the adjacent ranks is stated as future
work.</p>"""


def harness_prose(ha):
    if not ha:
        return ""
    wm, nm = ha["with_memory"], ha["no_memory"]
    return f"""<h3>Harness sensitivity</h3>
<p>Agent scores are known to depend on the execution scaffold, so we ablate the single most
load-bearing component of ours: the persistent memory file that carries long-horizon state
across monthly context refreshes. Disabling it (write_memory becomes a no-op; the prompt always
shows an empty memory) for <b>{ha['model']}</b> changes mean Impact from {wm['mean']} to
{nm['mean']} — that is, removing the memory scaffold does <i>not</i> lower the score, and
nominally raises it ({', '.join(map(str, wm['per_seed']))} → {', '.join(map(str, nm['per_seed']))}
per seed). Two things follow. First, the ranking is not a trivial artifact of the scaffold
handing the model state: when the state hand-off is removed, this model does at least as well.
Second, it nuances §4 — memory <i>use</i> correlates with capability, but for a mid-tier model
whose notes are low-quality, maintaining them is not causally load-bearing and may even cost
turn-budget. The more informative test is a memory-heavy strong model, and a full cross-scaffold
swap (a different runner or context budget) would bound harness dependence further; both are
future work, so rankings should be read within this fixed harness.</p>"""


def variance_prose(case):
    if not case:
        return "<p class='muted'>[variance analysis pending]</p>"
    L, R = case["left"], case["right"]
    return f"""<p>Because the simulator is deterministic, we replay every run's full world at
zero cost and decompose its Impact into <b>two multiplicative layers</b>. Most Impact comes
from riding a topic <i>boom</i>. <b>Whether a boom exists is exogenous</b>, fixed by the seed:
on our three worlds the hottest a topic gets is roughly 6.0, 6.0, and 3.0. <b>How much a model
capitalizes is the skill</b> — placing enough good papers in the hot topic and surviving to
publish them. Figure 2 shows both layers: Impact scales with the hotness a lab's papers
actually ride (left), and on boom worlds that Impact is bought with paper volume (right).
Heavy-tailed models commit hard and out-produce; timid models under-commit, capping both the
upside and the crash.</p>
<p><b>One model, two fates.</b> The clearest case is the top model, {case['model']}, on two
seeds. On seed {L['seed']} it secured a large moonshot grant by month 25, which bought the
runway to sustain a big lab and ride a booming topic to <b>Impact {L['outcome'].split()[-1]}</b>
(14+ papers, self-funding by year four). On seed {R['seed']} — a no-boom world — the same
aggressive playbook met a run of bad exogenous draws: its PhD offers were declined and the
postdoc search drew no applicants, it never landed a big grant, and it spent into a corner;
its own memory reads <i>"COLLAPSE M39 unless a grant lands"</i>, the grant did not, and the
lab went bankrupt at month 38 (its budget trajectory, and every model's, is in Figure 5), freezing Impact at <b>{R['outcome'].split()[-1]}</b> with no
going-concern projection. Identical strategy, opposite outcomes: the heavy tail is a
high-commitment policy meeting the luck of the seed — and precisely why a single number, or a
best-of-N run, misleads.</p>"""


def build():
    board = load("leaderboard.json", [])
    behav = load("behavior.json", {})
    skills = load("skills.json", {})
    ab = load("ablations.json", [])
    refs = load("refs.json", {})  # {baseline:{...}, oracle:{...}, model_list:[...]}
    case = load("case_study.json", {})
    decomp = load("variance_decomp.json", {})
    harness = load("ablation_harness.json", {})
    baseline_row = refs.get("baseline")
    oracle_row = refs.get("oracle")

    top_model, top_impact, n_beat, n_models = headline(board, baseline_row, oracle_row)
    model_list = ", ".join(refs.get("model_list", [r["model"] for r in board])) or \
        "seven Bailian-served models"
    spread = "—"
    if board:
        lo = min(r["impact_mean"] for r in board) or 1
        spread = f"{max(r['impact_mean'] for r in board)/lo:.0f}×"

    html = PAGE.format(
        css=CSS,
        headline_model=top_model, headline_impact=top_impact,
        spread=spread,
        n_beat=n_beat, n_models=n_models,
        model_list=model_list,
        b_broad=f"{refs.get('baseline_broad', {}).get('impact_mean', 0):.0f}",
        o_broad=f"{refs.get('oracle_broad', {}).get('impact_mean', 0):.0f}",
        board_table=leaderboard_table(board, baseline_row, oracle_row),
        ablation_table=ablation_table(ab),
        results_prose=results_prose(board, baseline_row, oracle_row, refs),
        variance_prose=variance_prose(case),
        decomp_prose=decomp_prose(decomp),
        harness_prose=harness_prose(harness),
        behavior_prose=behavior_prose(behav, board),
        chasing_prose=chasing_prose(behav, board),
        ablation_prose=ablation_prose(ab),
        fig_variance=fig("fig_variance.png",
                         "The variance decomposed. Left: Impact scales with the peak hotness "
                         "a lab's papers actually ride — the seed sets which cluster a run can "
                         "reach, the model sets how high within it. Right: on boom worlds, "
                         "paper volume converts the boom into Impact. Cross = collapse.", 2),
        fig_traj=fig("fig_budget_traj.png",
                     "Lab budget over 60 months, all runs per model (log scale). "
                     "A cross marks a collapse (bankruptcy); the dashed line is the "
                     "$600K starting fund.", 5),
        fig_impact=fig("fig_impact_traj.png",
                       "Cumulative citations accrue late. Mean across seeds per model, "
                       "with the rule-based baseline dashed. Most Impact arrives in the "
                       "final years — the delayed-reward structure the benchmark is built "
                       "around.", 1),
        fig_behavior=fig("fig_behavior.png",
                         "Behavioral axes. Left: actions per simulated month. Right: papers per "
                         "student-year. Both correlate with Impact (and with each other); the "
                         "informative cases are labs that are active yet fail to convert — a "
                         "distinct failure mode.", 3),
        fig_skills=fig("fig_skills.png",
                       "Recovering the capability axes from the hidden eval log: mentoring "
                       "allocation efficiency (0.5 = random), topic anticipation (&gt;0 = "
                       "enters before the boom), PhD attrition (lower better), and risk "
                       "calibration (bolder when affordable).", 4),
    )
    out = os.path.join(PAPER, "index.html")
    open(out, "w").write(html)
    print("wrote", out, f"({len(html)//1024} KB)")


# ---------------------------------------------------------------- template + CSS
CSS = open(os.path.join(os.path.dirname(__file__), "paper_style.css")).read() \
    if os.path.exists(os.path.join(os.path.dirname(__file__), "paper_style.css")) else ""

PAGE = """<title>PI-Bench — Can Agents Run a Research Lab?</title>
<style>{css}</style>
<div class="page">
<header class="masthead">
  <div class="wordmark">PI-<span>Bench</span></div>
  <div class="tagline">a long-horizon agent benchmark</div>
</header>

<section class="hero">
  <div class="eyebrow">benchmark &middot; long-horizon agents &middot; mechanistic world</div>
  <h1>Can agents run a research lab?</h1>
  <p class="dek">An LLM agent plays a new professor for five simulated years — hiring
  students whose talent is hidden, betting on research topics before they boom, chasing
  grants, and shepherding papers to citations — under two budgets at once: money and the
  PI's own attention.</p>
  <div class="headline-stats">
    <div class="stat"><div class="stat-num">{headline_impact}</div>
      <div class="stat-lab">best mean Impact<br><span>{headline_model}</span></div></div>
    <div class="stat"><div class="stat-num">{spread}</div>
      <div class="stat-lab">spread, top to bottom<br><span>tiers overlap within seed variance</span></div></div>
    <div class="stat"><div class="stat-num">60</div>
      <div class="stat-lab">simulated months<br><span>{n_models} models &middot; 3 seeds</span></div></div>
  </div>
</section>

<article class="paper">

<p class="abstract"><b>Abstract.</b> Language-model agents are competent at short,
well-specified tasks, but a research career is not a task — it is a long chain of
interdependent bets made under uncertainty, where feedback is slow and the field keeps
shifting. Real long-horizon agency demands a cluster of capabilities that current benchmarks
test in isolation, if at all: <b>(1)</b> inferring hidden state from noisy, biased signals;
<b>(2)</b> making irreversible commitments that cannot be unwound; <b>(3)</b> planning under
delayed, heavy-tailed rewards; <b>(4)</b> budgeting two scarce resources at once; and
<b>(5)</b> exploring a non-stationary environment before it is obviously worth it.
<b>PI-Bench</b> stresses these together by simulating one of the most information-poor,
delayed-reward jobs there is: running an academic lab for 60 months. The world is fully
mechanistic (no LLM judge in the reward path), partially observable, non-stationary, and full
of delayed, coupled consequences. Success is <b>Impact</b> — citations accrued plus a
projection of published work's future citations — a score built so that abandoning the lab to
hoard cash earns nothing. We evaluate {model_list}; Impact spans more than an order of
magnitude, every model captures only a small fraction of the attainable citation ceiling, and
— because a career turns on catching a single rare research boom — the scores are dominated by
a heavy-tailed variance that a few seeds cannot resolve. We quantify each capability above from
a hidden ground-truth log, closing the loop this abstract opens. PI-Bench is a step toward
measuring the sustained, adaptive intelligence that long-horizon agency demands.</p>

<h2><span class="sn">1</span> Introduction</h2>
<p>Agents built on today's models can fix a GitHub issue, follow a support policy, or
complete a web workflow. These are real skills, and they share a shape: a clear goal, a
short horizon, quick feedback. As agents saturate that shape, the interesting question is
what they do when the local task is no longer the bottleneck — when success depends on
<i>sustaining</i> progress toward a distant goal as earlier decisions keep shaping later
ones.</p>
<p>Running a research lab is a canonical instance of the opposite of a task: a five-year
arc in which nearly every important variable is hidden, nearly every payoff is delayed, and
the environment does not hold still. A new professor cannot observe how good an applicant
truly is, only noisy transcripts and inflated letters; cannot observe which topics will be
hot in two years, only this month's headlines; cannot observe what an agency wants, only
whether last year's proposal was funded. Her decisions commit resources that cannot be
recovered, and their consequences — citations, reputation, a student's morale collapsing
into departure — surface months or years later.</p>
<p>PI-Bench turns this into a benchmark. An agent runs a lab for five years through a
programmable interface over a fully mechanistic world — every outcome decided by explicit
rules and stochastic draws, never by a language model acting as judge, so success cannot be
talked into existence. Three design commitments give the task its character:</p>
<ul>
  <li><b>Two scarce resources, not one.</b> Beyond money, the agent has exactly 100 hours a
  month of its own attention — use-it-or-lose-it — to split across mentoring, proposals,
  paper polishing, interviews, and service, and this budget shrinks as the lab grows. A lab
  can be cash-rich and time-poor, and the two constraints bind at different moments.</li>
  <li><b>People as the central, illiquid asset.</b> Output comes from students whose ability
  must be <i>inferred</i> from biased signals at hiring, whose skill grows only with the
  mentoring hours you can spare, and whose morale can cascade into quitting. Stipends are
  multi-year commitments; you cannot fire a student to cut costs. Bets on people cannot be
  unwound.</li>
  <li><b>A reward you cannot harvest.</b> Impact counts citations already earned <i>plus a
  projection of what published work will earn over the next three years</i>, so a paper
  accepted in the final months still pays. There is no endgame in which stripping the lab
  and hoarding cash beats keeping the research engine running.</li>
</ul>
<p>Three methodological choices keep the measurement honest: we report the <b>mean across
seeds</b>, never a best-of-N run; we tune the rule-based baseline on <b>held-out</b> seeds
it never sees at test time; and we report <b>token cost</b> beside every score, so that
"spent more thinking" is not mistaken for "is more capable." The closest prior benchmark to
adopt this mechanistic, long-horizon shape is CEO-Bench (Chen et al., 2026), which runs an
agent through a simulated startup; PI-Bench is its complement in a different economy — an
illiquid, delayed, people-driven research career rather than a liquid operating business.</p>

<h2><span class="sn">2</span> Designing PI-Bench</h2>
<p>An agent runs a fictional lab for 60 months, beginning with a <b>$600,000 startup fund,
zero students, and baseline reputation</b>, graded on Impact at month 60. If the budget
ever falls below zero, the lab <b>collapses</b> and the run ends, keeping only citations
earned so far. Each month the agent takes actions across ~26 tools in eight namespaces —
recruiting, mentoring, running projects, submitting papers, writing proposals, doing field
research, responding to events — plus SQL queries over a 19-table observable database, then
advances the clock.</p>

<h3>The two budgets</h3>
<p>Cash flows in from grants and out through stipends, compute, travel, and overhead.
Separately, the PI has 100 hours of attention per month; every mentoring allocation,
interview, proposal, and revision draws it down, and unused hours expire. The core tension
is that the two budgets bind at different times: early on you have cash but no results to
build on; later you have results but not enough hours to mentor five students, write two
proposals, and polish three papers in the same month.</p>

<h3>What makes it hard</h3>
<p><b>Mechanistic, not judged.</b> Whether a paper is accepted, a student quits, or a grant
is funded is decided by explicit formulas and stochastic draws, never by an LLM asked to
role-play. This closes the failure mode where an agent talks a simulated judge into an
unearned reward. <b>Hidden and indirect.</b> The agent sees only what a real PI could —
dashboards, records, a news and preprint feed, reviewer scores, monthly student reports —
never true ability, latent quality, topic hotness, agency preferences, or morale, and must
infer them. <b>Delayed and coupled.</b> Research takes months, citations years, grant
decisions half a year; a scoop is revealed only after it has damaged a project; reputation
propagates across the lab. <b>Non-stationary.</b> Topic hotness drifts and jumps, crowding
follows with a lag and drives scooping, a funding climate cycles over years.</p>

<h3>A programmable interface</h3>
<p>The agent operates through a Python package executed in a terminal, not a fixed menu of
calls. It composes the API with SQL and its own analysis — joining
submissions and students to decide who revises which paper, or estimating topic momentum
from the preprint feed. Information acquisition is thus itself a tested capability. Context
is refreshed every month; only a self-maintained memory file persists, so long-horizon
coherence must live in what the agent writes down.</p>

<h2><span class="sn">3</span> Results</h2>
{board_table}
<p class="cap-note"><b>Table 1.</b> Benchmark summary. Impact is mean across seeds
{{101, 102, 103}}; per-seed values show the spread. "collapse" counts runs that went
bankrupt. Reference rows use the same three seeds: the non-LLM rule-based baseline (tuned
on separate held-out seeds) and the oracle (plays with full hidden state). Because three
seeds are high-variance, we also report broader eight-seed estimates in the text —
baseline {b_broad}, oracle {o_broad} — as more stable reference points.</p>
{results_prose}
{fig_impact}

<h3>The anatomy of the variance</h3>
{variance_prose}
{fig_variance}
{decomp_prose}

<h2><span class="sn">4</span> A look into agent behavior</h2>
<p>Because the world is fully logged, we can open the trajectories and read what agents
actually did. The single sharpest divide is whether a model treats the environment's hidden
parameters as a <i>system to be reverse-engineered</i> or as random noise.</p>
<p><b>Strong labs infer hidden structure from graded feedback and pivot.</b> Every top model
treats a grant rejection as evidence about an unobserved reward function. Fable-5's memory at
month 20 reads <i>"BSF rejected reasoning 2x → hypothesis BSF dislikes reasoning, trying
ai4science,"</i> later refined from a conference report to <i>"BSF prefers theory/data_systems
→ future BSF apps use data_systems."</i> GLM-5.2 reverse-engineers venue thresholds from
reviewer scores — <i>"CLAR bar: 4.4–5.2 accepted, 3.7–4.7 rejected … TIF funds reasoning ~25%
of the time"</i> — and every strong model models the pool-specific bias in applicant signals
(<i>"elite pool inflated paper signals; intl/nontrad interviews trustworthy"</i>). This is
explicit estimation of hidden decision boundaries and measurement bias — exactly the inference
the benchmark is built to demand.</p>
<p><b>Weak models substitute trial-and-error for a world model.</b> qwen-turbo wrote to its
memory file exactly once in 293 turns and re-fired the identical grant proposal every month;
it ended hoarding $741k having won six grants but published two papers and never hired a
student — cash with no plan. deepseek spent 51% of its turns in API/SQL error loops (against
1–4% for strong models), and thirty months in still had no team. A revealing edge case is
qwen-plus, whose reasoning is genuinely strong — it hypothesizes hidden draft-generation rules
correctly — yet it collapses by prioritizing student morale over runway, starting a project at
$4.3k cash and burning into insolvency. Good memory is necessary but not sufficient; what
tracks Impact is the <i>combination</i> the strong labs share — a persistent structured memory,
hypotheses about hidden parameters updated from feedback, and low-error execution that leaves
turn-budget for that reasoning.</p>
{behavior_prose}
{fig_behavior}

<h3>Chasing hot topics vs. sitting on the cold bench</h3>
{chasing_prose}

<h3>Recovering the five capabilities — closing the loop</h3>
<p>We now recover the capabilities the abstract enumerated, measuring each from a hidden
eval log the agent never sees (four axes in Figure 4, plus a resource-utilization measure).
<b>Mentoring allocation efficiency</b> — does the agent spend its zero-sum mentoring hours on
the students with the highest hidden return? — instruments axis (1), inference of hidden
state. <b>PhD attrition</b>, the share of hires that quit before graduating, is a proxy for
axis (2), the quality of an irreversible commitment. <b>Risk calibration</b> — does it take
bolder projects only when it can afford the variance? — probes axis (3), planning under
heavy-tailed reward. Axis (4), the <b>dual budget</b>, is not a metric but a measured fact:
attention genuinely binds for agents that build a lab — the top model runs at 77% mean
attention utilization and hits the ceiling in 51% of its months, while the models that barely
staff a lab sit near 15–27% — so the second budget is a live constraint precisely for the
ambitious strategies, even though it never binds the conservative baseline (§5). And
<b>topic anticipation</b> — does it enter a topic before it heats, or chase what is already
hot? — measures axis (5). The stronger models score higher on allocation and lower on
attrition; but anticipation runs near zero for every model, the one axis on which none
approaches informed play.</p>
{fig_skills}
{fig_traj}

<h2><span class="sn">5</span> Ablations</h2>
{ablation_prose}
{ablation_table}
<p class="cap-note"><b>Table 2.</b> Deterministic ablations: the rule-based baseline under
modified world configurations, mean over eight seeds. The horizon ablation isolates the
delayed-reward structure; freezing the field removes the boom-timing upside.</p>
{harness_prose}

<h2><span class="sn">6</span> Related work</h2>
<p><b>General agent evaluation.</b> Benchmarks such as SWE-bench, WebArena, τ-bench, GAIA,
and AppWorld measure valuable real-world skills — resolving issues, navigating sites,
following tool-use policies. <i>However</i>, they are scoped to short, single-episode tasks
with quickly observed outcomes: the agent gets a clear goal, acts for a bounded horizon, and
is graded on completion. They do not test whether an agent can sustain a coherent strategy as
its own earlier decisions reshape a stateful world over years.</p>
<p><b>Long-horizon and economic agency.</b> A newer line places agents in persistent
environments — running a vending machine over many days, closing monthly books, operating a
simulated business. <i>However</i>, these involve narrower decisions or largely stable,
observable dynamics, and typically grade a single liquid resource. PI-Bench differs on the
axis that matters most here: it is an <i>illiquid, delayed, people-driven</i> economy where
bets cannot be unwound, the reward is heavy-tailed and arrives across mismatched horizons,
and success requires inferring hidden state and a shifting field rather than optimizing a
dense, observable signal. The closest prior work, CEO-Bench (Chen et al., 2026), established
this mechanistic long-horizon shape for a startup; PI-Bench is its complement in the research
economy, and adds a second scarce resource (attention), an irreversible people-centric asset
base, and a harvest-resistant score.</p>

<h2><span class="sn">7</span> Limitations &amp; conclusion</h2>
<p><b>Limitations.</b> We name our gaps plainly. (i) Research <b>quality is a scalar</b> — we
model impact, not the substance of ideas — and we omit teaching, collaboration politics, and
the human texture of mentorship beyond a morale variable. (ii) The <b>oracle is not a proven
optimum</b>: it plays with hidden information through a fixed heuristic, and the strongest model
exceeds it on all three seeds; our headroom claim therefore rests on the transparent citation-based
ceiling (Appendix), not on the oracle. (iii) <b>Three seeds</b> give a mean with wide spread
but do not settle the ranking of adjacent models; the robust claims are the tier separation and
the near-zero anticipation axis, and we are extending all models to the eight-seed grid. (iv)
Results are <b>entangled with one harness</b>: long-horizon coherence lives in a self-maintained
memory file, and while we ablate that component (§5) and hold the scaffold, tool set, and
context policy identical across models — the winner uses fewer tokens than most losers, so the
ranking is not a trivial compute artifact — a full cross-scaffold swap remains future work. (v)
Cost is reported in <b>tokens, not dollars</b>, so a cross-provider price comparison is out of
scope.</p>
<p><b>Conclusion.</b> PI-Bench shows a gap between models' local tool competence and the
sustained judgment a five-year project demands: agents take plausible individual actions but
struggle to compound them into a lab that grows under delayed feedback, hidden state, and a
shifting field. Two findings sharpen the picture. First, the reward is <b>heavy-tailed</b> — a
career turns on catching one rare boom — so a single number, or a best-of-N run, misleads, and
long-horizon benchmarks must report the per-seed spread. Second, the highest-value skill,
<b>anticipating</b> a boom rather than chasing it, is absent in every model evaluated. Closing
those gaps is what it will take to build agents that steer long-running efforts, not just answer
requests.</p>

<h2><span class="sn">A</span> Attainable-Impact ceiling</h2>
<p>Rather than a hand-tuned upper-bound heuristic, we read the ceiling straight off the
citation mechanics. A published paper accrues citations at a rate
<code class="inl">v · e^{{0.42(q−5)}} · H_k(t) · age(t) · (1 + 0.08(R−R_0))</code> per month. On
seed 101 a topic reaches hotness <code class="inl">H = 6.0</code>; substituting a top-venue
paper (<code class="inl">v = 3.0</code>) of near-maximal quality (<code class="inl">q = 9</code>)
under high reputation and integrating over an optimal publication month plus the 36-month
projection window yields <b>≈ 3,300 projected citations for a single paper</b> — already close
to the entire score of the best observed run (4,078). A productive lab that places even a
handful of such papers reaches the tens of thousands. This is a loose bound (it ignores
attention, review, and scooping frictions), but its purpose is only to show that the best
observed Impact captures a small fraction of what the reward mechanics permit — the benchmark
is far from saturated. The computation is fully determined by the released config; no free
friction factor is introduced.</p>

<h2><span class="sn">B</span> Adversarial validation</h2>
<p>Before running experiments we subjected the simulator and harness to a multi-agent
adversarial review across seven lenses (spec conformance, correctness, hidden-information
leaks, economic and scoring exploits, determinism, harness security), each finding verified
by an independent skeptic. It surfaced — and we fixed — a sandbox escape that exposed the
entire hidden world state (including the future hotness trajectory) and allowed direct
score mutation; an uncapped reputation-farming exploit scoring several times the baseline
with zero students; a one-month compute-spike exploit on paper quality; and an
order-dependence in review outcomes that violated determinism. The hardened sandbox and the
resulting invariant and penetration suites ship with the benchmark.</p>

<h2 class="refs-h">References</h2>
<ol class="refs">
<li>A. Backlund and L. Petersson. Vending-Bench: A Benchmark for Long-Term Coherence of
Autonomous Agents. <i>arXiv:2502.15840</i>, 2025.</li>
<li>H. Chen, K. Narasimhan, and Z. Liu. CEO-Bench: Can Agents Play the Long Game?
<i>arXiv:2606.18543</i>, 2026.</li>
<li>C. E. Jimenez, J. Yang, A. Wettig, S. Yao, K. Pei, O. Press, and K. Narasimhan. SWE-bench:
Can Language Models Resolve Real-World GitHub Issues? <i>ICLR</i>, 2024.</li>
<li>G. Mialon, C. Fourrier, T. Wolf, Y. LeCun, and T. Scialom. GAIA: A Benchmark for General
AI Assistants. <i>ICLR</i>, 2024.</li>
<li>M. Mussa and S. Rosen. Monopoly and Product Quality. <i>Journal of Economic Theory</i>,
18(2):301–317, 1978.</li>
<li>T. Patwardhan, R. Dias, et al. GDPval: Evaluating AI Model Performance on Real-World
Economically Valuable Tasks. <i>arXiv:2510.04374</i>, 2025.</li>
<li>Penrose AI. AccountingBench: Evaluating LLMs on Real Long-Horizon Business Tasks. 2025.</li>
<li>H. Trivedi, T. Khot, M. Hartmann, R. Manku, V. Dong, E. Li, S. Gupta, A. Sabharwal, and
N. Balasubramanian. AppWorld: A Controllable World of Apps and People for Benchmarking
Interactive Coding Agents. <i>ACL</i>, 2024.</li>
<li>S. Yao, N. Shinn, P. Razavi, and K. Narasimhan. τ-bench: A Benchmark for Tool-Agent-User
Interaction in Real-World Domains. <i>arXiv:2406.12045</i>, 2025.</li>
<li>S. Zhou, F. F. Xu, H. Zhu, et al. WebArena: A Realistic Web Environment for Building
Autonomous Agents. <i>ICLR</i>, 2024.</li>
</ol>

</article>

<footer class="colophon">
  <div>PI-Bench &middot; a mechanistic long-horizon benchmark for research-lab agency</div>
  <div class="muted">Simulator, harness, adversarial test suite, and all agent
  trajectories released with the paper.</div>
</footer>
</div>
"""

if __name__ == "__main__":
    build()
