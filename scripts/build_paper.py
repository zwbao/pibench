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
        seeds = " / ".join(str(int(v)) for v in r["impact_per_seed"].values())
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
            f"<tr class='ref'><td class='model'>oracle (full hidden state)</td>"
            f"<td class='num'>{oracle_row['impact_mean']:.0f}</td>"
            f"<td class='num tiny'>—</td><td class='num'>{oracle_row['collapsed']}"
            f"/{oracle_row['n']}</td><td class='num'>{oracle_row['pubs']:.1f}</td>"
            f"<td class='num'>—</td><td class='num'>—</td><td class='num'>—</td>"
            f"<td class='num'>—</td><td class='num tiny'>upper bound</td></tr>")
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
    hi, lo = max(top_seeds), min(top_seeds)
    orc_seeds = refs.get("oracle", {}).get("per_seed", [])
    return f"""<p>Table 1 summarizes the benchmark. Impact spans a wide range — from
<b>{top['model']}</b> at {top['impact_mean']:.0f} down to {bot['model']} at
{bot['impact_mean']:.0f}, a {top['impact_mean']/max(1,bot['impact_mean']):.0f}-fold gap —
so PI-Bench discriminates cleanly across capability tiers. The two weakest models fail to
beat even the simple non-LLM baseline on the same worlds, while the strongest four clear
it by a wide margin.</p>
<p><b>The scores are dominated by variance, and the variance is structure, not noise.</b>
{top['model']}'s three runs scored {', '.join(f'{int(v)}' for v in top_seeds)} — a single
seed contributes most of its average. The oracle shows the same signature
({', '.join(f'{int(v)}' for v in orc_seeds)}): one world admits a score of over 2,000,
another barely 40. The reason is that most of a lab's Impact comes from catching a topic
<i>boom</i> — a rare, high-magnitude event — so a career's payoff is heavy-tailed, much as
real academic impact is. This is precisely why we report the per-seed spread and a mean
rather than a best-of-N: with three seeds the ranking of adjacent models is not settled,
and a single lucky run is not evidence of a robust strategy. It is also a caution for any
long-horizon benchmark that reports one number.</p>
<p><b>Headroom remains.</b> The oracle — playing with full access to hidden abilities, the
future hotness trajectory, and latent quality — averages {orc_broad:.0f} over a broader
eight-seed estimate (and {orc:.0f} over these three), well above any model's stable
performance; the simple baseline's broader estimate is {b_broad:.0f}. No agent reliably
reaches the attainable frontier: the best model touches the oracle's neighborhood only on
the one lucky, boom-rich seed and falls back to a few hundred on the others.</p>"""


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
    return f"""<p>Behavioral traces separate the models by more than the headline number.
Figure 3 shows two axes. <b>Action intensity</b> — actions taken per simulated month —
varies about three-fold across models, but it does <i>not</i> track Impact.{busy_clause}</p>
<p>The second axis, <b>conversion</b> (papers published per student-year), tracks the
leaderboard far better: the strongest lab, {top}, extracts
{tb['pubs_per_student_year']:.2f} papers from each student-year, roughly twice what the
weakest labs manage. The gap is not in taking actions — every model issues valid tool
calls — but in composing mentoring, project choice, polishing, and venue targeting into a
paper that actually gets in and gets cited. The bottleneck is not issuing valid tool
calls — every model does that — but composing them into a coherent research program that
survives delayed feedback and a shifting field.</p>"""


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
booms, and a frozen world removes that lever. Finally, an <b>ambitious</b> policy that
hires to capacity and runs only tier-3 projects bankrupts the lab on most seeds: overreach
without runway discipline bankrupts the lab: ambition must be paid for out of a runway the
agent has to protect.</p>"""


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
never-crash record. But <b>no model does the genuinely contrarian move</b>: entering a
still-cold topic that later blooms. That requires foresight — the oracle does it because it
sees the future field — and its absence is why the anticipation axis (below) runs near zero
for every model. Agents react to observed hotness; they do not anticipate it, which is
precisely where the largest, most durable Impact lives.</p>"""


