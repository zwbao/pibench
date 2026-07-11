# PIBench: Can Agents Run a Research Lab?

A long-horizon benchmark where an LLM agent plays a new professor running an academic
research lab for **60 simulated months**. Starting with a $600K fund, no students, and no
reputation, the agent hires students whose talent is hidden, bets on research topics before
they boom, chases grants, and shepherds papers to citations — under two budgets at once:
**money and the PI's own attention**. The world is fully **mechanistic** (no LLM judge in
the reward path), partially observable, non-stationary, and full of delayed, coupled
consequences.

**Headline score — Impact** = citations accrued + a deterministic going-concern projection
of published papers' future citations. Budget below zero ⇒ the lab collapses. The score is
built so that abandoning the lab to hoard cash earns nothing.

See `SPEC.md` for the complete world mechanics and `paper/` for the write-up (paper +
standalone research site).

## What it tests

An *investment* problem, not an operating one: allocating a perishable budget and making
irreversible bets on latent processes whose payoff is heavy-tailed and arrives across
mismatched horizons.

1. Inferring hidden ability from noisy, differently-biased signals (hiring).
2. Irreversible multi-year commitments — students cannot be fired.
3. Explore/exploit on a drifting research field (booms, busts, crowding, scooping).
4. Delayed rewards — citations lag actions by 1–2 years; grants by months.
5. Dual-resource budgeting — money AND 100 h/month of attention (which shrinks as the lab grows).
6. People dynamics — morale, quitting, mentoring as a zero-sum bandit.

## The role ladder (illiquid → liquid)

| role | cost/mo | commitment | grows | authors | fire? |
|---|---|---|---|---|---|
| PhD student | $3.2K | multi-year | yes | first-author | **no** |
| postdoc | $6.5K | 24-mo contract | little | yes | at contract end |
| research assistant | $1.8K | monthly | no | no | **yes** |
| lab manager | $4.5K | monthly | — | — | **yes** |

A lab manager buys back PI attention (money → time); an RA adds cheap throughput. Students
and contracted postdocs cannot be dismissed — that irreversibility is central to the task.

## Layout

```
pibench/            simulator: world.py (engine), api.py (agent surface),
                    db.py (observable SQLite), baseline.py (rule-based PI),
                    config.py, entities.py, rng.py
pibench/harness/    minimal terminal harness + sandbox + LLM client (Bailian + OpenRouter)
scripts/            smoke, calibrate, ablate, oracle, run_agent, run_experiments,
                    analyze, build_paper, build_site, finalize
tests/              invariant + sandbox penetration tests
paper/              PIBENCH.md, index.html (paper), leaderboard/skills/refs/ablations JSON, figs/
site/               index.html — the standalone, deployable research site
```

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in TONGYI_API_KEY and/or OPENROUTER_API_KEY

python3 scripts/smoke.py                 # engine sanity + determinism
python3 tests/test_invariants.py         # invariants
python3 tests/test_sandbox.py            # sandbox penetration tests
python3 scripts/calibrate.py all         # scripted policies + baseline grid

# one LLM episode — provider auto-routes by model id (a "/" ⇒ OpenRouter, else Bailian)
python3 scripts/run_agent.py --model qwen3.7-max --seed 101 --months 60
python3 scripts/run_agent.py --model anthropic/claude-opus-4.8 --seed 101 --months 60

# the full matrix, then regenerate figures + paper + site
python3 scripts/run_experiments.py --exp exp2 \
  --models "qwen3.7-max,glm-5.2,anthropic/claude-opus-4.8,openai/gpt-5.6-sol" \
  --seeds 101,102,103 --parallel 12
python3 scripts/finalize.py --exp exp2
```

## Evaluation protocol

- Every model runs the **same seeds**; the headline is the **mean across seeds** — never a
  best-of-N. Per-seed values are reported because the variance is heavy-tailed and part of
  the finding.
- The rule-based baseline is tuned on **held-out** seeds it never sees at test time.
- **Token cost** is reported beside every score, so "spent more thinking" is not confused
  with "is more capable."
- The agent knows the horizon; the score's projection term removes any incentive to stop
  publishing near the end.

## Harness contract

Context resets every simulated month; only the agent's self-maintained memory file (≤6 KB)
persists — long-horizon coherence must live in what it writes down. Each month the agent
gets up to eight Python code turns against a hardened sandbox (AST sanitizer + facades so
the hidden world is unreachable), then the clock auto-advances.

## Reproducibility & validation

Independent per-subsystem RNG streams plus entity-keyed draws make every run exactly
reproducible (same seed + policy ⇒ identical outcome) and ensure unrelated actions cannot
shift another subsystem's result. Before experiments, the simulator and harness passed a
multi-agent adversarial review across seven lenses (spec conformance, correctness, hidden-
information leaks, economic and scoring exploits, determinism, harness security); the
findings and fixes ship with the code.

## License

MIT.
