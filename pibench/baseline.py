"""Rule-based baseline PI: a fixed playbook with a small config grid.

It uses no hidden information and no learning; it reads only what the API
exposes. Mirrors CEO-Bench's non-LLM heuristic baseline, but is tuned on
training seeds and evaluated on held-out seeds (see scripts/calibrate.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from .api import LabAPI
from .world import ApiError, World


@dataclass
class BaselineConfig:
    n_target_students: int = 4       # hire until this many active members
    hires_per_season: int = 2
    use_interview: bool = True
    tier: int = 2
    compute: float = 1500.0
    mentor_hours: float = 5.0
    proposal_hours: float = 25.0
    polish_hours: float = 8.0
    topic_rule: str = "news"         # news | fixed
    fixed_topic: str = "reasoning"
    min_runway_for_hiring: float = 18.0


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ApiError:
        return None


def hottest_topic(api: LabAPI, fallback: str) -> str:
    counts: dict[str, int] = {}
    for x in api.field.news(40):
        if x["kind"] == "field" and x["topic"]:
            counts[x["topic"]] = counts.get(x["topic"], 0) + 1
    return max(counts, key=counts.get) if counts else fallback


def run_baseline(seed: int, cfg: BaselineConfig | None = None, months: int = 60) -> dict:
    """Convenience wrapper: build a world, play the baseline, return its summary."""
    return run_baseline_world(seed, cfg, months).summary()


def run_baseline_world(seed: int, cfg: BaselineConfig | None = None, months: int = 60):
    """Build a world and play the baseline on it; return the World (so callers can
    read monthly_stats / eval_snapshot). This is the SINGLE source of the baseline
    policy — analysis code must call it, never re-implement the loop."""
    cfg = cfg or BaselineConfig()
    w = World(seed)
    w.cfg.months = months
    play_baseline(LabAPI(w), w, cfg)
    return w


def play_baseline(api: LabAPI, w: World, cfg: BaselineConfig | None = None):
    """The rule-based PI policy loop, run to completion on an existing world/api."""
    cfg = cfg or BaselineConfig()
    while not w.finished:
        m = w.month
        dash = api.lab.dashboard()
        runway = dash["runway_months"] if dash["runway_months"] is not None else 99

        # ---- recruiting
        if m % 12 == 1:
            apps = api.recruit.applicants()
            active = [s for s in api.students.list() if s["status"] == "active"]
            want = min(cfg.hires_per_season,
                       max(0, cfg.n_target_students - len(active)))
            if runway < cfg.min_runway_for_hiring:
                want = 0
            if want and apps:
                ranked = sorted(apps, key=lambda a: -(a["transcript"] + a["letter"]))
                shortlist = ranked[:2 * want + 2]
                if cfg.use_interview:
                    _safe(api.recruit.interview, [a["id"] for a in shortlist])
                    apps2 = api.recruit.applicants()
                    by_id = {a["id"]: a for a in apps2}
                    def score(a):
                        a = by_id.get(a["id"], a)
                        iv = a.get("interview")
                        return (0.6 * iv + 0.25 * a["transcript"] + 0.15 * a["letter"]
                                if iv is not None else a["transcript"])
                    shortlist = sorted(shortlist, key=lambda a: -score(a))
                for a in shortlist[:want + 1]:  # over-offer by one (some decline)
                    _safe(api.recruit.offer, a["id"])

        # ---- mentoring (even split, capped)
        active = [s for s in api.students.list() if s["status"] == "active"]
        if active:
            per = min(cfg.mentor_hours, 60.0 / len(active))
            _safe(api.students.set_mentoring, {s["id"]: per for s in active})

        # ---- projects: keep everyone on exactly one active project
        proj = [p for p in api.projects.list() if p["status"] == "active"]
        busy = {sid for p in proj for sid in p["members"]}
        idle = [s["id"] for s in active if s["id"] not in busy]
        if idle:
            topic = (hottest_topic(api, cfg.fixed_topic)
                     if cfg.topic_rule == "news" else cfg.fixed_topic)
            for i in range(0, len(idle), 2):
                _safe(api.projects.start, topic, cfg.tier, idle[i:i + 2], cfg.compute)

        # ---- papers: polish then submit via a quality ladder
        for d in api.papers.drafts():
            if d["status"] != "available":
                continue
            if d["polish_hours"] == 0 and not d["salvage"]:
                _safe(api.papers.polish, d["id"], cfg.polish_hours)
            rejected_venues = {s["venue"] for s in api.papers.submissions()
                               if s["draft"] == d["id"] and s["status"] == "reject"}
            if d["salvage"]:
                ladder = ["W-SHOP"]
            elif d["revisions"] == 0 and not rejected_venues:
                ladder = ["CLAR", "W-SHOP"]
            else:
                ladder = ["CLAR", "W-SHOP"]
            if d["tier"] >= 2 and not rejected_venues and not d["salvage"]:
                ladder = ["NAIC"] + ladder
            ladder = [v for v in ladder if v not in rejected_venues] or ["W-SHOP"]
            if rejected_venues and d["revisions"] == 0:
                _safe(api.papers.revise, d["id"], 8)
            for v in ladder:
                if _safe(api.papers.submit, d["id"], v):
                    break

        # ---- grants
        pubs = api.papers.publications()
        drafts = api.papers.drafts()
        topic = hottest_topic(api, cfg.fixed_topic) if cfg.topic_rule == "news" \
            else cfg.fixed_topic
        for call in api.grants.calls():
            if call["agency"] == "TIF" and runway > 24:
                continue
            evidence = [p["id"] for p in pubs if p["topic"] == topic][:4] \
                or [p["id"] for p in pubs][:4] \
                or [d["id"] for d in drafts if d["status"] == "available"][:2]
            _safe(api.grants.propose, call["id"], topic, cfg.proposal_hours, evidence)

        # ---- events: accept talks/reviews when attention allows, always support crises
        for e in api.events.pending():
            if e["kind"] == "student_crisis":
                _safe(api.events.respond, e["id"], "support")
            elif e["kind"] in ("invited_talk", "review_request"):
                if api.lab.attention()["left"] > 20:
                    _safe(api.events.respond, e["id"], "accept")
                else:
                    _safe(api.events.respond, e["id"], "decline")
            elif e["kind"] == "collab_offer":
                _safe(api.events.respond, e["id"], "accept")

        api.time.next_month()
