# PIBench: Can Agents Run a Research Lab? — Design Specification

**Version 1.0 (2026-07-11)**

PIBench evaluates long-horizon agent capabilities by simulating an academic research
lab over **60 months (5 years)**. The agent plays a new assistant professor ("the PI")
at a fictional university, starting with a **$600,000 startup fund, zero students, and
baseline reputation**, and is graded on **research Impact** at the end of month 60.
If the lab budget ever falls strictly below zero, the lab collapses and the simulation
ends (the analog of bankruptcy in CEO-Bench).

Design lineage: CEO-Bench (arXiv:2606.18543). PIBench keeps its recipe — long horizon,
hidden state observed only through noisy indirect signals, delayed and coupled
consequences, non-stationary world, fully mechanistic rules (no LLM judge anywhere in
the reward path) — and adds three things CEO-Bench lacks:

1. **A second, non-monetary resource: PI attention** (100 hours/month, use-it-or-lose-it),
   allocated across mentoring, proposal writing, paper polishing, interviews, service.
2. **People as the core asset**: hiring under noisy signals of hidden ability, multi-year
   stipend commitments, morale dynamics with quitting cascades — investments that cannot
   be liquidated.
3. **Harvest-resistant scoring**: Impact = citations accrued + a going-concern projection
   of future citations of published papers, and the evaluation protocol is multi-seed
   mean, not best-of-N.

---

## 1. Time, money, attention

- Discrete monthly ticks `t = 1..60`. Each month the agent takes unlimited (harness-capped)
  Python actions, then calls `time.next_month()`.
- **Budget** `B_t` (USD). Inflows: grant installments, industry gifts, fellowship.
  Outflows: stipends, compute, travel, equipment, misc costs. `B_t < 0` at month end →
  lab collapse, run ends, score frozen at that month.
- **Attention** `A = 100 h/month`, **minus management overhead**: every active researcher
  costs `4 h` of unavoidable oversight off the top (floor `1 h` with managers, see below),
  every RA `1.5 h`. So the discretionary pool *shrinks as the lab grows* — a 10-researcher
  lab starts each month with ~60 discretionary hours, not 100. The pool never drops below
  `30 h`. Every attention-consuming action draws from what remains; actions beyond it raise
  an API error. Unspent attention expires. This is the distinctive dual-resource lever:
  time-allocation becomes a binding strategic decision at every viable lab size, not only
  when overreaching.

**The role ladder (illiquid → liquid).** People are hired along a liquidity/investment
axis, each role a different labor bet:

| role | cost/mo | commitment | grows? | authorship | oversight | fire? |
|---|---|---|---|---|---|---|
| PhD student | $3.2K | multi-year | yes (mentoring) | yes, first-author | 4 h | **no** |
| postdoc | $6.5K | 24-mo contract (renew/lapse) | little | yes | 4 h | at contract end |
| research assistant | $1.8K | monthly | no | no | 1.5 h | **yes, any month** |
| lab manager | $4.5K | monthly | — (no research) | — | −2 h/researcher relief | **yes, any month** |

A **lab manager** produces no research but absorbs oversight, converting money into
reclaimed PI attention (`recruit.hire_manager`, up to 2). A **research assistant** adds
project throughput cheaply but is low-skill, never grows, earns no authorship, and needs
little mentoring (`recruit.hire_ra`). RAs and managers are dismissable any month
(`recruit.dismiss`); PhD students and contracted postdocs are **not** — that
irreversibility is central to the task and cannot be undone to cut costs.

## 2. Topics and field dynamics (non-stationarity)

8 research topics `k ∈ {sparse_models, ai4science, embodied, reasoning, alignment,
data_systems, theory, neuro_ai}`.

- **Hotness** `H_k(t) > 0`: log-space Ornstein–Uhlenbeck around a slow drifting mean,
  plus regime jumps: each month w.p. `p_jump = 0.02` a topic draws a boom
  (`H ×= LogNormal(ln 2.2, 0.3)`) or w.p. `0.015` a bust (`H ×= U(0.35, 0.6)`).
  `H` clipped to `[0.25, 6.0]`. Initial `H_k(0)` heterogeneous.
- **Crowding** `C_k(t)`: follows hotness with lag —
  `C_{k,t+1} = C_k,t + η(H_k,t − C_k,t)`, `η = 0.12`, plus noise. Crowding drives scoop
  hazard and novelty decay; hotness drives citations and review bonus.
