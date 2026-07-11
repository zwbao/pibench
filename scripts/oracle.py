"""Oracle policy: plays with full access to hidden state (true abilities, the future
hotness trajectory, latent draft quality, proposal quality). NOT a fair player — it
estimates attainable headroom for the paper, replacing hand-waved upper bounds.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from pibench.api import LabAPI
from pibench.config import AGENCIES, TOPICS, VENUES
from pibench.world import ApiError, World


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ApiError:
        return None


def future_hot(w: World, topic: str, ahead: int = 18) -> float:
    end = min(w.month + ahead, len(w._hot_traj) - 1)
    return float(np.mean([w._hot_traj[t][topic] for t in range(w.month, end + 1)]))


def run_oracle(seed: int, months: int = 60) -> dict:
    w = World(seed)
    w.cfg.months = months
    api = LabAPI(w)

    while not w.finished:
        m = w.month

        # ---- hiring: true ability, aggressive but runway-aware
        if m % 12 == 1:
            active = w.active_researchers()
            burn = max(1.0, w.burn_rate())
            runway = w.budget / burn
            want = 0
            if len(active) < 3:
                want = 3 - len(active)
            elif runway > 20 and len(active) < 7:
                want = 2
            apps = [a for a in w.applicants.values()
                    if a.season_year == w.season_year() and a.status == "pending"]
            apps.sort(key=lambda a: -a.h_ability)          # CHEAT
            for a in apps[:want + 1]:
                if a.h_ability > 0.55:
                    _safe(api.recruit.offer, a.id)

        # ---- lab manager: once the lab is large enough that oversight eats attention,
        # buy it back (a manager pays for itself when it frees >~its salary in PI time)
        if len(w.active_researchers()) >= 5 and not w.active_managers() and runway > 15:
            _safe(api.recruit.hire_manager)

        # ---- mentoring: give hours to dependent students (CHEAT: reads independence)
        active = w.active_researchers()
        if active:
            alloc, left = {}, 55.0
            for s in sorted(active, key=lambda s: s.h_independence):
                h = min(6.0 if s.h_independence < 0.7 else 3.0, left)
                alloc[s.id] = h
                left -= h
            _safe(api.students.set_mentoring, alloc)

        # ---- topic choice: best mean future hotness (CHEAT: future trajectory)
        best_topic = max(TOPICS, key=lambda k: future_hot(w, k))

        # ---- projects: fast tier-2 pubs first; tier 3 only once the lab is rolling
        burn = max(1.0, w.burn_rate())
        runway = w.budget / burn
        compute = 500 if runway < 12 else 2000
        n_pubs = len([p for p in w.publications.values() if p.published_month <= m])
        proj = [p for p in w.projects.values() if p.status == "active"]
        busy = {sid for p in proj for sid in p.members}
        idle = [s for s in active if s.id not in busy]
        idle.sort(key=lambda s: -(s.h_ability * s.skill))
        while idle:
            team = [s.id for s in idle[:2]]
            idle = idle[2:]
            strong = (w.students[team[0]].h_ability > 0.7 and n_pubs >= 2
                      and m < months - 24 and runway > 18)
            tier = 3 if strong else 2
            _safe(api.projects.start, best_topic, tier, team, compute)
        for p in proj:  # keep compute aligned with runway
            if p.compute != compute:
                _safe(api.projects.set_compute, p.id, compute)

        # ---- papers: perfect venue targeting (CHEAT: reads latent q); never
        # resubmit to a venue that already rejected the draft; drop hopeless junk
        for d in list(w.drafts.values()):
            if d.status != "available":
                continue
            rejected = {s.venue for s in w.submissions.values()
                        if s.draft_id == d.id and s.status == "reject"}
            if d.polish_hours < 12 and not d.salvage and not rejected:
                _safe(api.papers.polish, d.id, min(12 - d.polish_hours,
                                                   max(0, w.attention_left() - 5)))
            q = w.draft_effective_q(d)
            score = q + 0.35 * (w.hot[d.topic] - 1.0) + 0.15 * (w.reputation - 2.0)
            if score < VENUES["W-SHOP"]["theta"] - 0.3 and rejected:
                continue  # hopeless; stop hurting morale
            if score >= VENUES["NAIC"]["theta"] - 0.2:
                order = ["NAIC", "JMR", "CLAR", "W-SHOP"]
            elif score >= VENUES["JMR"]["theta"] - 0.2:
                order = ["JMR", "CLAR", "W-SHOP"]
            elif score >= VENUES["CLAR"]["theta"] - 0.3:
                order = ["CLAR", "W-SHOP"]
            else:
                order = ["W-SHOP"]
            for v in order:
                if v in rejected:
                    continue
                if _safe(api.papers.submit, d.id, v):
                    break

        # ---- grants (CHEAT: quality preview). Risk tolerance scales with need:
        # comfortable -> only sure bets; tight runway -> take coin flips.
        slack = 0.15 if runway > 24 else -0.20
        for call in list(w.calls.values()):
            if not (call.open_month <= m <= call.close_month):
                continue
            pubs = [p for p in w.publications.values() if p.published_month <= m]
            evid_pool = sorted(pubs, key=lambda p: -p.q)[:4]
            drafts_pool = sorted([d for d in w.drafts.values()
                                  if d.status in ("available", "under_review")],
                                 key=lambda d: -d.q)[:2]
            best_t, best_q, best_e = None, -9, []
            for topic in TOPICS:
                evid = ([p.id for p in evid_pool if p.topic == topic]
                        or [p.id for p in evid_pool]
                        or [d.id for d in drafts_pool])
                try:
                    q = w._compute_proposal_quality(call, topic, 25, evid)
                except Exception:
                    continue
                if q > best_q:
                    best_t, best_q, best_e = topic, q, evid
            need = AGENCIES[call.agency]["theta"]
            if best_t and best_q > need + slack and w.attention_left() > 27:
                _safe(api.grants.propose, call.id, best_t, 25, best_e)

        # ---- events
        for e in list(w.events.values()):
            if e.status != "pending":
                continue
            if e.kind == "student_crisis":
                _safe(api.events.respond, e.id, "support")
            elif e.kind == "collab_offer":
                _safe(api.events.respond, e.id, "accept")
            elif w.attention_left() > 15:
                _safe(api.events.respond, e.id, "accept")
            else:
                _safe(api.events.respond, e.id, "decline")

        api.time.next_month()

    return w.summary()


if __name__ == "__main__":
    seeds = [int(x) for x in (sys.argv[1:] or ["101", "102", "103", "104", "105"])]
    rows = [run_oracle(s) for s in seeds]
    for s, r in zip(seeds, rows):
        print(f"seed {s}: impact={r['impact']:9.1f} pubs={r['publications']:3d} "
              f"top={r['top_pubs']:2d} grants={r['grants_won']} "
              f"surv={r['months_survived']} budget={r['final_budget']:9.0f}")
    print(f"ORACLE mean impact: {np.mean([r['impact'] for r in rows]):.1f}")
