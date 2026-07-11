"""Build the PIBench research SITE — a self-contained, deployable project page.

Unlike the paper (build_paper.py), this is a richer multi-section page meant as a
standalone mode of dissemination: a peer opens one URL and understands the whole
work — motivation, the task, an interactive leaderboard, the findings with figures,
the world mechanics, and how to reproduce. Everything is inlined (CSS, JS, figures
as data URIs, data as embedded JSON) so it can be dropped on any static host.
"""
import base64
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")
SITE = os.path.join(ROOT, "site")


def load(name, default):
    p = os.path.join(PAPER, name)
    return json.load(open(p)) if os.path.exists(p) else default


def data_uri(fname):
    p = os.path.join(PAPER, "figs", fname)
    if not os.path.exists(p):
        return ""
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()


def img(fname, cap):
    uri = data_uri(fname)
    if not uri:
        return f'<figure><div class="muted" style="padding:2rem;text-align:center">[{fname} — run analyze]</div><figcaption>{cap}</figcaption></figure>'
    return f'<figure><img src="{uri}" alt="{cap}"><figcaption>{cap}</figcaption></figure>'


ARCH = r"""PROVIDERS  Bailian/DashScope (qwen, glm, kimi, deepseek) · OpenRouter (gpt, claude, gemini)
    │  OpenAI-compatible /chat/completions  (auto-routed by model id)
    ▼
HARNESS  60 monthly steps · context RESET each month · only memory.md (<=6KB) persists
    │   system prompt + memory + dashboard(JSON) ──► up to 8 python code turns
    ▼
SANDBOX  AST sanitizer (blocks dunder/__globals__/bare-except) · facades (no world ref)
    │   restricted builtins · SIGALRM timeout
    ▼
AGENT API (pilab)  recruit · students · projects · papers · grants · field · events
    │   + query(sql) over OBSERVABLE state · time.next_month()   (validates money+attention)
    ▼
WORLD ENGINE  deterministic per-subsystem RNG · tick() closes a month
    ├─ OBSERVABLE: 19-table SQLite, dashboards, noisy monthly reports, news/preprint feed
    └─ HIDDEN (never exported): true ability, latent paper quality, topic hotness H,
       agency preferences, morale, FUTURE hotness trajectory
    SUBSYSTEMS: Field(8 topics, OU hotness + booms) · People(4 pools, PhD/postdoc/RA/
    manager ladder, morale->quit, mentoring bandit) · Projects(tier 1/2/3) · Venues ·
    Citations(ramp+decay) · Grants(4 agencies, hidden prefs) · Reputation · Events
    TWO BUDGETS: cash (bankruptcy) + attention (100h - oversight tax)
    SCORE: Impact = citations-to-date + 36-month projected citations (H, R frozen)
    ▼
ANALYSIS  baseline (held-out tuned) · oracle (headroom) · ablations · 4 skill axes
    ──► leaderboard · figures · this site · the paper"""


