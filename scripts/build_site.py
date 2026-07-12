"""Build the PI-Bench research SITE — a self-contained, web-native project page.

A peer opens one URL and understands the whole work: motivation, the task, an
interactive leaderboard, the findings with LIVE charts (drawn in-browser, not static
images), a hand-drawn system architecture, expandable methodology, conclusions, and
how to reproduce. Everything is inlined (CSS, JS, data, static figures as data URIs)
so it drops onto any static host. Uses sentinel-token replacement (not str.format)
so the embedded JavaScript needs no brace escaping.
"""
import base64
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")
SITE = os.path.join(ROOT, "site")
GITHUB = "https://github.com/zwbao/pibench"

# categorical palette (8 validated + 4 extensions) — matches the matplotlib figures
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948",
           "#e87ba4", "#eb6834", "#16a0a0", "#8a6d3b", "#6a5acd", "#c71585"]


def load(name, default):
    p = os.path.join(PAPER, name)
    return json.load(open(p)) if os.path.exists(p) else default


def data_uri(fname):
    p = os.path.join(PAPER, "figs", fname)
    if not os.path.exists(p):
        return ""
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()


def fig(fname, cap):
    uri = data_uri(fname)
    if not uri:
        return f'<figure><div class="muted" style="padding:2rem;text-align:center">[{fname}]</div><figcaption>{cap}</figcaption></figure>'
    return f'<figure><img src="{uri}" alt="{cap}"><figcaption>{cap}</figcaption></figure>'


def arch_svg():
    """Hand-drawn layered architecture (replaces the ASCII diagram)."""
    layers = [
        ("PROVIDERS", "Bailian / DashScope · OpenRouter — the LLM under test", "OpenAI-compatible API, auto-routed by model id", False),
        ("HARNESS", "60 monthly steps · context resets each month", "only memory.md (≤6KB) persists · up to 8 code turns/month", False),
        ("SANDBOX", "AST sanitizer · facades · restricted builtins · timeout", "the hidden world is unreachable from agent code", False),
        ("AGENT API — pilab", "recruit · students · projects · papers · grants · field · events", "+ query(sql) over observable state · next_month()", False),
    ]
    W, x0, bw = 920, 40, 840
    y = 24
    rows = []
    lh = 62
    for name, desc, tag, hl in layers:
        cls = "box hl" if hl else "box"
        rows.append(f'<rect class="{cls}" x="{x0}" y="{y}" width="{bw}" height="48" rx="8"/>')
        rows.append(f'<text class="lyr" x="{x0+16}" y="{y+21}">{name}</text>')
        rows.append(f'<text class="desc" x="{x0+16}" y="{y+38}">{desc}</text>')
        rows.append(f'<text class="tag" x="{x0+bw-16}" y="{y+29}" text-anchor="end">{tag}</text>')
        y += lh
        rows.append(f'<path class="flow" d="M{x0+bw/2},{y-14} L{x0+bw/2},{y}"/>')
    # world engine box (taller, split observable/hidden)
    wy = y
    wh = 150
    rows.append(f'<rect class="box" x="{x0}" y="{wy}" width="{bw}" height="{wh}" rx="8"/>')
    rows.append(f'<text class="lyr" x="{x0+16}" y="{wy+22}">WORLD ENGINE</text>')
    rows.append(f'<text class="desc" x="{x0+16}" y="{wy+39}">deterministic per-subsystem RNG · tick() closes each month · 8 topics, 4 applicant pools, role ladder, venues, grants, two budgets</text>')
    # observable / hidden split
    oy = wy + 52
    half = (bw - 48) / 2
    rows.append(f'<rect class="box" x="{x0+16}" y="{oy}" width="{half}" height="82" rx="6"/>')
    rows.append(f'<text class="hidtag" x="{x0+30}" y="{oy+18}" style="fill:var(--indigo)">OBSERVABLE</text>')
    rows.append(f'<text class="desc" x="{x0+30}" y="{oy+36}">19-table SQLite · dashboards</text>')
    rows.append(f'<text class="desc" x="{x0+30}" y="{oy+51}">noisy monthly reports</text>')
    rows.append(f'<text class="desc" x="{x0+30}" y="{oy+66}">news &amp; preprint feed</text>')
    rows.append(f'<rect class="box hidden hl" x="{x0+32+half}" y="{oy}" width="{half}" height="82" rx="6"/>')
    rows.append(f'<text class="hidtag" x="{x0+46+half}" y="{oy+18}">HIDDEN — never exported</text>')
    rows.append(f'<text class="desc" x="{x0+46+half}" y="{oy+36}">true ability · latent quality</text>')
    rows.append(f'<text class="desc" x="{x0+46+half}" y="{oy+51}">topic hotness · agency prefs</text>')
    rows.append(f'<text class="desc" x="{x0+46+half}" y="{oy+66}">morale · FUTURE hotness traj.</text>')
    y = wy + wh
    rows.append(f'<path class="flow" d="M{x0+bw/2},{y} L{x0+bw/2},{y+14}"/>')
    y += 14
    rows.append(f'<rect class="box" x="{x0}" y="{y}" width="{bw}" height="48" rx="8"/>')
    rows.append(f'<text class="lyr" x="{x0+16}" y="{y+21}">ANALYSIS</text>')
    rows.append(f'<text class="desc" x="{x0+16}" y="{y+38}">baseline (held-out tuned) · oracle (headroom) · ablations · 4 skill axes → leaderboard, figures, this site</text>')
    y += 48
    H = y + 24
    return (f'<svg class="arch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="PI-Bench architecture">'
            f'<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6" fill="var(--muted)"/></marker></defs>'
            + "".join(rows) + "</svg>")