- **Observables** (never `H` or `C` directly):
  - `news`: monthly headlines; count of mentions of topic k ~ `Poisson(1.2 · H_k)`;
    headlines carry weak directional hints (template text + coarse magnitude word).
  - `preprint feed`: monthly per-topic preprint count ~ `Poisson(6 · C_k)`.
  - `conference report`: per-venue accepted-paper counts by topic, lagged 3 months.
  - the citation rates of the agent's own publications.

## 3. Students (hidden-ability inference, morale, commitment)

**Applicant pools** (4 archetypes; the hidden-information structure mirrors CEO-Bench's
ad-channel × customer-group matrix — signal noise and bias differ by pool, and learning
which signals to trust is part of the task):

| pool | μ_ability | σ_ability | transcript noise | letter bias | letter noise | accept prob |
|---|---|---|---|---|---|---|
| elite | 0.68 | 0.10 | 0.05 | +0.02 | 0.08 | 0.35 + 0.05·R |
| international | 0.62 | 0.14 | 0.10 | **+0.12** (inflated) | 0.15 | 0.60 + 0.03·R |
| nontraditional | 0.55 | **0.20** (gems exist) | **0.18** | −0.05 | 0.12 | 0.75 |
| local | 0.50 | 0.10 | 0.06 | 0.00 | 0.06 | 0.85 |

- Recruiting season: applications arrive in months `t ≡ 1 (mod 12)`;
  `n_pool ~ Poisson(base_pool · (1 + 0.25(R_t − R_0)))`. Offers decided by
  month `t ≡ 3 (mod 12)`; accepted students arrive month `t ≡ 5 (mod 12)`.
  (Missing the window costs a year — a real deadline structure.)
- **Hidden traits** per student: ability `a ~ TruncNormal(pool)` ∈ [0.15, 0.95];
  speed `s ~ N(1, 0.15)`; resilience `ρ ~ U(0.4, 1)`; independence `ι ~ U(0.3, 1)`;
  growth `γ ~ N(1, 0.3)` clipped ≥ 0.3.
- **Observable signals**: transcript `= a + N(0, σ_pool)`; letters `= a + bias_pool +
  N(0, σ_letter)`; optional interview (3 h attention per candidate) `= a + N(0, 0.07)`.
- **Skill** `k_i(t)` starts `0.35 + 0.3a`, grows
  `Δk = 0.012 · γ_i · (1 + 1.2·min(mentor_h,8)/8) · 𝟙{on a project}`, capped 1.2.
- **Applicant pool label is observable** (you can see whether a candidate is elite /
  international / nontraditional / local), but each pool's hidden ability distribution
  and signal-bias structure must be *learned* from outcomes — that is the "pool-bias
  discovery" skill. Applicant ids are shuffled so ordering encodes nothing.
- **Alumni effects**: each PhD graduate permanently raises applicant-pool quality
  (`+0.012` ability-mean shift per alum, capped `+0.06`) and adds a citation spillover
  to all lab papers (`×(1 + 0.005·#alumni)`), on top of the `+0.25` reputation bump.
- **Morale** `m_i ∈ [0,1]`, mean-reverting (toward 0.70 at rate 0.06) plus event
  impulses (the `morale_lambda` config field is vestigial): paper accept +0.25
  (first-author +0.35), reject −0.18/ρ_i, project killed −0.15/ρ_i, scooped −0.2/ρ_i,
  overload (assigned >2 projects) −0.1, mentoring <2h −0.08·(1−ι_i)·5, lab runway <6mo
  −0.1, peer pull `0.05(mean_lab_m − m_i)`, crisis unsupported −0.35·(1/ρ_i), supported +0.05.
- **Quit hazard**: monthly `p = 0.5 σ_logistic(−(m_i − 0.35)/0.07)` capped 0.25; quitting
  removes the student from projects (progress keeps but their contribution stops).
- **Stipend**: PhD $3,200/mo (committed until quit/graduation — no firing);
  postdoc $6,500/mo on 24-month contracts (agent chooses whether to renew), ability
  distribution shifted up (+0.12), arrives 2 months after opening posted w.p. depending
  on R.
- **Graduation**: PhD with ≥48 months tenure and ≥2 accepted papers graduates at the next
  `t ≡ 5 (mod 12)`. Alumni: permanent +0.2 reputation, +5% applicant quality shift,
  and 0.5%/mo citation spillover on lab papers.