def build():
    board = load("leaderboard.json", [])
    skills = load("skills.json", {})
    behav = load("behavior.json", {})
    refs = load("refs.json", {})
    ab = load("ablations.json", [])
    baseline = refs.get("baseline", {})
    oracle = refs.get("oracle", {})
    oracle_broad = refs.get("oracle_broad", {}) or oracle
    baseline_broad = refs.get("baseline_broad", {}) or baseline

    top = board[0] if board else {"model": "—", "impact_mean": 0}
    n_models = len(board)

    # embed data for the interactive leaderboard
    lb_rows = []
    for r in board:
        s = skills.get(r["model"], {})
        b = behav.get(r["model"], {})
        lb_rows.append(dict(
            model=r["model"], impact=r["impact_mean"],
            seeds=list(r["impact_per_seed"].values()),
            collapse=r["collapsed"], n=r["n_runs"],
            pubs=r["pubs_mean"], top=r["top_pubs_mean"], grants=r["grants_mean"],
            grad=r["graduated_mean"], surv=r["survival_mean"], tokens=r["tokens_mean_m"],
            alloc=s.get("alloc_efficiency"), anticip=s.get("anticipation"),
            quit=s.get("phd_early_quit_rate"), hot_rank=b.get("topic_hot_rank"),
            ppsy=b.get("pubs_per_student_year")))
    refs_rows = [
        dict(model="rule-based baseline", impact=baseline.get("impact_mean", 0),
             collapse=baseline.get("collapsed", 0), n=baseline.get("n", 0), ref=True,
             note="no LLM · held-out tuned"),
        dict(model="oracle (full hidden state)", impact=oracle.get("impact_mean", 0),
             collapse=oracle.get("collapsed", 0), n=oracle.get("n", 0), ref=True,
             note="upper bound"),
    ]
    data_json = json.dumps(dict(models=lb_rows, refs=refs_rows), ensure_ascii=False)

    css = open(os.path.join(os.path.dirname(__file__), "site_style.css")).read()

    html = TEMPLATE.format(
        css=css,
        top_model=top["model"], top_impact=f"{top['impact_mean']:.0f}",
        oracle_ceiling=f"{oracle_broad.get('impact_mean', 0):.0f}",
        n_models=n_models,
        baseline_broad=f"{baseline_broad.get('impact_mean', 0):.0f}",
        data_json=data_json,
        arch=ARCH,
        fig_impact=img("fig_impact_traj.png",
            "<b>Citations accrue late.</b> Mean cumulative citations per model; the "
            "rule-based baseline dashed. Most Impact arrives in the final years — the "
            "delayed-reward structure the benchmark is built around."),
        fig_skills=img("fig_skills.png",
            "<b>Four capability axes</b> from a hidden eval log the agent never sees: "
            "mentoring allocation (0.5 = random), topic anticipation (&gt;0 = enters before "
            "the boom), PhD attrition (lower better), risk calibration (bolder when affordable)."),
        fig_behavior=img("fig_behavior.png",
            "<b>Activity is not the bottleneck; conversion is.</b> Left: actions per month, "
            "uncorrelated with Impact. Right: papers per student-year, which tracks the leaderboard."),
        fig_traj=img("fig_budget_traj.png",
            "<b>Two failure modes.</b> Lab budget over 60 months, all runs per model (log scale); "
            "a cross marks collapse. Most models do not go bankrupt — they simply fail to publish."),
    )
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w").write(html)
    print(f"wrote {SITE}/index.html ({len(html)//1024} KB, {n_models} models)")