def sparkline(series, collapsed):
    """Inline SVG budget trajectory: linear, with a zero line and an end dot."""
    W, H, pad = 260, 46, 4
    lo, hi = min(series + [0]), max(series + [0])
    rng = (hi - lo) or 1
    n = len(series)
    def x(i): return pad + (W - 2 * pad) * i / max(1, n - 1)
    def y(v): return H - pad - (H - 2 * pad) * (v - lo) / rng
    d = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(series))
    zy = y(0)
    ex, ey = x(n - 1), y(series[-1])
    return (f'<svg class="spark" viewBox="0 0 {W} {H}" preserveAspectRatio="none">'
            f'<line class="zero" x1="{pad}" y1="{zy:.1f}" x2="{W-pad}" y2="{zy:.1f}"/>'
            f'<path d="{d}"/>'
            f'<circle class="end{" bad" if collapsed else ""}" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5"/></svg>')


def case_study_html(case):
    if not case:
        return ""
    def col(side, cls):
        c = case[side]
        ms = "".join(
            f'<li class="tag-{m.get("tag","")}"><span class="mo">m{m["m"]}</span>{m["t"]}</li>'
            for m in c["milestones"])
        return (f'<div class="case-col {cls}"><div class="oc">{c["outcome"]}</div>'
                f'<div class="sub">seed {c["seed"]} · {c["label"]}</div>'
                f'{sparkline(c["budget_series"], c["collapsed"])}'
                f'<ul class="ms">{ms}</ul></div>')
    return (f'<div class="case">{col("left","win")}{col("right","lose")}</div>'
            f'<div class="case-moral">{case["moral"]}</div>')


def build():
    board = load("leaderboard.json", [])
    skills = load("skills.json", {})
    behav = load("behavior.json", {})
    refs = load("refs.json", {})
    case = load("case_study.json", {})
    traj = load("trajectories.json", {"months": [], "series": [], "baseline": None})
    baseline = refs.get("baseline", {})
    oracle = refs.get("oracle", {})
    oracle_broad = refs.get("oracle_broad", {}) or oracle
    baseline_broad = refs.get("baseline_broad", {}) or baseline
    top = board[0] if board else {"model": "—", "impact_mean": 0}
    n_models = len(board)

    lb_rows = []
    for r in board:
        s = skills.get(r["model"], {})
        b = behav.get(r["model"], {})
        lb_rows.append(dict(
            model=r["model"], impact=r["impact_mean"],
            seeds=list(r["impact_per_seed"].values()),
            collapse=r["collapsed"], n=r["n_runs"], pubs=r["pubs_mean"],
            grants=r["grants_mean"], surv=r["survival_mean"], tokens=r["tokens_mean_m"],
            anticip=s.get("anticipation"), quit=s.get("phd_early_quit_rate"),
            ppsy=b.get("pubs_per_student_year"), hotrank=b.get("topic_hot_rank")))
    refs_rows = [
        dict(model="rule-based baseline", impact=baseline.get("impact_mean", 0),
             collapse=baseline.get("collapsed", 0), n=baseline.get("n", 0), note="no LLM · held-out"),
        dict(model="oracle (informed reference)", impact=oracle.get("impact_mean", 0),
             collapse=oracle.get("collapsed", 0), n=oracle.get("n", 0), note="full-info policy"),
    ]
    payload = dict(models=lb_rows, refs=refs_rows, traj=traj, palette=PALETTE)

    css = open(os.path.join(os.path.dirname(__file__), "site_style.css")).read()
    html = TEMPLATE
    repl = {
        "%%CSS%%": css,
        "%%GITHUB%%": GITHUB,
        "%%DATA%%": json.dumps(payload, ensure_ascii=False),
        "%%TOP_MODEL%%": top["model"], "%%TOP_IMPACT%%": f"{top['impact_mean']:.0f}",
        "%%ORACLE%%": f"{oracle_broad.get('impact_mean', 0):.0f}",
        "%%SPREAD%%": (f"{max(r['impact'] for r in lb_rows)/max(1,min(r['impact'] for r in lb_rows)):.0f}×"
                       if lb_rows else "—"),
        "%%BASELINE_BROAD%%": f"{baseline_broad.get('impact_mean', 0):.0f}",
        "%%NMODELS%%": str(n_models),
        "%%ARCH%%": arch_svg(),
        "%%FIG_SKILLS%%": fig("fig_skills.png",
            "<b>Four capability axes</b> from a hidden eval log the agent never sees: mentoring "
            "allocation (0.5 = random), topic anticipation (&gt;0 = enters before the boom), "
            "PhD attrition (lower better), risk calibration (bolder when affordable)."),
        "%%FIG_BEHAVIOR%%": fig("fig_behavior.png",
            "<b>Activity is not the bottleneck; conversion is.</b> Left: actions per month, "
            "uncorrelated with Impact. Right: papers per student-year, which tracks the leaderboard."),
    }
    repl["%%FIG_VARIANCE%%"] = fig("fig_variance.png",
        "<b>The variance decomposed.</b> Left: Impact scales with the hotness the agent's papers "
        "actually rode — the seed sets which cluster (≈1.5 / 3 / 6) a run can reach, the model "
        "sets how high within it. Right: on boom worlds, paper volume converts the boom into "
        "Impact. × = collapsed.")
    repl["%%CASE_STUDY%%"] = case_study_html(case)
    for k, v in repl.items():
        html = html.replace(k, v)
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w").write(html)
    print(f"wrote {SITE}/index.html ({len(html)//1024} KB, {n_models} models)")