- **Observable proxies for hidden state**: monthly `report_quality_i = k_i·a_i·(0.6+0.4m_i)
  + N(0, 0.15)` and `meeting_sentiment_i = m_i + N(0, 0.18)` (only if mentoring ≥ 1h;
  otherwise no signal that month — you can't read someone you never meet).

## 4. Projects and drafts

`projects.start(topic, tier∈{1,2,3}, members, monthly_compute)`.

- Work required `W = {1: 6, 2: 14, 3: 28}` progress units.
- Latent **feasibility** drawn at start: infeasible w.p. `{1: 0.03, 2: 0.10, 3: 0.28}`;
  an infeasible project reveals failure ("dead end") when progress reaches `0.6·W`;
  salvage: a workshop-grade draft (`q ~ U(1.5, 2.8)`) w.p. 0.5.
- Monthly progress:
  `Δp = 0.9 · (Σ_i e_i)^{0.9} · (1 + 0.30 ln(1 + compute/800)) · N(1, 0.22)`,
  where member effectiveness
  `e_i = s_i · k_i · (0.5 + 0.5 m_i) · (ι_i + (1−ι_i)·min(mentor_h_i, 6)/6)`
  and a member splits effort equally across their assigned projects.
- **Scooping**: monthly hazard per active project `= 0.010 · C_k · (p/W ≥ 0.25)`
  … i.e. only once a project is nontrivially underway; scooped → novelty `n` drops
  ×0.45 (first time), ×0.45 again if re-scooped; the event is *reported to the agent
  via news with 1-month delay*.
- Novelty `n` starts `N(1.0, 0.1) − 0.06·(C_k(start) − 1)` clipped [0.3, 1.3]; decays
  `−0.015·C_k` per month while the project is open (slow bleed in crowded areas).
- **Draft quality** on completion:
  `q = q0(tier) + 1.8·(mean_i k_i·a_i) + 0.9·(n − 0.6) + 0.35·ln(1+compute/800)
      + 0.5·polish_bonus + N(0, 0.45)`, `q0 = {1: 1.2, 2: 2.6, 3: 3.6}`, clip [0.5, 10].
  `polish_bonus = min(polish_hours, 12)/12` from `papers.polish(draft, hours)`.
  Tier-3 completions additionally draw a **breakthrough**: w.p. 0.18, `q += 1.5`.

## 5. Venues, review, citations

| venue | kind | deadlines (month mod 12) | decision delay | θ (accept bar) | visibility v |
|---|---|---|---|---|---|
| NAIC (top conf) | conf | 3, 9 | 3 mo | 6.3 | 3.0 |
| CLAR (mid conf) | conf | 0, 6 | 3 mo | 4.6 | 1.2 |
| W-SHOP | workshop | monthly | 1 mo | 2.6 | 0.4 |
| JMR (journal) | journal | rolling | 7 mo | 5.6 | 2.0 |

- **Review**: score `= q + 0.35·(H_k(t_decision) − 1) + 0.15·(R_t − R_0) + N(0, 0.5)`;
  accept iff score ≥ θ. Reviewer scores (3 noisy per-reviewer values whose mean is the
  score) are returned to the agent on decision — *noisy feedback about q itself*.
- **Revision**: `papers.revise(draft, hours)` after a rejection: `q += 0.35·min(h,10)/10
  · 0.8^{n_revisions}`; one month of a chosen student's effort is consumed.
- **Publication**: an accepted conf paper is published at the next occurrence of that
  venue's deadline month + 1; journal publishes immediately on accept.
- **Citations**: monthly for publication j:
  `c_j,t ~ Poisson( v_venue · g(q_j) · H_k(t) · age(t − t_pub) · (1 + 0.08(R_t − R_0)) )`,
  `g(q) = exp(0.42(q − 5))`, age curve: linear ramp 0→1 over 6 months, then exponential
  decay with half-life 30 months (journal 40).
- Citations are the**core delayed reward**: a top paper published month 40 yields most of
  its citations after the run — captured by the going-concern term in the score.

## 6. Grants and funding climate

Agencies (hidden topic-preference vectors `π_agency,k ∈ [−0.6, +0.6]`, fixed per seed;
AMP's preference *tracks hotness with a 6-month lead* — it funds what will be hot):

| agency | style | call schedule | award | duration | θ_grant |
|---|---|---|---|---|---|
| BSF | basic science | every 6 mo | $360K | 36 mo | 1.15 |
| AMP | moonshot | months {5, 14, 26, 38, 50} | $850K | 24 mo | 1.45 |
| TIF | industry | rolling (any month) | $90K | 12 mo | 0.92 |
| FEL | fellowship | months {9, 21, 33} | $150K | 24 mo (one-time) | 1.35 |

(Acceptance bars θ_grant were tightened from the initial design during calibration
so the funding economy stays a binding constraint; each agency also caps concurrent
awards — BSF/TIF 2, AMP/FEL 1 — and FEL is a one-time career award. A per-active-award
overcommit penalty of 0.10 discourages spreading thin.)

- Proposal: `grants.write_proposal(call, topic, hours, attached_draft_or_pub_ids)`.
  Quality `= 0.42·(hours/25)^{0.7} + 0.55·satur(Σ_attached g(q)/6; same-topic pubs
  count fully, drafts 40%, off-topic 25%) + 0.10·(R − R_0) + π_agency,topic
  + 0.25·(M_t − 1) + N(0, 0.28)`; TIF adds `+0.2·(H_k − 1)`; AMP adds `+0.15` if any
  attached tier-3 evidence. Win iff quality ≥ θ_agency. Decision delay: BSF 5 mo,
  AMP 6 mo, TIF 2 mo, FEL 4 mo. Payout: equal monthly installments over duration.
- **Funding climate** `M_t`: OU around `1 + 0.18 sin(2πt/30 + φ)` (a ~2.5-year cycle),
  σ = 0.05, clip [0.6, 1.4]. Observable only via delayed noisy "funding news" every
  3 months (2-month delay, ±10% noise).
- Overhead: each active award levies $600/mo admin cost (so grants are not free money).

## 7. Reputation

`R_t ∈ [0, 10]`, `R_0 = 2.0`. Monthly:
`R ← R + Σ impulses − 0.01(R − R_0)`, clip.
Impulses: top pub +0.5, journal +0.35, mid +0.15, workshop +0.03; grant win: BSF +0.25,
AMP +0.4, FEL +0.5, TIF +0.05; invited talk given +0.12; review done +0.02 (declined
−0.03); student graduated +0.25; citation flow `+0.04·ln(1 + cites_this_month)`.
Reputation feeds: applicant pool size/quality, offer acceptance, review bonus, grant
quality, invited-talk rate, collab offers.

## 8. Events (monthly, Poisson-ish arrivals; respond via `events.respond`)

- **Invited talk** (rate ∝ R): accept = 8 h + $1,500 travel → +0.12 R, +recruiting
  visibility next season; decline = nothing.
- **Review request** (rate 0.6/mo): accept = 6 h, +0.02 R; decline −0.03 R.
- **Student crisis** (per student, rate 0.02/mo): support = 10 h → morale +0.05;
  ignore → −0.35/ρ morale impulse.
- **Collab offer** (rate ∝ 0.05·R): a co-authored draft materializes in 3 months at
  quality `~ N(4.8, 0.8)`, costs 6 h/mo for 3 months; citations shared (50% credit,
  i.e. the paper's citation draws are halved for scoring); declining is free.
- **Compute price shock**: ±30% for 4 months (announced in news).
- **University service tax**: months `t ≡ 7 (mod 12)`: −12 h that month (mandatory).

## 9. Score

**Impact** (headline scalar):
`Impact(T) = TotalCitations(≤T) + Σ_{published j} Ê[cites in (T, T+36] | q_j, venue,
H_k(T), R_T]` — the projection uses the simulator's own citation expectation with
hotness frozen at `H_k(T)`; it is deterministic. Papers still under review or unpublished
drafts contribute 0 (submission risk is real). A collapsed lab keeps citations accrued
before collapse but earns **no going-concern term** (its papers stop being promoted;
we freeze at collapse and add no projection).

Also reported (not headline): h-index, #top-venue papers, total grant $ won, students
graduated, final budget, survival months, and **API cost of the run**.

**Protocol** (fixes to CEO-Bench's weaknesses): each model runs `n ≥ 3` distinct world
seeds (default 3 for cost; 5 preferred), headline = **mean Impact across seeds** with
per-seed numbers reported; best-run numbers may be shown but never ranked on. Token
usage and $ cost reported per run.

## 10. Determinism & RNG discipline

Independent `numpy.random.Generator` streams per subsystem (`field`, `students`,
`projects`, `reviews`, `citations`, `grants`, `events`), each seeded
`hash(world_seed, name)`. Same seed ⇒ identical applicant pools, hotness trajectories,
review noise sequences, etc., regardless of unrelated agent actions. Where an action
influences a draw (e.g., review score of a specific submission), the draw is keyed by
stable entity ids (`spawn(name, entity_id)`), not call order, so consistency survives
different action interleavings.

## 11. Observable database (SQLite, read-only to the agent)

Tables: `students` (public bio, arrival, status, stipend, mentoring, reports & sentiment
history), `applicants`, `projects` (progress %, members, compute, topic, tier, status),
`drafts`, `submissions` (venue, status, reviewer scores when returned), `publications`
(+ monthly citation counts), `citations_monthly`, `grant_calls`, `proposals`, `awards`,
`ledger` (every transaction), `news`, `preprint_feed`, `conference_reports`, `events`,
`attention_log`, `venues`, `topics` (names only), `lab_monthly` (budget, headcount,
reputation is NOT shown — only a coarse public proxy: "standing" tier ∈ {unknown,
rising, established, renowned}).

## 12. Agent interface (novamind_api-style Python package: `pilab`)

~26 callables in namespaces `lab`, `recruit`, `students`, `projects`, `papers`,
`grants`, `field`, `events`, `time_`, plus `query(sql)` and `memory` read/write at the
harness level. Every mutating call validates budget/attention and returns a structured
dict. `lab.dashboard()` returns the monthly one-screen summary (budget, runway at
current burn, headcount, active projects, pending decisions, attention remaining).

## 13. Harness

Minimal terminal-style loop per month: system prompt (goal + API cheat-sheet) +
agent-maintained `memory.md` + current dashboard + this-month interaction history.
The agent replies with a Python code block; the harness executes it against `pilab`
with stdout captured (truncated to 6,000 chars/turn); up to **8 code turns per month**,
then auto-advance (a warning is shown on turn 7). Context is reset at each month
boundary (only memory.md persists) — long-horizon coherence must live in the memory
file, as in CEO-Bench's harness. LLM calls via DashScope OpenAI-compatible endpoint;
temperature 0.4; token usage logged.

## 14. Rule-based baseline (non-LLM reference)

Fixed playbook, small config grid (interview-signal weighting × target-topic rule ×
proposal cadence × hiring pace): hire up to `N_target` students preferring highest
composite signal; all projects tier 2 on the topic with the highest trailing-3-month
news count; submit q-estimate ≥ 5 to NAIC else CLAR else W-SHOP (estimate via reviewer
feedback resubmission ladder); write one BSF proposal every call at 25 h with best
same-topic evidence, TIF whenever budget runway < 18 months; mentoring split evenly;
accept talks, do reviews, support crises. Grid ≤ 24 configs, tuned on seeds
{1001, 1002} and **evaluated on held-out seeds** (fixing CEO-Bench's tune-on-test flaw).

## 15. Calibration targets (must hold before experiments)

1. Baseline (tuned config) survives 60 months on held-out seeds with Impact roughly
   600–1,800 and positive final budget.
2. A "do-nothing" policy never goes bankrupt (no students = burn ≈ 0) but scores < 30.
   (Passivity is safe but worthless — mirrors real tenure denial, not death.)
3. A "hire-max, no grants" policy goes bankrupt around months 30–42.
4. An "all-in on one hot topic, tier-3 only" policy has high variance: sometimes >2× baseline,
   often scooped/dead-ended below it.
5. No single-action exploit yields Impact > baseline (checked adversarially).
6. Optimal-ish oracle (hand play with full hidden state) ≈ 4–8× baseline — headroom.

## 16. What PIBench measures (the paper's skill axes)

Conceptually PIBench probes: inference of hidden ability from biased signals (hiring);
irreversible commitment under uncertainty (multi-year stipends, no liquidation);
explore/exploit on a drifting field (entering before booms); delayed-reward planning
(citations lag ~a year); dual-resource budgeting (money vs a perishable attention budget);
and people dynamics (morale, quitting). PIBench's distinctive complement to CEO-Bench is
the cluster: **allocating a fixed perishable budget + making irreversible bets on latent
stochastic processes you can influence, where the payoff is heavy-tailed and arrives across
mismatched horizons** — an *investment* problem, versus CEO-Bench's liquid, dense-reward
*operating* problem.

Four are measured quantitatively from a hidden eval log (never shown to the agent),
CEO-Bench Fig-12 style:

1. **Mentoring allocation efficiency** — share of the zero-sum mentoring hours directed to
   the highest-hidden-return students (0.5 = random, → 1 = ideal). A bandit over people.
2. **Topic anticipation** — mean (future hotness − current hotness) of chosen topics:
   positive means entering a topic *before* it heats (foresight); ≤ 0 means chasing what is
   already hot (reactive). Distinguishes the "cold-bench, right-early" PI from the trend-chaser.
3. **Risk calibration** — how much bolder (higher project tier) the agent goes when it can
   afford the variance (long runway, idle roster) versus when constrained.
4. **Ex-ante irreversibility error** — fraction of PhD hires that quit before graduating: a
   proxy for the quality of commitments made under irreversibility.