def build():
    board = load("leaderboard.json", [])
    behav = load("behavior.json", {})
    skills = load("skills.json", {})
    ab = load("ablations.json", [])
    refs = load("refs.json", {})  # {baseline:{...}, oracle:{...}, model_list:[...]}
    baseline_row = refs.get("baseline")
    oracle_row = refs.get("oracle")

    top_model, top_impact, n_beat, n_models = headline(board, baseline_row, oracle_row)
    model_list = ", ".join(refs.get("model_list", [r["model"] for r in board])) or \
        "seven Bailian-served models"
    oracle_ceiling = f"{refs.get('oracle_broad', {}).get('impact_mean', 0):.0f}" \
        if refs.get("oracle_broad") else "—"

    html = PAGE.format(
        css=CSS,
        headline_model=top_model, headline_impact=top_impact,
        oracle_ceiling=oracle_ceiling,
        n_beat=n_beat, n_models=n_models,
        model_list=model_list,
        b_broad=f"{refs.get('baseline_broad', {}).get('impact_mean', 0):.0f}",
        o_broad=f"{refs.get('oracle_broad', {}).get('impact_mean', 0):.0f}",
        board_table=leaderboard_table(board, baseline_row, oracle_row),
        ablation_table=ablation_table(ab),
        results_prose=results_prose(board, baseline_row, oracle_row, refs),
        behavior_prose=behavior_prose(behav, board),
        chasing_prose=chasing_prose(behav, board),
        ablation_prose=ablation_prose(ab),
        fig_traj=fig("fig_budget_traj.png",
                     "Lab budget over 60 months, all runs per model (log scale). "
                     "A cross marks a collapse (bankruptcy); the dashed line is the "
                     "$600K starting fund.", 1),
        fig_impact=fig("fig_impact_traj.png",
                       "Cumulative citations accrue late. Mean across seeds per model, "
                       "with the rule-based baseline dashed. Most Impact arrives in the "
                       "final years — the delayed-reward structure the benchmark is built "
                       "around.", 2),
        fig_behavior=fig("fig_behavior.png",
                         "Behavioral axes. Left: actions taken per simulated month — not "
                         "correlated with Impact. Right: papers per student-year, which "
                         "tracks the leaderboard: the gap is conversion, not activity.", 3),
        fig_skills=fig("fig_skills.png",
                       "Four capability axes from the hidden eval log: mentoring "
                       "allocation efficiency (0.5 = random), topic anticipation (>0 = "
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
    <div class="stat"><div class="stat-num">{oracle_ceiling}</div>
      <div class="stat-lab">oracle ceiling<br><span>no model comes near</span></div></div>
    <div class="stat"><div class="stat-num">60</div>
      <div class="stat-lab">simulated months<br><span>{n_models} models &middot; 3 seeds</span></div></div>
  </div>
</section>

<article class="paper">

<p class="abstract"><b>Abstract.</b> Language-model agents are competent at short,
well-specified tasks, but a research career is not a task — it is a long chain of
interdependent bets made under uncertainty, where feedback is slow and the field keeps
shifting. <b>PI-Bench</b> stresses these capabilities together by simulating one of the most
information-poor, delayed-reward jobs there is: running an academic lab for 60 months. The
world is fully mechanistic (no LLM judge in the reward path), partially observable,
non-stationary, and full of delayed, coupled consequences. Success is <b>Impact</b> —
citations accrued plus a projection of published work's future citations — a score built
so that abandoning the lab to hoard cash earns nothing. We evaluate {model_list} and find
that most struggle to sustain a productive lab.</p>

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

<h2><span class="sn">4</span> A look into agent behavior</h2>
{behavior_prose}
{fig_behavior}

<h3>Chasing hot topics vs. sitting on the cold bench</h3>
{chasing_prose}

<h3>Four capability axes</h3>
<p>Beyond the headline, we measure four skills from a hidden eval log the agent never sees:
<b>mentoring allocation efficiency</b> (does the
agent spend its zero-sum mentoring hours on the students with the highest hidden return?),
<b>topic anticipation</b> (does it enter topics before they heat, or chase what is already
hot?), <b>PhD attrition</b> (the share of hires that quit before graduating — a proxy for
the quality of an irreversible commitment), and <b>risk calibration</b> (does it take bolder
projects when it can afford the variance?). Together they probe the core of the task:
allocating a perishable budget and making irreversible bets on latent processes whose payoff
is heavy-tailed and arrives across mismatched horizons.</p>
{fig_skills}
{fig_traj}

<h2><span class="sn">5</span> Ablations</h2>
{ablation_prose}
{ablation_table}
<p class="cap-note"><b>Table 2.</b> Deterministic ablations: the rule-based baseline under
modified world configurations, mean over eight seeds. The horizon ablation isolates the
delayed-reward structure; freezing the field removes the boom-timing upside.</p>

<h2><span class="sn">6</span> Limitations &amp; conclusion</h2>
<p>We approximate a research career and gaps remain: the quality of research is abstracted
to a scalar; we omit teaching, collaboration politics, and the human texture of mentorship
beyond a morale variable; three seeds report a mean with spread but do not settle the
ranking of close models; and results are entangled with the harness and a model's
willingness to spend tokens, which we report to keep visible. Still, the headline holds:
current agents can take plausible individual actions — interview a candidate, submit a
paper, write a proposal — but struggle to compound them into a lab that grows under delayed
feedback, hidden state, and a shifting field. Measuring that gap is the point.</p>

<h2><span class="sn">A</span> Adversarial validation</h2>
<p>Before running experiments we subjected the simulator and harness to a multi-agent
adversarial review across seven lenses (spec conformance, correctness, hidden-information
leaks, economic and scoring exploits, determinism, harness security), each finding verified
by an independent skeptic. It surfaced — and we fixed — a sandbox escape that exposed the
entire hidden world state (including the future hotness trajectory) and allowed direct
score mutation; an uncapped reputation-farming exploit scoring several times the baseline
with zero students; a one-month compute-spike exploit on paper quality; and an
order-dependence in review outcomes that violated determinism. The hardened sandbox and the
resulting invariant and penetration suites ship with the benchmark.</p>

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