TEMPLATE = r"""<title>PI-Bench · Can Agents Run a Research Lab?</title>
<meta name="description" content="A long-horizon benchmark where an LLM agent runs an academic research lab for five simulated years.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>%%CSS%%</style>

<nav class="nav">
  <span class="mark">PI-<span>Bench</span></span>
  <div class="links">
    <a href="#task">The task</a>
    <a href="#leaderboard">Leaderboard</a>
    <a href="#findings">Findings</a>
    <a href="#takeaways">Takeaways</a>
    <a href="#design">How it works</a>
    <a href="%%GITHUB%%">GitHub ↗</a>
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
      <a href="%%GITHUB%%">Code &amp; data ↗</a>
    </div>
    <div class="stats">
      <div class="stat"><div class="n">%%TOP_IMPACT%%</div>
        <div class="l">best mean Impact<br><b>%%TOP_MODEL%%</b></div></div>
      <div class="stat"><div class="n">%%SPREAD%%</div>
        <div class="l">spread, top to bottom<br><b>tiers overlap within seed variance</b></div></div>
      <div class="stat"><div class="n">60</div>
        <div class="l">simulated months<br><b>%%NMODELS%% models · 3 seeds</b></div></div>
    </div>
  </div>
</section>

<section id="why">
  <div class="inner read">
    <div class="eyebrow">why this task</div>
    <h2>The consequential work of a career is not a task</h2>
    <p>Agents are increasingly good at short, well-specified tasks — fix an issue, follow a
    policy, complete a web flow. Those share a shape: a clear goal, a short horizon, quick
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
        as the lab grows. You can be rich and time-poor; the constraints bind at different moments.</p></div>
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
    every month — only a memory file it maintains persists, so long-horizon strategy has to be
    written down.</p>
    <div class="console">
      <div class="bar-top"><span class="dot" style="background:#e34948"></span>
        <span class="dot" style="background:#eda100"></span>
        <span class="dot" style="background:#1baf7a"></span>
        <span class="muted" style="margin-left:.6rem">month 25 · Y3M1</span></div>
<pre><span class="cmt"># recruiting season — read applicants, interview the promising, infer hidden ability</span>
apps = <span class="kw">recruit</span>.applicants()
<span class="kw">recruit</span>.interview([a[<span class="str">"id"</span>] <span class="kw">for</span> a <span class="kw">in</span> apps[:5]])   <span class="cmt"># 3h attention each</span>
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
    could see. True ability, latent paper quality, topic hotness, and agency preferences stay
    hidden and must be inferred from noisy traces.</p>
  </div>
</section>

<section id="leaderboard">
  <div class="inner">
    <div class="eyebrow">results</div>
    <h2>Leaderboard</h2>
    <p class="read">Impact is the mean across three world seeds — never a best-of-N. Per-seed
    values are shown because the variance is the story. Click a column header to sort.</p>
    <div class="lb-wrap"><table class="lb" id="lb"></table></div>
    <p class="muted" style="font-size:.82rem;margin-top:.8rem">Reference rows use the same
    seeds. Broader eight-seed estimates: baseline %%BASELINE_BROAD%%, oracle %%ORACLE%%.
    "collapse" counts runs that went bankrupt.</p>
  </div>
</section>

<section id="findings">
  <div class="inner">
    <div class="eyebrow">what we found · live charts</div>
    <h2>Four things the traces reveal</h2>

    <h3>1 · Citations arrive years after the work</h3>
    <p class="read">For the first two simulated years almost no model earns anything; Impact
    fans out only in the final stretch. Hover to read any month; toggle a model in the legend.
    A benchmark that ended at month 12 would measure something else entirely.</p>
    <div class="chart" id="c-cites">
      <div class="ctrl"><button data-scale="linear" class="active">linear</button><button data-scale="log">log</button></div>
    </div>
    <div class="legend" id="leg-cites"></div>

    <h3 style="margin-top:2.4rem">2 · The variance is structure, not noise</h3>
    <p class="read">Each model's three runs are plotted on a log Impact axis — three dots, and a
    bar at their mean. The dots span orders of magnitude. Hover a dot for its seed.</p>
    <div class="chart" id="c-strip"></div>
    <p class="read" style="margin-top:1.4rem">Reconstructing every run's full world (the
    simulator is deterministic, so we can replay it exactly at zero cost) shows the variance is
    <b>two multiplicative layers</b>. Most Impact comes from riding a topic <i>boom</i> — a rare,
    high-magnitude event. Whether a boom exists is <b>exogenous</b>, set by the seed; how much a
    model <b>capitalizes</b> on it — by placing enough good papers in the hot topic and surviving
    to publish them — is the skill. Heavy-tailed models commit hard and produce many papers, so
    they explode on a lucky seed and crash on an unlucky one; stable models under-commit, capping
    both the upside and the downside.</p>
    %%FIG_VARIANCE%%

    <p class="read"><b>Can three seeds rank models at all?</b> On the arithmetic mean, one boom
    seed dominates — but that is the wrong summary for a heavy-tailed quantity. On the log scale,
    a variance decomposition over the 36 runs puts <b>47% of the variance on the model</b>
    (skill), 34% on the seed (luck), and 19% on their interaction: models are more separable than
    the raw spread suggests. The summary even moves the crown — by geometric mean gpt-5.6-sol
    leads and the arithmetic winner claude-fable-5 (largest log-scale spread) drops to third. We
    read the board as a robust separation of broad tiers, with the top ranks turning on how one
    weights the boom seed; an eight-seed grid to tighten adjacent ranks is future work.</p>

    <h4 style="margin-top:2rem;font-family:var(--sans);font-size:1rem;color:var(--ink)">One model, two fates</h4>
    <p class="read">The clearest illustration is a single model — the top-scoring
    <b>claude-fable-5</b> — on two different worlds. Its own monthly memory notes tell the story;
    the sparkline is its cash trajectory.</p>
    %%CASE_STUDY%%

    <h3 style="margin-top:2.4rem">3 · Everyone chases hot topics; no one anticipates them</h3>
    <p class="read">Some PIs chase fashionable topics; some sit on a cold bench betting on
    long-term value. Both appear — but asymmetrically. Almost every capable model is a
    trend-chaser, picking close to the currently hottest topic. Yet <b>no model makes the
    genuinely contrarian move</b>: entering a still-cold topic that later blooms. That needs
    foresight — the oracle has it because it sees the future field — and its absence is why the
    anticipation axis runs near zero. Agents react to observed hotness; they do not anticipate
    it, and that is where the largest, most durable Impact lives.</p>
    %%FIG_SKILLS%%

    <h3 style="margin-top:2.4rem">4 · Strong labs reverse-engineer the hidden world</h3>
    <p class="read">Because every run is fully logged, we can read what agents actually did.
    The sharpest divide: strong models treat the environment's hidden parameters as a
    <b>system to reverse-engineer</b>, not as noise. They infer a grant agency's tastes from
    rejections (Fable-5's memory: <i>"BSF rejected reasoning 2× → hypothesis BSF dislikes
    reasoning, trying ai4science"</i>), back out venue thresholds from reviewer scores
    (GLM-5.2: <i>"CLAR bar: 4.4–5.2 accepted"</i>), and correct the pool-specific bias in
    applicant signals. Weak models substitute trial-and-error: qwen-turbo wrote to memory once
    in 293 turns and hoarded $741k with two papers and no students; deepseek spent half its
    turns in API errors and had no team thirty months in. Both activity and conversion
    correlate with Impact (ρ ≈ 0.8, and with each other), so neither is cleanly the bottleneck —
    but the informative cases are labs that are <b>active yet cannot convert</b>: deepseek is as
    busy as the top models and finishes near the bottom.</p>
    %%FIG_BEHAVIOR%%
  </div>
</section>

<section id="takeaways">
  <div class="inner">
    <div class="eyebrow">conclusions</div>
    <h2>What PI-Bench shows</h2>
    <div class="takeaways">
      <div class="take"><div class="num">01</div><h3>A wide, honest gap</h3>
        <p>Impact spans more than an order of magnitude across models, and every model captures
        only a small fraction of the attainable citation ceiling (read straight off the reward
        mechanics — tens of thousands, vs. a best run near 4,000). Current agents take plausible
        individual actions but cannot yet compound them into a lab that grows under delayed
        feedback, hidden state, and a shifting field.</p></div>
      <div class="take"><div class="num">02</div><h3>Reward is heavy-tailed</h3>
        <p>A five-year career is dominated by whether the agent catches one rare research boom.
        This makes a single number — or a best-of-N run — actively misleading, and argues that
        long-horizon benchmarks must report per-seed spread, as PI-Bench does.</p></div>
      <div class="take"><div class="num">03</div><h3>Reactive, not anticipatory</h3>
        <p>Models chase topics that are already hot rather than committing early to ones that
        will be. The highest-value strategy — the contrarian bet that pays off years later —
        requires foresight none of them show.</p></div>
      <div class="take"><div class="num">04</div><h3>Investing ≠ operating</h3>
        <p>PI-Bench probes a distinct capability cluster: allocating a perishable budget and
        making irreversible bets on latent processes whose payoff is delayed and lumpy. It is a
        complement to operating-style benchmarks, not a restatement of them.</p></div>
    </div>
  </div>
</section>

<section id="design">
  <div class="inner">
    <div class="eyebrow">how it works</div>
    <h2>A mechanistic world, not an LLM judge</h2>
    <p class="read">Every outcome — whether a paper is accepted, a student quits, a grant is
    funded — is decided by explicit formulas and stochastic draws, never by a language model
    asked to role-play. This closes the failure mode where an agent talks a simulated judge into
    an unearned reward, and makes runs exactly reproducible: same seed and policy, same outcome.</p>

    <div style="margin:1.4rem 0 2rem">%%ARCH%%</div>

    <h3>The mechanics, in depth</h3>
    <p class="read muted">The high-level rules are below; expand any subsystem for the model
    that generates it.</p>

    <details class="disc"><summary>Field &amp; topics — where booms come from</summary>
      <div class="body"><p>Eight research topics each carry a hidden <b>hotness</b> that follows a
      log-space Ornstein–Uhlenbeck process around a slowly drifting mean, punctuated by boom and
      bust jumps. <b>Crowding</b> follows hotness with a lag and drives the scoop hazard and
      novelty decay, so a topic that is visibly hot is also contested. The agent never sees
      hotness — only a Poisson news feed, a preprint feed, and lagged conference reports.</p>
      <div class="formula">H_k(t+1) = H_k(t) + θ·(mean − H_k) + σ·ε   ·   boom ×2.2 @ p=0.02   ·   bust ×0.5 @ p=0.015</div></div>
    </details>

    <details class="disc"><summary>People — a bandit over hidden potential</summary>
      <div class="body"><p>Four applicant pools carry different hidden ability distributions and
      signal biases (international letters inflated, non-traditional transcripts noisy with rare
      gems). Skill grows only with the mentoring hours you can spare; morale is a hidden
      mean-reverting state driven by paper outcomes, scoops, overload, and support, and a low
      draw raises a quit hazard. A role ladder runs from illiquid to liquid — PhD (unfireable,
      grows, authors) → postdoc (contract) → RA (cheap throughput) → lab manager (buys back
      attention). Mentoring is a zero-sum allocation across students of unknown, heterogeneous
      return.</p></div>
    </details>

    <details class="disc"><summary>Projects, venues &amp; citations — the delayed reward</summary>
      <div class="body"><p>Projects are tier 1/2/3 — more work for more ambition; tier 3 risks
      dead ends. Draft quality uses the <i>time-averaged</i> team and compute, so last-minute
      manipulation buys nothing. Four venues (top/mid conference, workshop, journal) differ in
      acceptance bar, decision delay, publication cadence, and visibility; reviews are noisy.
      Citations then follow a ramp-then-decay curve scaled by topic hotness and reputation — the
      delayed, heavy-tailed payoff at the heart of the task.</p>
      <div class="formula">cites/mo ~ Poisson( visibility · e^{0.42(q−5)} · hotness · age-curve · (1 + rep) )</div></div>
    </details>

    <details class="disc"><summary>Grants &amp; the two budgets</summary>
      <div class="body"><p>Four agencies fund on hidden topic preferences under a macroeconomic
      funding climate that cycles over years, seen only through delayed, noisy news. Cash pays
      stipends, compute, travel; below zero the lab collapses. Separately, the PI has 100 hours a
      month of attention, reduced by an oversight tax that grows with headcount — so the second
      budget binds harder as the lab grows, and a lab manager trades money for reclaimed time.</p></div>
    </details>

    <details class="disc"><summary>Scoring &amp; the harvest-resistant design</summary>
      <div class="body"><p>Impact = citations accrued to date + a deterministic projection of each
      published paper's next 36 months of citations, with hotness and reputation frozen at the
      final month. Because a late paper still earns its projection, there is no endgame where
      stripping the lab and hoarding cash beats keeping the research engine running — the failure
      mode we observed in cash-graded simulators.</p>
      <div class="formula">Impact(T) = Σ citations(≤T) + Σ_published Ê[cites in (T, T+36] | q, venue, H(T), R(T)]</div></div>
    </details>

    <h3 style="margin-top:2rem">Validated before use</h3>
    <p class="read">Before any experiment the simulator and harness went through a multi-agent
    adversarial review across seven lenses — spec conformance, correctness, hidden-information
    leaks, economic and scoring exploits, determinism, harness security — each finding verified by
    an independent skeptic. It surfaced, and we fixed, a sandbox escape that exposed the entire
    hidden world (including the future hotness trajectory) and allowed direct score mutation; an
    uncapped reputation-farming exploit; a compute-spike exploit on paper quality; and an
    order-dependence that violated determinism. The hardened sandbox and the resulting invariant
    and penetration suites ship with the benchmark.</p>
    <p class="read"><b>Harness sensitivity.</b> Scores can depend on the scaffold, so we ablate
    its most load-bearing part — the persistent memory file. Disabling it for qwen-plus does
    <i>not</i> lower its score (mean 80 → 202), so the ranking is not a trivial artifact of the
    scaffold handing the model state; a memory-heavy strong-model ablation and a full
    cross-scaffold swap remain future work, so rankings should be read within this fixed
    harness.</p>
  </div>
</section>

<section id="reproduce">
  <div class="inner read">
    <div class="eyebrow">reproduce</div>
    <h2>Run it yourself</h2>
    <p>The simulator is ~2,700 lines of dependency-light Python. Every run records its full
    trajectory — result, monthly snapshots, every action, the complete turn-by-turn transcript,
    and a hidden eval log — so any lab's five years can be replayed decision by decision. All of
    it is open on <a href="%%GITHUB%%">GitHub ↗</a>.</p>
    <div class="console"><pre><span class="cmt"># deterministic sanity + the rule-based baseline</span>
git clone %%GITHUB%%
pip install -r requirements.txt && cp .env.example .env   <span class="cmt"># add your API key(s)</span>
python3 scripts/smoke.py

<span class="cmt"># one LLM episode (Bailian or OpenRouter, auto-routed by model id)</span>
python3 scripts/run_agent.py --model qwen3.7-max --seed 101 --months 60
python3 scripts/run_agent.py --model anthropic/claude-opus-4.8 --seed 101

<span class="cmt"># the full matrix, then regenerate figures + paper + this site</span>
python3 scripts/run_experiments.py --exp exp2 --models ... --seeds 101,102,103
python3 scripts/finalize.py --exp exp2</pre></div>

    <h3 style="margin-top:2rem">Citation</h3>
    <p>If you use PI-Bench, please cite it:</p>
    <div class="console"><pre>@software{bao2026pibench,
  title   = {PI-Bench: Can Agents Run a Research Lab?},
  author  = {Bao, Zhiwei},
  year    = {2026},
  url     = {%%GITHUB%%},
  version = {1.0.0}
}</pre></div>
    <details class="disc" style="margin-top:1.4rem"><summary>References</summary><div class="body">
    <p style="font-size:.82rem;line-height:1.5">Backlund &amp; Petersson. Vending-Bench. arXiv:2502.15840, 2025. ·
    Chen, Narasimhan &amp; Liu. CEO-Bench. arXiv:2606.18543, 2026. ·
    Jimenez et al. SWE-bench. ICLR 2024. · Mialon et al. GAIA. ICLR 2024. ·
    Mussa &amp; Rosen. Monopoly and Product Quality. J. Econ. Theory 1978. ·
    Patwardhan et al. GDPval. arXiv:2510.04374, 2025. · Penrose AI. AccountingBench. 2025. ·
    Trivedi et al. AppWorld. ACL 2024. · Yao et al. &tau;-bench. arXiv:2406.12045, 2025. ·
    Zhou et al. WebArena. ICLR 2024.</p></div></details>
  </div>
</section>

<footer class="foot">
  <div class="inner">
    <b style="color:var(--ink)">PI-Bench</b> — a mechanistic, long-horizon benchmark for
    research-lab agency. Simulator, harness, adversarial test suite, and all agent trajectories
    open at <a href="%%GITHUB%%">github.com/zwbao/pibench ↗</a>.
    <div style="margin-top:.6rem">The closest prior benchmark to adopt this mechanistic,
    long-horizon shape is CEO-Bench (Chen et al., 2026); PI-Bench is its complement in an
    illiquid, delayed, people-driven research economy.</div>
  </div>
</footer>

<div class="tooltip" id="tip"></div>

<script>
const P = %%DATA%%;
const PAL = P.palette;
const $ = id => document.getElementById(id);
const tip = $("tip");
function showTip(html, x, y){ tip.innerHTML=html; tip.style.opacity=1;
  tip.style.left=Math.min(x+12, innerWidth-tip.offsetWidth-8)+"px"; tip.style.top=(y+12)+"px"; }
function hideTip(){ tip.style.opacity=0; }
function toggleTheme(){ const r=document.documentElement;
  const cur=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  r.setAttribute('data-theme', cur==='dark'?'light':'dark'); }
const SVGNS="http://www.w3.org/2000/svg";
function el(tag, attrs){ const e=document.createElementNS(SVGNS,tag);
  for(const k in attrs) e.setAttribute(k, attrs[k]); return e; }

/* ---------- leaderboard ---------- */
const COLS=[
  {k:'model',t:'Model',f:v=>v},
  {k:'impact',t:'Impact',f:v=>v==null?'—':v.toFixed(0),bar:true},
  {k:'seeds',t:'per-seed',f:v=>v?('<span class=seeds>'+v.map(x=>Math.round(x)).join(' / ')+'</span>'):'—',nosort:true},
  {k:'collapse',t:'collapse',f:(v,r)=>v+'/'+r.n},
  {k:'pubs',t:'pubs',f:v=>v==null?'—':v.toFixed(1)},
  {k:'grants',t:'grants',f:v=>v==null?'—':v.toFixed(1)},
  {k:'ppsy',t:'papers/yr',f:v=>v==null?'—':v.toFixed(2)},
  {k:'anticip',t:'anticip.',f:v=>v==null?'—':v.toFixed(2)},
  {k:'quit',t:'attrition',f:v=>v==null?'—':v.toFixed(2)},
  {k:'tokens',t:'tokens',f:v=>v==null?'—':v.toFixed(2)+'M'},
];
let sk='impact', sd=-1;
function renderLB(){
  const maxI=Math.max(...P.models.map(m=>m.impact||0),1);
  let rows=[...P.models];
  if(sk!=='seeds') rows.sort((a,b)=>(((a[sk]??-1e9)-(b[sk]??-1e9))*sd));
  const head='<tr>'+COLS.map(c=>`<th class="${c.k===sk?'active':''}" ${c.nosort?'':`onclick="sortLB('${c.k}')"`}>${c.t}${c.k===sk?(sd<0?' ▾':' ▴'):''}</th>`).join('')+'</tr>';
  const body=rows.map(r=>'<tr>'+COLS.map(c=>{
    let v=r[c.k]; if(c.k==='model') return `<td class=model>${v}</td>`;
    let inner=c.f(v,r);
    if(c.bar&&v!=null){ const w=Math.round(58*v/maxI); inner=`<span class=bar style="width:${w}px"></span>`+inner; }
    return `<td>${inner}</td>`; }).join('')+'</tr>').join('');
  const refs=P.refs.map(r=>'<tr class=ref>'+COLS.map(c=>{
    if(c.k==='model') return `<td class=model>${r.model}</td>`;
    if(c.k==='impact') return `<td>${r.impact.toFixed(0)}</td>`;
    if(c.k==='collapse') return `<td>${r.collapse}/${r.n}</td>`;
    if(c.k==='tokens') return `<td>${r.note}</td>`;
    return '<td>—</td>'; }).join('')+'</tr>').join('');
  $('lb').innerHTML=head+body+refs;
}
function sortLB(k){ if(k===sk) sd*=-1; else {sk=k; sd=-1;} renderLB(); }
renderLB();

/* ---------- line chart: cumulative citations over time ---------- */
const shortName = m => m.replace('anthropic/','').replace('openai/','');
let citeScale='linear';
const hidden=new Set();
function drawCites(){
  const box=$('c-cites'); box.querySelectorAll('svg').forEach(s=>s.remove());
  const W=920,H=380, mL=54,mR=16,mT=14,mB=30;
  const months=P.traj.months, ser=P.traj.series, base=P.traj.baseline;
  const vis=ser.filter(s=>!hidden.has(s.model));
  let maxY=1;
  vis.forEach(s=>s.cites.forEach(v=>maxY=Math.max(maxY,v)));
  if(base) base.forEach(v=>maxY=Math.max(maxY,v));
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`});
  const px=i=> mL+(W-mL-mR)*(i/(months.length-1));
  const isLog=citeScale==='log';
  const py=v=>{ if(isLog){ const lv=Math.log10(Math.max(1,v)), lm=Math.log10(Math.max(10,maxY));
      return H-mB-(H-mB-mT)*(lv/lm); } return H-mB-(H-mB-mT)*(v/maxY); };
  // gridlines + y ticks
  const ticks = isLog?[1,10,100,1000,10000].filter(t=>t<=maxY*1.2):[0,.25,.5,.75,1].map(f=>Math.round(f*maxY));
  ticks.forEach(t=>{ const y=py(t); svg.appendChild(el('line',{class:'grid',x1:mL,y1:y,x2:W-mR,y2:y}));
    const tk=el('text',{class:'tick',x:mL-8,y:y+3,'text-anchor':'end'}); tk.textContent=t>=1000?(t/1000)+'k':t; svg.appendChild(tk); });
  [1,12,24,36,48,60].forEach(m=>{ const x=px(m-1); const tk=el('text',{class:'tick',x:x,y:H-mB+16,'text-anchor':'middle'}); tk.textContent='m'+m; svg.appendChild(tk); });
  svg.appendChild(el('line',{class:'axis',x1:mL,y1:H-mB,x2:W-mR,y2:H-mB}));
  const yl=el('text',{class:'alab',x:14,y:H/2,transform:`rotate(-90 14 ${H/2})`,'text-anchor':'middle'}); yl.textContent='cumulative citations (mean)'; svg.appendChild(yl);
  // baseline
  if(base){ let d='M'+base.map((v,i)=>px(i)+','+py(v)).join(' L'); svg.appendChild(el('path',{class:'baseline',d})); }
  // series
  ser.forEach(s=>{ if(hidden.has(s.model)) return;
    let d='M'+s.cites.map((v,i)=>px(i)+','+py(v)).join(' L');
    const p=el('path',{class:'sline',d,stroke:PAL[s.colorIndex%PAL.length],'data-m':s.model}); svg.appendChild(p); });
  // hover crosshair
  const ch=el('line',{class:'crosshair',y1:mT,y2:H-mB,x1:0,x2:0,style:'opacity:0'}); svg.appendChild(ch);
  const ov=el('rect',{x:mL,y:mT,width:W-mL-mR,height:H-mB-mT,fill:'transparent'}); svg.appendChild(ov);
  ov.addEventListener('mousemove',e=>{ const r=svg.getBoundingClientRect();
    const sx=(e.clientX-r.left)/r.width*W; let i=Math.round((sx-mL)/(W-mL-mR)*(months.length-1));
    i=Math.max(0,Math.min(months.length-1,i)); ch.setAttribute('x1',px(i)); ch.setAttribute('x2',px(i)); ch.style.opacity=1;
    const rows=vis.map(s=>({m:shortName(s.model),v:s.cites[i],c:PAL[s.colorIndex%PAL.length]})).sort((a,b)=>b.v-a.v).slice(0,8);
    showTip('<b>month '+months[i]+'</b><br>'+rows.map(r=>`<span style="color:${r.c}">■</span> ${r.m}: ${r.v.toFixed(0)}`).join('<br>'), e.clientX, e.clientY); });
  ov.addEventListener('mouseleave',()=>{ ch.style.opacity=0; hideTip(); });
  box.insertBefore(svg, box.firstChild);
}
function drawCiteLegend(){
  const L=$('leg-cites'); L.innerHTML='';
  P.traj.series.forEach(s=>{ const b=document.createElement('button');
    b.className=hidden.has(s.model)?'off':''; b.innerHTML=`<span class=sw style="background:${PAL[s.colorIndex%PAL.length]}"></span>${shortName(s.model)}`;
    b.onclick=()=>{ if(hidden.has(s.model)) hidden.delete(s.model); else hidden.add(s.model); drawCites(); drawCiteLegend(); };
    L.appendChild(b); });
  const bl=document.createElement('button'); bl.style.cursor='default';
  bl.innerHTML='<span class=sw style="background:var(--muted)"></span>baseline'; L.appendChild(bl);
}
document.querySelectorAll('#c-cites .ctrl button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('#c-cites .ctrl button').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); citeScale=b.dataset.scale; drawCites(); });
drawCites(); drawCiteLegend();

/* ---------- range plot: per-seed Impact spread on a log axis ---------- */
function drawStrip(){
  const box=$('c-strip'); box.querySelectorAll('svg').forEach(s=>s.remove());
  const rows=[...P.traj.series].map(s=>({m:s.model,seeds:[...s.seedsImpact].sort((a,b)=>a-b),ci:s.colorIndex}))
    .filter(r=>r.seeds&&r.seeds.length).sort((a,b)=>{
      const ma=a.seeds.reduce((x,y)=>x+y,0)/a.seeds.length, mb=b.seeds.reduce((x,y)=>x+y,0)/b.seeds.length; return mb-ma; });
  const W=920, rh=42, mL=150, mR=34, mT=34, mB=30, zoneW=30; // zoneW = a "0 / collapsed" lane left of x=1
  const H=mT+mB+rows.length*rh;
  let maxV=10; rows.forEach(r=>r.seeds.forEach(v=>maxV=Math.max(maxV,v)));
  const lmax=Math.log10(maxV*1.4);
  const x1=mL+zoneW;                                   // where the log axis (value 1) begins
  const px=v=> v<1 ? mL+zoneW*0.5 : x1+(W-x1-mR)*(Math.log10(v)/lmax);
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`});
  // alternating row bands
  rows.forEach((r,i)=>{ if(i%2===0) svg.appendChild(el('rect',{x:0,y:mT+i*rh,width:W,height:rh,fill:'var(--surface-2)',opacity:.5,rx:4})); });
  // "0" zone divider + label
  svg.appendChild(el('line',{class:'grid',x1:x1,y1:mT-8,x2:x1,y2:H-mB}));
  const z=el('text',{class:'tick',x:mL+zoneW*0.5,y:mT-12,'text-anchor':'middle'}); z.textContent='0'; svg.appendChild(z);
  // log gridlines + ticks
  [1,10,100,1000,10000].filter(t=>t<=maxV*1.4).forEach(t=>{ const x=px(t);
    svg.appendChild(el('line',{class:'grid',x1:x,y1:mT-8,x2:x,y2:H-mB}));
    const tk=el('text',{class:'tick',x:x,y:mT-12,'text-anchor':'middle'}); tk.textContent=t>=1000?(t/1000)+'k':t; svg.appendChild(tk); });
  rows.forEach((r,i)=>{ const cy=mT+i*rh+rh/2, col=PAL[r.ci%PAL.length];
    const nm=el('text',{x:mL-12,y:cy+4,'text-anchor':'end',style:'font-family:var(--mono);font-size:11px;fill:var(--ink-soft)'}); nm.textContent=shortName(r.m); svg.appendChild(nm);
    // faint range connector from min to max seed
    const lo=r.seeds[0], hi=r.seeds[r.seeds.length-1];
    svg.appendChild(el('line',{x1:px(lo),y1:cy,x2:px(hi),y2:cy,stroke:col,'stroke-width':2,opacity:.28,'stroke-linecap':'round'}));
    // mean tick (diamond)
    const mean=r.seeds.reduce((a,b)=>a+b,0)/r.seeds.length, mx=px(mean);
    svg.appendChild(el('path',{d:`M${mx},${cy-8} L${mx+6},${cy} L${mx},${cy+8} L${mx-6},${cy} Z`,fill:'none',stroke:col,'stroke-width':2,opacity:.9}));
    // dots with vertical jitter so equal/overlapping values separate
    const seen={};
    r.seeds.forEach(v=>{ const xk=Math.round(px(v)); const k=xk in seen?++seen[xk]:(seen[xk]=0);
      const jitter=(k===0?0:(k%2? -1:1)*Math.ceil(k/2)*7);
      const c=el('circle',{class:'dot',cx:px(v),cy:cy+jitter,r:5.5,fill:col});
      const lab=v<1?'0 (collapsed / no output)':v.toFixed(0);
      c.addEventListener('mouseenter',e=>showTip(`<b>${shortName(r.m)}</b><br>seed Impact: ${lab}`,e.clientX,e.clientY));
      c.addEventListener('mouseleave',hideTip); svg.appendChild(c); }); });
  const xl=el('text',{class:'alab',x:(x1+W-mR)/2,y:H-6,'text-anchor':'middle'}); xl.textContent='Impact per seed (log scale) · dot = one run · line = spread · ◇ = mean'; svg.appendChild(xl);
  box.appendChild(svg);
}
drawStrip();
</script>
"""

if __name__ == "__main__":
    build()