TEMPLATE = r"""<title>PIBench · Can Agents Run a Research Lab?</title>
<meta name="description" content="A long-horizon benchmark where an LLM agent runs an academic research lab for five simulated years.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style>

<nav class="nav">
  <span class="mark">PI<span>Bench</span></span>
  <div class="links">
    <a href="#task">The task</a>
    <a href="#leaderboard">Leaderboard</a>
    <a href="#findings">Findings</a>
    <a href="#design">How it works</a>
    <a href="#reproduce">Reproduce</a>
    <button class="theme" onclick="toggleTheme()">◐ theme</button>
  </div>
</nav>

<section class="hero">
  <div class="inner">
    <div class="eyebrow">a long-horizon benchmark for agentic intelligence</div>
    <h1>Can agents run a research lab?</h1>
    <p class="dek">An LLM agent plays a new professor for five simulated years — hiring
    students whose talent is hidden, betting on research topics before they boom, chasing
    grants, and shepherding papers to citations — under two budgets at once: money, and the
    PI's own attention. Every outcome is generated by mechanistic rules, not a language-model
    judge.</p>
    <div class="cta">
      <a class="primary" href="#leaderboard">See the leaderboard</a>
      <a href="#task">How the task works</a>
      <a href="#reproduce">Code &amp; data</a>
    </div>
    <div class="stats">
      <div class="stat"><div class="n">{top_impact}</div>
        <div class="l">best mean Impact<br><b>{top_model}</b></div></div>
      <div class="stat"><div class="n">{oracle_ceiling}</div>
        <div class="l">oracle ceiling<br><b>no model comes near</b></div></div>
      <div class="stat"><div class="n">60</div>
        <div class="l">simulated months<br><b>{n_models} models · 3 seeds</b></div></div>
    </div>
  </div>
</section>

<section id="why">
  <div class="inner read">
    <div class="eyebrow">why this task</div>
    <h2>The consequential work of a career is not a task</h2>
    <p>Agents are increasingly good at short, well-specified tasks: fix an issue, follow a
    policy, complete a web flow. Those share a shape — a clear goal, a short horizon, quick
    feedback. Running a research lab is the opposite: a five-year arc in which almost every
    variable is hidden, almost every payoff is delayed, and the field will not hold still. A
    new professor cannot observe how good an applicant truly is, only noisy transcripts and
    inflated letters; cannot observe which topics will be hot in two years, only this month's
    headlines; cannot observe what an agency wants, only whether last year's proposal was
    funded. Decisions commit resources that cannot be recovered, and their consequences —
    citations, reputation, a student's morale collapsing into departure — surface months or
    years later.</p>
    <div class="grid g3" style="margin-top:1.6rem">
      <div class="card"><div class="k">two budgets</div><h3>Money &amp; attention</h3>
        <p>Beyond cash, the agent has 100 hours a month of its own time — and the pool shrinks
        as the lab grows. You can be rich and time-poor; the two constraints bind at different
        moments.</p></div>
      <div class="card"><div class="k">illiquid</div><h3>People you can't unwind</h3>
        <p>Output comes from students whose ability must be inferred from biased signals and
        whose morale can cascade into quitting. Stipends are multi-year; you cannot fire a
        student to cut costs.</p></div>
      <div class="card"><div class="k">no harvest</div><h3>A reward you can't cash out</h3>
        <p>Impact counts citations earned plus a projection of future citations, so a late paper
        still pays. There is no endgame where stripping the lab beats keeping it running.</p></div>
    </div>
  </div>
</section>

<section id="task">
  <div class="inner">
    <div class="eyebrow">the task at a glance</div>
    <h2>One month in the life of the agent</h2>
    <p class="read">Each simulated month the agent writes Python against a programmable lab
    API, reads its own 19-table database with SQL, then advances the clock. Context resets
    every month — only a memory file it maintains persists, so long-horizon strategy has to
    be written down. A typical month:</p>
    <div class="console">
      <div class="bar-top"><span class="dot" style="background:#e34948"></span>
        <span class="dot" style="background:#eda100"></span>
        <span class="dot" style="background:#1baf7a"></span>
        <span class="muted" style="margin-left:.6rem">month 25 · Y3M1</span></div>
<pre><span class="cmt"># recruiting season — read applicants, interview the promising, infer hidden ability</span>
apps = <span class="kw">recruit</span>.applicants()
<span class="kw">recruit</span>.interview([a[<span class="str">"id"</span>] <span class="kw">for</span> a <span class="kw">in</span> apps[:5]])   <span class="cmt"># costs 3h attention each</span>
<span class="kw">recruit</span>.offer(<span class="str">"APP214"</span>)                            <span class="cmt"># a multi-year, unfireable bet</span>

<span class="cmt"># which topics are heating up? mine the preprint feed, not just the dashboard</span>
q = <span class="kw">query</span>(<span class="str">"SELECT topic, SUM(preprint_count) n FROM preprint_feed "</span>
          <span class="str">"WHERE month &gt; 22 GROUP BY topic ORDER BY n DESC"</span>)

<span class="kw">projects</span>.start(<span class="str">"reasoning"</span>, tier=<span class="str">3</span>, members=[<span class="str">"S07"</span>,<span class="str">"S11"</span>], monthly_compute=<span class="str">2500</span>)
<span class="kw">papers</span>.polish(<span class="str">"D14"</span>, hours=<span class="str">10</span>); <span class="kw">papers</span>.submit(<span class="str">"D14"</span>, <span class="str">"NAIC"</span>)   <span class="cmt"># top venue</span>
<span class="kw">grants</span>.propose(<span class="str">"BSF-m26"</span>, <span class="str">"reasoning"</span>, hours=<span class="str">25</span>, attach=[<span class="str">"P03"</span>])
<span class="kw">recruit</span>.hire_manager()                            <span class="cmt"># buy back PI attention</span>
<span class="kw">write_memory</span>(<span class="str">"S07 high-growth, mentor heavily. reasoning booming — front-run it."</span>)
<span class="kw">next_month</span>()
<span class="out">→ budget $612k · attention 60h left · 1 paper under review · runway 41 mo</span></pre>
    </div>
    <p class="read muted" style="margin-top:1rem">The world answers only through what a real PI
    could see — dashboards, records, reviewer scores, a noisy news feed. True ability, latent
    paper quality, topic hotness, and agency preferences stay hidden and must be inferred.</p>
  </div>
</section>

<section id="leaderboard">
  <div class="inner">
    <div class="eyebrow">results</div>
    <h2>Leaderboard</h2>
    <p class="read">Impact is the mean across three world seeds — never a best-of-N. Per-seed
    values are shown because the variance is the story: a lab's fate turns on a few early,
    irreversible bets. Click a column to sort.</p>
    <div class="lb-wrap"><table class="lb" id="lb"></table></div>
    <p class="muted" style="font-size:.82rem;margin-top:.8rem">Reference rows use the same
    seeds. Broader eight-seed estimates: baseline {baseline_broad}, oracle {oracle_ceiling}.
    "collapse" counts runs that went bankrupt.</p>
  </div>
</section>

<section id="findings">
  <div class="inner">
    <div class="eyebrow">what we found</div>
    <h2>Four things the traces reveal</h2>

    <div class="tabs" id="figtabs">
      <button class="active" data-t="f1">Delayed reward</button>
      <button data-t="f2">Heavy-tailed variance</button>
      <button data-t="f3">Chase vs cold-bench</button>
      <button data-t="f4">Skill axes</button>
    </div>

    <div class="tabpane active" id="f1">
      <div class="grid g2" style="align-items:center">
        <div class="read"><h3>Citations arrive years after the work</h3>
        <p>For the first two simulated years almost no model earns anything; Impact fans out
        only in the final stretch. A benchmark that ended at month 12 would measure something
        else entirely — the ablations show baseline Impact collapsing from ~237 at 60 months to
        ~2 at 12. Long-horizon investment is the whole point.</p></div>
        {fig_impact}
      </div>
    </div>

    <div class="tabpane" id="f2">
      <div class="read"><h3>The variance is structure, not noise</h3>
      <p>The strongest model's three runs can read like <b>2106 / 160 / 158</b> — a single
      world drives its average — and the oracle shows the same signature. Most of a lab's
      Impact comes from catching a topic <i>boom</i>, a rare high-magnitude event, so a
      career's payoff is heavy-tailed, much as real academic impact is. This is why we report
      the spread and a mean, not a best-of-N: with three seeds the ranking of adjacent models
      is genuinely unsettled. One model is the informative exception — low variance, never a
      boom, never a crash: a conservative PI who trades upside for safety.</p></div>
      {fig_traj}
    </div>

    <div class="tabpane" id="f3">
      <div class="grid g2" style="align-items:center">
        <div class="read"><h3>Everyone chases; no one anticipates</h3>
        <p>Some PIs chase fashionable topics; some sit on a cold bench betting on long-term
        value. Both appear — but asymmetrically. Almost every capable model is a trend-chaser,
        picking close to the currently hottest topic. The one cold-bench profile posts the
        lowest-variance record. Yet <b>no model makes the genuinely contrarian move</b>:
        entering a still-cold topic that later blooms. That needs foresight — the oracle has it
        because it sees the future field — and its absence is why the anticipation axis runs
        near zero. Agents react to observed hotness; they do not anticipate it, and that is
        where the largest, most durable Impact lives.</p></div>
        {fig_behavior}
      </div>
    </div>

    <div class="tabpane" id="f4">
      <div class="read"><h3>Measuring the skills, not just the score</h3>
      <p>From a hidden eval log the agent never sees, we score four capabilities: does it spend
      its zero-sum <b>mentoring</b> hours on the highest-return students? does it <b>anticipate</b>
      topics or chase them? what share of PhD hires <b>quit</b> before graduating (a proxy for
      the quality of an irreversible commitment)? does it take <b>bolder</b> projects when it can
      afford the variance? Together they probe the core of the task: allocating a perishable
      budget and making irreversible bets on latent processes whose payoff is heavy-tailed.</p></div>
      {fig_skills}
    </div>
  </div>
</section>

<section id="design">
  <div class="inner">
    <div class="eyebrow">how the world works</div>
    <h2>A mechanistic world, not an LLM judge</h2>
    <p class="read">Every outcome — whether a paper is accepted, a student quits, a grant is
    funded — is decided by explicit formulas and stochastic draws (Normal, Poisson, Bernoulli,
    Log-normal), never by a language model asked to role-play. This closes the failure mode
    where an agent talks a simulated judge into an unearned reward, and makes runs exactly
    reproducible: same seed and policy, same outcome.</p>
    <div class="mech" style="margin-top:1.4rem">
      <div class="row"><div class="t">field</div><div class="d">8 topics; hotness is a mean-reverting process with boom/bust jumps; crowding lags hotness and drives scooping. Observed only through a noisy news &amp; preprint feed.</div></div>
      <div class="row"><div class="t">people</div><div class="d">4 applicant pools with different hidden ability and signal biases. A role ladder from illiquid to liquid: PhD (unfireable, grows, authors) → postdoc (contract) → RA (cheap throughput) → lab manager (buys back attention). Morale is a hidden state that can cascade into quitting.</div></div>
      <div class="row"><div class="t">projects</div><div class="d">Tier 1/2/3 trade work for ambition; tier 3 risks dead ends. Draft quality uses the time-averaged team and compute, so last-minute manipulation buys nothing.</div></div>
      <div class="row"><div class="t">venues</div><div class="d">Top/mid conference, workshop, journal — different acceptance bars, decision delays, publication cadence, and visibility. Reviews are noisy.</div></div>
      <div class="row"><div class="t">citations</div><div class="d">A ramp-then-decay curve scaled by topic hotness and reputation — the delayed, heavy-tailed reward.</div></div>
      <div class="row"><div class="t">grants</div><div class="d">4 agencies with hidden topic preferences and a macroeconomic funding climate that cycles over years, seen only through delayed noisy news.</div></div>
      <div class="row"><div class="t">score</div><div class="d">Impact = citations to date + a deterministic 36-month projection of published work (hotness &amp; reputation frozen). Budget below zero ends the run.</div></div>
    </div>

    <h3>System architecture</h3>
    <pre class="arch">{arch}</pre>

    <h3>Validated before use</h3>
    <p class="read">Before running experiments we put the simulator and harness through a
    multi-agent adversarial review across seven lenses — spec conformance, correctness,
    hidden-information leaks, economic and scoring exploits, determinism, harness security —
    each finding verified by an independent skeptic. It surfaced, and we fixed, a sandbox
    escape that exposed the entire hidden world (including the future hotness trajectory) and
    allowed direct score mutation; an uncapped reputation-farming exploit; a compute-spike
    exploit on paper quality; and an order-dependence that violated determinism. The hardened
    sandbox and the resulting invariant and penetration suites ship with the benchmark.</p>
  </div>
</section>

<section id="reproduce">
  <div class="inner read">
    <div class="eyebrow">reproduce</div>
    <h2>Run it yourself</h2>
    <p>The simulator is ~2,700 lines of dependency-light Python. Every run records its full
    trajectory — result, monthly snapshots, every action, the complete turn-by-turn transcript,
    and a hidden eval log — so any lab's five years can be replayed decision by decision.</p>
    <div class="console"><pre><span class="cmt"># deterministic sanity + the rule-based baseline</span>
python3 scripts/smoke.py
python3 scripts/calibrate.py all

<span class="cmt"># one LLM episode (Bailian or OpenRouter, auto-routed by model id)</span>
python3 scripts/run_agent.py --model qwen3.7-max --seed 101 --months 60
python3 scripts/run_agent.py --model anthropic/claude-opus-4.8 --seed 101

<span class="cmt"># the full matrix, then regenerate figures + this site</span>
python3 scripts/run_experiments.py --exp exp2 --models ... --seeds 101,102,103
python3 scripts/finalize.py --exp exp2</pre></div>
    <p class="muted" style="margin-top:1rem">Evaluation protocol: every model runs the same
    seeds; the headline is the mean, never a best-of-N; the baseline is tuned on held-out
    seeds; token cost is reported beside every score.</p>
  </div>
</section>

<footer class="foot">
  <div class="inner">
    <b style="color:var(--ink)">PIBench</b> — a mechanistic, long-horizon benchmark for
    research-lab agency. Simulator, harness, adversarial test suite, and all agent trajectories
    released openly.
    <div style="margin-top:.6rem">The closest prior benchmark to adopt this mechanistic,
    long-horizon shape is CEO-Bench (Chen et al., 2026); PIBench is its complement in an
    illiquid, delayed, people-driven research economy.</div>
  </div>
</footer>

<script>
const DATA = {data_json};
function toggleTheme(){{
  const r=document.documentElement;
  const cur=r.getAttribute('data-theme')|| (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  r.setAttribute('data-theme', cur==='dark'?'light':'dark');
}}
// tabs
document.querySelectorAll('#figtabs button').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('#figtabs button').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tabpane').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); document.getElementById(b.dataset.t).classList.add('active');
}});
// leaderboard
const COLS=[
  {{k:'model',t:'Model',fmt:v=>v}},
  {{k:'impact',t:'Impact',fmt:v=>v.toFixed(0),bar:true}},
  {{k:'seeds',t:'per-seed',fmt:v=>v?('<span class=seeds>'+v.map(x=>Math.round(x)).join(' / ')+'</span>'):'—',nosort:true}},
  {{k:'collapse',t:'collapse',fmt:(v,r)=>v+'/'+r.n}},
  {{k:'pubs',t:'pubs',fmt:v=>v==null?'—':v.toFixed(1)}},
  {{k:'grants',t:'grants',fmt:v=>v==null?'—':v.toFixed(1)}},
  {{k:'ppsy',t:'papers/yr',fmt:v=>v==null?'—':v.toFixed(2)}},
  {{k:'anticip',t:'anticip.',fmt:v=>v==null?'—':v.toFixed(2)}},
  {{k:'quit',t:'attrition',fmt:v=>v==null?'—':v.toFixed(2)}},
  {{k:'tokens',t:'tokens',fmt:v=>v==null?'—':v.toFixed(2)+'M'}},
];
let sortKey='impact', sortDir=-1;
function render(){{
  const maxI=Math.max(...DATA.models.map(m=>m.impact),1);
  let rows=[...DATA.models];
  if(sortKey!=='seeds') rows.sort((a,b)=>((a[sortKey]??-1e9)-(b[sortKey]??-1e9))*sortDir);
  const head='<tr>'+COLS.map(c=>`<th class="${{c.k===sortKey?'active':''}}" ${{c.nosort?'':`onclick="sortBy('${{c.k}}')"`}}>${{c.t}}${{c.k===sortKey?(sortDir<0?' ▾':' ▴'):''}}</th>`).join('')+'</tr>';
  const body=rows.map(r=>'<tr>'+COLS.map(c=>{{
    let v=r[c.k];
    if(c.k==='model') return `<td class=model>${{v}}</td>`;
    let inner=c.fmt(v,r);
    if(c.bar&&v!=null){{const w=Math.round(58*v/maxI); inner=`<span class=bar style="width:${{w}}px"></span>`+inner;}}
    return `<td>${{inner}}</td>`;
  }}).join('')+'</tr>').join('');
  const refs=DATA.refs.map(r=>'<tr class=ref>'+COLS.map(c=>{{
    if(c.k==='model') return `<td class=model>${{r.model}}</td>`;
    if(c.k==='impact') return `<td>${{r.impact.toFixed(0)}}</td>`;
    if(c.k==='collapse') return `<td>${{r.collapse}}/${{r.n}}</td>`;
    if(c.k==='tokens') return `<td>${{r.note}}</td>`;
    return '<td>—</td>';
  }}).join('')+'</tr>').join('');
  document.getElementById('lb').innerHTML=head+body+refs;
}}
function sortBy(k){{ if(k===sortKey) sortDir*=-1; else {{sortKey=k; sortDir=-1;}} render(); }}
render();
</script>
"""

if __name__ == "__main__":
    build()
