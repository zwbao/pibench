"""The PIBench world engine.

All world mechanics live here; the agent-facing surface is in api.py. The month
counter starts at 1. During month m the agent acts through the API; ``tick()``
closes month m (money flows, project progress, reviews, citations, grants,
students, field update, events, reputation) and opens month m+1.

Naming: fields prefixed ``h_`` on entities and everything under ``World`` that the
DB export (db.py) does not surface is hidden from the agent.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from .config import WorldConfig, TOPICS, VENUES, AGENCIES, POOLS
from .entities import (Applicant, Student, Project, Draft, Submission, Publication,
                       GrantCall, Proposal, Award, EventItem, NewsItem)
from .names import make_name
from .rng import RngHub


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def satur(y: float) -> float:
    return y / (1.0 + y)


class ApiError(Exception):
    """Raised on invalid agent actions; message is shown to the agent."""


class World:
    def __init__(self, seed: int, cfg: WorldConfig | None = None):
        self.seed = seed
        self.cfg = cfg or WorldConfig()
        self.rng = RngHub(seed)

        c = self.cfg
        self.month = 1
        self.budget = float(c.start_budget)
        self.reputation = float(c.rep_init)
        self.collapsed = False
        self.collapse_month: int | None = None
        self.finished = False
        self.alumni = 0   # PhD graduates; drives applicant-quality lift and cite spillover

        # field state
        self.hot: dict[str, float] = dict(c.hot_init)
        self.crowd: dict[str, float] = {k: max(0.4, v * 0.8) for k, v in self.hot.items()}
        self.climate = 1.0
        self._climate_phase = float(self.rng.stream("field").uniform(0, 2 * math.pi))
        self.compute_price_mult = 1.0
        self._compute_shock_until = 0

        # entity stores
        self.applicants: dict[str, Applicant] = {}
        self.students: dict[str, Student] = {}
        self.projects: dict[str, Project] = {}
        self.drafts: dict[str, Draft] = {}
        self.submissions: dict[str, Submission] = {}
        self.publications: dict[str, Publication] = {}
        self.calls: dict[str, GrantCall] = {}
        self.proposals: dict[str, Proposal] = {}
        self.awards: dict[str, Award] = {}
        self.events: dict[str, EventItem] = {}
        self.news: list[NewsItem] = []
        self.preprints: list[tuple] = []      # (month, topic, count)
        self.conf_reports: list[tuple] = []   # (month, venue, topic, count)
        self.ledger: list[tuple] = []         # (month, category, amount, note)
        self.action_log: list[dict] = []
        self.monthly_stats: list[dict] = []
        self.eval_log: list[dict] = []        # HIDDEN ground truth for skill metrics

        # per-month scratch
        self.attention_oneoff = 0.0
        self._service_tax_applied = False
        self._rep_impulse = 0.0
        self._morale_impulse: dict[str, float] = defaultdict(float)
        self._recruit_boost_years: set[int] = set()
        self._last_tif_month = -99
        self._last_conf_month = -99
        self._postdoc_openings: list[dict] = []
        self._counters: dict[str, int] = defaultdict(int)

        # hidden agency preferences over topics (AMP handled dynamically with lead)
        g = self.rng.stream("grants")
        self.h_agency_pref = {
            a: {k: float(g.uniform(-c.agency_pref_range, c.agency_pref_range)) for k in TOPICS}
            for a in AGENCIES
        }

        # precompute the full hidden hotness trajectory so AMP can "lead" it and so the
        # trajectory is agent-independent
        self._hot_traj = self._simulate_hotness(c.months + c.amp_pref_lead + 2)
        self.hot = dict(self._hot_traj[1])

        self._schedule_calls()
        self._open_month(1)

    # ------------------------------------------------------------------ ids
    def _new_id(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}{self._counters[prefix]:03d}"

    # ------------------------------------------------------------- field sim
    def _simulate_hotness(self, horizon: int) -> list[dict]:
        """Agent-independent hotness trajectory H_k(t), t = 0..horizon."""
        c = self.cfg
        g = self.rng.stream("field_traj")
        traj = [dict(c.hot_init)]
        logmean = {k: math.log(v) for k, v in c.hot_init.items()}
        cur = {k: math.log(v) for k, v in c.hot_init.items()}
        for _ in range(horizon):
            nxt = {}
            for k in TOPICS:
                logmean[k] += float(g.normal(0, 0.015))
                x = cur[k] + c.hot_ou_theta * (logmean[k] - cur[k]) + float(g.normal(0, c.hot_ou_sigma))
                u = float(g.uniform())
                if u < c.p_boom:
                    x += float(g.normal(math.log(2.2), 0.3))
                elif u < c.p_boom + c.p_bust:
                    x += math.log(float(g.uniform(0.35, 0.6)))
                x = min(max(x, math.log(c.hot_clip[0])), math.log(c.hot_clip[1]))
                nxt[k] = x
            cur = nxt
            traj.append({k: math.exp(v) for k, v in cur.items()})
        return traj

    def _schedule_calls(self):
        for agency, spec in AGENCIES.items():
            if spec["schedule"] == "rolling":
                self.calls[f"{agency}-rolling"] = GrantCall(
                    id=f"{agency}-rolling", agency=agency, open_month=1,
                    close_month=self.cfg.months, award=spec["award"], duration=spec["duration"])
            else:
                for m in spec["schedule"]:
                    if m <= self.cfg.months:
                        cid = f"{agency}-m{m:02d}"
                        self.calls[cid] = GrantCall(
                            id=cid, agency=agency, open_month=m, close_month=m + 1,
                            award=spec["award"], duration=spec["duration"])

    # --------------------------------------------------------------- helpers
    def spend(self, amount: float, category: str, note: str = ""):
        self.budget -= amount
        self.ledger.append((self.month, category, -amount, note))

    def earn(self, amount: float, category: str, note: str = ""):
        self.budget += amount
        self.ledger.append((self.month, category, amount, note))

    # role helpers: researchers (phd/postdoc) are the mentored, paper-producing,
    # (semi-)illiquid investments; staff (ra/manager) are liquid, dismissable labor.
    RESEARCHER_ROLES = ("phd", "postdoc")
    STAFF_ROLES = ("ra", "manager")

    def active_researchers(self) -> list[Student]:
        return [s for s in self.students.values()
                if s.status == "active" and s.role in self.RESEARCHER_ROLES]

    def active_ras(self) -> list[Student]:
        return [s for s in self.students.values()
                if s.status == "active" and s.role == "ra"]

    def active_managers(self) -> list[Student]:
        return [s for s in self.students.values()
                if s.status == "active" and s.role == "manager"]

    def oversight_tax(self) -> float:
        c = self.cfg
        n_res = len(self.active_researchers())
        n_ra = len(self.active_ras())
        n_mgr = len(self.active_managers())
        per = max(c.oversight_min_per_researcher,
                  c.oversight_per_researcher - c.manager_oversight_relief * n_mgr)
        return per * n_res + c.oversight_per_ra * n_ra

    def attention_pool(self) -> float:
        c = self.cfg
        pool = c.attention_budget - self.oversight_tax()
        if self.month % 12 == 7:
            pool -= c.service_tax_hours
        return max(c.attention_floor, pool)

    def mentoring_total(self) -> float:
        return sum(s.mentoring for s in self.students.values() if s.status == "active")

    def attention_left(self) -> float:
        return self.attention_pool() - self.mentoring_total() - self.attention_oneoff

    def charge_attention(self, hours: float, what: str):
        if hours < 0:
            raise ApiError("hours must be >= 0")
        if hours > self.attention_left() + 1e-9:
            raise ApiError(
                f"not enough attention for {what}: need {hours:.1f}h, "
                f"only {self.attention_left():.1f}h left this month "
                f"(pool {self.attention_pool():.0f}h - mentoring {self.mentoring_total():.0f}h "
                f"- used {self.attention_oneoff:.0f}h)")
        self.attention_oneoff += hours

    def active_students(self) -> list[Student]:
        return [s for s in self.students.values() if s.status == "active"]

    def burn_rate(self) -> float:
        """Approximate current monthly net burn (positive = losing money)."""
        c = self.cfg
        out = sum(s.stipend for s in self.active_students())
        out += sum(p.compute * c.compute_unit_cost * self.compute_price_mult
                   for p in self.projects.values() if p.status == "active")
        out += c.grant_overhead_monthly * len([a for a in self.awards.values()
                                               if a.start_month <= self.month <= a.end_month])
        inc = sum(a.monthly for a in self.awards.values()
                  if a.start_month <= self.month <= a.end_month)
        return out - inc

    def standing(self) -> str:
        r = self.reputation
        return "unknown" if r < 2.5 else "rising" if r < 4 else "established" if r < 6 else "renowned"

    def season_year(self) -> int:
        return (self.month - 1) // 12

    # =============================================================== the tick
    def tick(self):
        """Close the current month and open the next one."""
        if self.finished:
            raise ApiError("simulation is over")
        m = self.month
        self._money_flows(m)
        self._projects_step(m)
        self._review_decisions(m)
        self._citations_step(m)
        self._grant_decisions(m)
        # expire events (incl. crisis auto-ignore) BEFORE students step so that an
        # auto-ignored crisis's morale hit lands the same month as an explicit ignore
        self._events_expire(m)
        self._students_step(m)
        self._recruiting_step(m)
        self._postdoc_step(m)
        self._reputation_step()
        self._record_stats(m)

        if self.budget < 0 and not self.collapsed:
            self.collapsed = True
            self.collapse_month = m
            self.finished = True
            return
        if m >= self.cfg.months:
            self.finished = True
            return

        self.month = m + 1
        self._field_step(self.month)
        self._open_month(self.month)

    # ------------------------------------------------------------ money
    def _money_flows(self, m: int):
        c = self.cfg
        for s in self.active_students():
            self.spend(s.stipend, "stipend", s.id)
        for p in self.projects.values():
            if p.status == "active" and p.compute > 0:
                self.spend(p.compute * c.compute_unit_cost * self.compute_price_mult,
                           "compute", p.id)
        for a in self.awards.values():
            if a.start_month <= m <= a.end_month:
                self.earn(a.monthly, "grant_income", a.id)
                self.spend(c.grant_overhead_monthly, "overhead", a.id)

    # ------------------------------------------------------------ projects
    def _member_effectiveness(self, s: Student, n_projects: int) -> float:
        ind = s.h_independence
        mf = ind + (1 - ind) * min(s.mentoring, 6.0) / 6.0
        e = s.h_speed * s.skill * (0.5 + 0.5 * s.h_morale) * mf
        return e / max(1, n_projects)

    def _assignments(self) -> dict[str, int]:
        n = defaultdict(int)
        for p in self.projects.values():
            if p.status == "active":
                for sid in p.members:
                    if sid in self.students and self.students[sid].status == "active":
                        n[sid] += 1
        return n

    def _projects_step(self, m: int):
        c = self.cfg
        nproj = self._assignments()
        # deliver delayed scoop news for ALL projects, even ones that finished or
        # dead-ended in the intervening month (the rival result is public regardless)
        for p in self.projects.values():
            if p.pending_scoop_news == m:
                self.news.append(NewsItem(m, "scoop", p.topic,
                    f"A rival group posted results close to your project {p.id}."))
                p.pending_scoop_news = None
        for p in list(self.projects.values()):
            if p.status != "active":
                continue
            members = [self.students[sid] for sid in p.members
                       if sid in self.students and self.students[sid].status == "active"]
            effort = sum(self._member_effectiveness(s, nproj[s.id]) for s in members)
            # accumulate the whole-life inputs to draft quality (this tick counts)
            p.ticks += 1
            p.compute_accum += p.compute
            if members:
                ka = float(np.mean([s.skill * s.h_ability for s in members]))
                w = max(effort, 1e-6)
                p.ka_accum += ka * w
                p.ka_weight += w
            if effort > 0:
                comp = c.compute_coef * math.log1p(p.compute / c.compute_c0)
                noise = float(self.rng.keyed("prog", p.id, m).normal(1.0, c.progress_noise))
                dp = c.progress_coef * (effort ** 0.9) * (1 + comp) * max(0.1, noise)
                p.progress += dp
            # novelty bleed + scooping
            p.novelty = max(0.3, p.novelty - c.novelty_bleed * self.crowd[p.topic])
            if p.progress / p.work_required >= 0.25:
                sr = self.rng.keyed("scoop", p.id, m)
                if float(sr.uniform()) < c.scoop_base * self.crowd[p.topic]:
                    p.novelty *= c.scoop_novelty_mult
                    p.scooped_times += 1
                    p.pending_scoop_news = m + 1
                    for s in members:
                        self._morale_impulse[s.id] -= 0.2 / s.h_resilience
            # dead-end reveal
            if not p.h_feasible and p.progress >= c.deadend_reveal_frac * p.work_required:
                p.status = "deadend"
                p.ended_month = m
                for s in members:
                    self._morale_impulse[s.id] -= 0.15 / s.h_resilience
                if float(self.rng.keyed("salvage", p.id).uniform()) < c.salvage_prob:
                    q = float(self.rng.keyed("salvageq", p.id).uniform(1.5, 2.8))
                    self._make_draft(p, q, m, salvage=True)
                continue
            # completion
            if p.progress >= p.work_required:
                p.status = "completed"
                p.ended_month = m
                q = self._draft_quality(p, members, m)
                self._make_draft(p, q, m)

    def _draft_quality(self, p: Project, members: list[Student], m: int) -> float:
        c = self.cfg
        r = self.rng.keyed("quality", p.id)
        # time-averaged inputs: a late compute spike or last-minute roster change
        # cannot buy the full bonus for one month's cost
        ka = (p.ka_accum / p.ka_weight) if p.ka_weight > 0 else 0.2
        avg_compute = (p.compute_accum / p.ticks) if p.ticks > 0 else p.compute
        q = (c.tier_q0[p.tier]
             + c.quality_skill_coef * ka
             + c.quality_novelty_coef * (p.novelty - 0.6)
             + c.quality_compute_coef * math.log1p(avg_compute / c.compute_c0)
             + float(r.normal(0, c.quality_noise)))
        if p.tier == 3 and float(r.uniform()) < c.breakthrough_prob:
            q += c.breakthrough_gain
        return float(min(max(q, 0.5), 10.0))

    def _make_draft(self, p: Project, q: float, m: int, salvage: bool = False):
        did = self._new_id("D")
        # only researchers (phd/postdoc) are authors — RAs contribute effort but do
        # not earn authorship, graduation credit, or the morale bump from a paper
        authors = [sid for sid in p.members if sid in self.students
                   and self.students[sid].role in self.RESEARCHER_ROLES]
        self.drafts[did] = Draft(
            id=did, project_id=p.id, topic=p.topic, tier=p.tier,
            authors=authors, created_month=m, q=q, salvage=salvage)
        p.draft_id = did

    # ------------------------------------------------------------ reviews
    def draft_effective_q(self, d: Draft) -> float:
        c = self.cfg
        return d.q + c.quality_polish_coef * min(d.polish_hours, 12.0) / 12.0

    def _review_decisions(self, m: int):
        c = self.cfg
        for sub in self.submissions.values():
            if sub.status != "under_review" or sub.decision_month != m:
                continue
            d = self.drafts[sub.draft_id]
            v = VENUES[sub.venue]
            # key the review draw by the stable (draft, venue, submission month) tuple,
            # NOT the call-order submission id, so unrelated same-month submissions
            # cannot swap each other's outcomes
            r = self.rng.keyed("review", sub.draft_id, sub.venue, sub.submitted_month)
            score = (self.draft_effective_q(d)
                     + c.review_hot_coef * (self.hot[d.topic] - 1.0)
                     + c.review_rep_coef * (self.reputation - c.rep_init)
                     + float(r.normal(0, c.review_noise)))
            noise3 = r.normal(0, 0.35, 3)
            sub.reviewer_scores = [round(float(score + z - np.mean(noise3)), 1) for z in noise3]
            if score >= v["theta"]:
                sub.status = "accept"
                d.status = "accepted"
                # SPEC §5: a conf paper publishes at the next occurrence of the
                # venue's deadline month + 1; journals/workshops publish on decision
                if v["deadlines"]:
                    ahead = min(((dl - m) % 12) or 12 for dl in v["deadlines"])
                    pub_month = m + ahead + 1
                else:
                    pub_month = m + v["pub_lag"]
                pid = self._new_id("P")
                self.publications[pid] = Publication(
                    id=pid, draft_id=d.id, venue=sub.venue, topic=d.topic, tier=d.tier,
                    authors=list(d.authors), q=self.draft_effective_q(d),
                    published_month=pub_month, collab=d.collab)
                self._rep_impulse += c.rep_pub[sub.venue]
                for i, sid in enumerate(d.authors):
                    if sid in self.students:
                        s = self.students[sid]
                        s.papers_accepted += 1
                        if i == 0:
                            s.first_author_accepted += 1
                        self._morale_impulse[sid] += 0.35 if i == 0 else 0.25
            else:
                sub.status = "reject"
                d.status = "available"
                for sid in d.authors:
                    if sid in self.students:
                        s = self.students[sid]
                        self._morale_impulse[sid] -= 0.18 / s.h_resilience

    # ------------------------------------------------------------ citations
    def _cite_lambda(self, pub: Publication, month: int, hot: float, rep: float) -> float:
        c = self.cfg
        v = VENUES[pub.venue]
        age = month - pub.published_month
        if age < 0:
            return 0.0
        ramp = min(1.0, (age + 1) / c.cite_ramp_months)
        hl = c.cite_halflife_journal if v["kind"] == "journal" else c.cite_halflife
        decay = 0.5 ** (max(0, age - c.cite_ramp_months) / hl)
        lam = (v["vis"] * math.exp(c.cite_g_coef * (pub.q - 5.0)) * hot * ramp * decay
               * (1 + c.cite_rep_coef * (rep - c.rep_init))
               * (1 + c.alumni_cite_spillover * self.alumni))   # SPEC §3 alumni spillover
        if pub.collab:
            lam *= c.collab_credit
        return max(0.0, lam)

    def _citations_step(self, m: int):
        total = 0
        for pub in self.publications.values():
            if pub.published_month > m:
                continue
            lam = self._cite_lambda(pub, m, self.hot[pub.topic], self.reputation)
            n = int(self.rng.keyed("cite", pub.id, m).poisson(lam))
            if n:
                pub.citations += n
                pub.cite_history.append((m, n))
                total += n
        if total:
            self._rep_impulse += 0.04 * math.log1p(total)

    # ------------------------------------------------------------ grants
    def proposal_quality(self, prop: Proposal) -> float:
        """Deterministic part + stored noise; computed at submission time."""
        return prop.h_quality

    def _compute_proposal_quality(self, call: GrantCall, topic: str, hours: float,
                                  attached: list[str]) -> float:
        c = self.cfg
        y = 0.0
        has_t3 = False
        for xid in attached:
            if xid in self.publications:
                obj, w = self.publications[xid], 1.0
            elif xid in self.drafts:
                obj, w = self.drafts[xid], 0.4
            else:
                continue
            if getattr(obj, "tier", 1) == 3:
                has_t3 = True
            g = math.exp(c.cite_g_coef * ((obj.q if isinstance(obj, Publication)
                                           else self.draft_effective_q(obj)) - 5.0))
            if obj.topic != topic:
                w *= 0.25
            y += w * g
        prelim = satur(y / c.prop_prelim_norm)
        agency = call.agency
        if agency == "AMP":
            lead = self._hot_traj[min(self.month + c.amp_pref_lead, len(self._hot_traj) - 1)]
            pref = 0.35 * (lead[topic] - 1.0) + 0.5 * self.h_agency_pref[agency][topic]
        else:
            pref = self.h_agency_pref[agency][topic]
        n_active_awards = len([a for a in self.awards.values()
                               if a.start_month <= self.month <= a.end_month])
        q = (c.prop_hours_coef * (hours / c.prop_hours_norm) ** c.prop_hours_pow
             + c.prop_prelim_coef * prelim
             + min(c.prop_rep_cap, c.prop_rep_coef * (self.reputation - c.rep_init))
             + pref
             + c.prop_climate_coef * (self.climate - 1.0)
             - c.prop_overcommit_penalty * n_active_awards)
        if agency == "TIF":
            q += c.tif_hot_coef * (self.hot[topic] - 1.0)
        if agency == "AMP" and has_t3:
            q += c.amp_tier3_bonus
        return q

    def _grant_decisions(self, m: int):
        for prop in self.proposals.values():
            if prop.status != "pending" or prop.decision_month != m:
                continue
            noise = float(self.rng.keyed("grantdec", prop.id).normal(0, self.cfg.prop_noise))
            theta = AGENCIES[prop.agency]["theta"]
            if prop.h_quality + noise >= theta:
                prop.status = "funded"
                spec = AGENCIES[prop.agency]
                aid = self._new_id("A")
                self.awards[aid] = Award(
                    id=aid, proposal_id=prop.id, agency=prop.agency, total=spec["award"],
                    start_month=m + 1, end_month=m + spec["duration"],
                    monthly=spec["award"] / spec["duration"])
                self._rep_impulse += self.cfg.rep_grant[prop.agency]
            else:
                prop.status = "rejected"

    # ------------------------------------------------------------ students
    def _students_step(self, m: int):
        c = self.cfg
        nproj = self._assignments()
        # staff (ra/manager) have no morale/skill-growth/quit/graduation dynamics —
        # they are hired labor, dismissed via the API or ended by budget. Only
        # researchers (phd/postdoc) go through the growth/morale/attrition machinery.
        researchers = self.active_researchers()
        mean_morale = float(np.mean([s.h_morale for s in researchers])) if researchers else 0.7
        runway_stress = 0 < self.budget < 6 * max(1.0, self.burn_rate())
        for s in researchers:
            # skill growth
            if nproj.get(s.id, 0) > 0:
                s.skill = min(c.skill_cap,
                              s.skill + c.skill_growth * s.h_growth
                              * (1 + 1.2 * min(s.mentoring, 8.0) / 8.0))
            # recurring morale pressures
            imp = self._morale_impulse.pop(s.id, 0.0)
            if nproj.get(s.id, 0) > 2:
                imp -= 0.10
            if s.mentoring < 2.0:
                imp -= 0.08 * (1 - s.h_independence)
            if runway_stress:
                imp -= 0.10
            imp += 0.05 * (mean_morale - s.h_morale)
            s.h_morale = float(min(1.0, max(0.0,
                s.h_morale + 0.06 * (0.70 - s.h_morale) + imp)))
            # observable monthly report
            rq = s.skill * s.h_ability * (0.6 + 0.4 * s.h_morale) \
                + float(self.rng.keyed("report", s.id, m).normal(0, 0.15))
            sentiment = None
            if s.mentoring >= 1.0:
                sentiment = round(float(min(1, max(0, s.h_morale
                    + self.rng.keyed("sent", s.id, m).normal(0, 0.18)))), 2)
            s.reports.append((m, round(max(0.0, rq), 2), sentiment))
            # quits
            p_quit = min(c.quit_cap,
                         c.quit_scale * sigmoid(-(s.h_morale - c.quit_mid) / c.quit_temp))
            if float(self.rng.keyed("quit", s.id, m).uniform()) < p_quit:
                s.status = "quit"
                s.left_month = m
                self._remove_from_projects(s.id)
                self.news.append(NewsItem(m, "lab", None,
                                          f"{s.name} ({s.id}) left the lab."))
                continue
            # postdoc contract end
            if s.role == "postdoc" and s.contract_end is not None and m >= s.contract_end:
                s.status = "contract_ended"
                s.left_month = m
                self._remove_from_projects(s.id)
            # graduation (checked at the annual arrival month)
            if (s.role == "phd" and m % 12 == 5
                    and m - s.arrived_month >= c.grad_min_months
                    and s.papers_accepted >= c.grad_min_papers):
                s.status = "graduated"
                s.left_month = m
                self._remove_from_projects(s.id)
                self._rep_impulse += c.rep_grad
                self.alumni += 1   # SPEC §3 alumni effects: applicant-pool lift + cite spillover
                self.news.append(NewsItem(m, "lab", None,
                                          f"{s.name} ({s.id}) graduated with a PhD."))
        # events arrivals for next month happen in _open_month

    def _remove_from_projects(self, sid: str):
        for p in self.projects.values():
            if p.status == "active" and sid in p.members:
                p.members.remove(sid)

    # ------------------------------------------------------------ recruiting
    def _recruiting_step(self, m: int):
        """Offer resolution at m % 12 == 3; arrivals at m % 12 == 5."""
        c = self.cfg
        if m % 12 == 3:
            for a in self.applicants.values():
                if a.season_year != self.season_year():
                    continue
                if a.status == "offered":
                    pool = POOLS[a.pool]
                    p = min(0.95, max(0.05,
                            pool["acc"] + pool["acc_rep"] * (self.reputation - c.rep_init)))
                    if float(self.rng.keyed("offer", a.id).uniform()) < p:
                        a.status = "accepted"
                    else:
                        a.status = "declined"
                elif a.status == "pending":
                    a.status = "expired"
        if m % 12 == 4:  # arrivals happen when month 5 opens (tick of month 4)
            for a in self.applicants.values():
                if a.status == "accepted" and a.season_year == self.season_year():
                    sid = self._new_id("S")
                    self.students[sid] = Student(
                        id=sid, name=a.name, role="phd", arrived_month=m + 1,
                        stipend=c.phd_stipend,
                        h_ability=a.h_ability, h_speed=a.h_speed,
                        h_resilience=a.h_resilience, h_independence=a.h_independence,
                        h_growth=a.h_growth,
                        skill=c.skill_init_base + c.skill_init_ability * a.h_ability)
                    a.status = "joined"

    def _postdoc_step(self, m: int):
        c = self.cfg
        for opening in self._postdoc_openings:
            if opening["resolved"] or m < opening["month"] + 2:
                continue
            opening["resolved"] = True
            if len(self.active_researchers()) >= c.max_students:
                self.news.append(NewsItem(m, "lab", None,
                    "Postdoc search paused: lab is at capacity."))
                continue
            g = self.rng.keyed("postdoc", opening["id"])
            p_fill = min(0.85, 0.45 + 0.06 * (self.reputation - c.rep_init))
            if float(g.uniform()) < p_fill:
                a = float(np.clip(g.normal(0.62 + c.postdoc_ability_shift, 0.12), 0.2, 0.97))
                # separate id space: postdoc hiring must NOT advance the PhD 'S'
                # counter, else it re-rolls which PhD quits (draws keyed by student id)
                sid = self._new_id("PD")
                self.students[sid] = Student(
                    id=sid, name=make_name(g), role="postdoc", arrived_month=m,
                    stipend=c.postdoc_salary, h_ability=a,
                    h_speed=float(g.normal(1.05, 0.12)),
                    h_resilience=float(g.uniform(0.5, 1.0)),
                    h_independence=float(g.uniform(0.6, 1.0)),
                    h_growth=float(max(0.3, g.normal(0.8, 0.2))),
                    skill=0.55 + 0.35 * a,
                    contract_end=m + c.postdoc_contract_months)
                self.news.append(NewsItem(m, "lab", None,
                    f"Postdoc search succeeded: {self.students[sid].name} ({sid}) joined."))
            else:
                self.news.append(NewsItem(m, "lab", None,
                    "Postdoc search came up empty this time."))

    def _generate_applicants(self, m: int):
        """Called when a month with m % 12 == 1 opens."""
        c = self.cfg
        year = (m - 1) // 12
        g = self.rng.keyed("applicants", year)
        boost = 1.15 if year in self._recruit_boost_years else 1.0
        # alumni make the lab more attractive to stronger applicants (SPEC §3)
        qlift = min(c.alumni_quality_lift_cap, c.alumni_quality_lift * self.alumni)
        revealed = []
        for pool_name, pool in POOLS.items():
            n_max = 12
            traits = []
            for i in range(n_max):
                a = float(np.clip(g.normal(pool["mu"] + qlift, pool["sd"]), 0.15, 0.95))
                traits.append(dict(
                    pool=pool_name, ability=a,
                    speed=float(g.normal(1.0, 0.15)),
                    resilience=float(g.uniform(0.4, 1.0)),
                    independence=float(g.uniform(0.3, 1.0)),
                    growth=float(max(0.3, g.normal(1.0, 0.3))),
                    transcript=float(np.clip(a + g.normal(0, pool["t_noise"]), 0, 1)),
                    letter=float(np.clip(a + pool["l_bias"] + g.normal(0, pool["l_noise"]), 0, 1)),
                    interview=float(np.clip(a + g.normal(0, 0.07), 0, 1)),
                    name=make_name(g),
                ))
            lam = pool["vol"] * (1 + 0.25 * max(0, self.reputation - c.rep_init)) * boost
            n = int(min(n_max, self.rng.keyed("appcount", year, pool_name).poisson(lam)))
            revealed.extend(traits[:n])
        # shuffle so the applicant id order does not encode pool membership
        order = self.rng.keyed("appshuffle", year).permutation(len(revealed))
        for idx in order:
            t = revealed[int(idx)]
            aid = self._new_id("APP")
            self.applicants[aid] = Applicant(
                id=aid, season_year=year, pool=t["pool"], name=t["name"],
                transcript=round(t["transcript"], 2), letter=round(t["letter"], 2),
                h_ability=t["ability"], h_speed=t["speed"],
                h_resilience=t["resilience"], h_independence=t["independence"],
                h_growth=t["growth"])
            self.applicants[aid].__dict__["_h_interview"] = round(t["interview"], 2)

    # ------------------------------------------------------------ field/news
    def _field_step(self, m: int):
        c = self.cfg
        self.hot = dict(self._hot_traj[m])
        for k in TOPICS:
            noise = float(self.rng.stream("crowd").normal(0, 0.03))
            self.crowd[k] = max(0.2, self.crowd[k]
                                + c.crowd_eta * (self.hot[k] - self.crowd[k]) + noise)
        # climate OU around sinusoid
        target = 1.0 + c.climate_amp * math.sin(2 * math.pi * m / c.climate_cycle
                                                + self._climate_phase)
        self.climate = float(np.clip(
            self.climate + 0.25 * (target - self.climate)
            + self.rng.stream("climate").normal(0, c.climate_sigma),
            *c.climate_clip))
        # compute price shocks
        if m >= self._compute_shock_until and float(self.rng.stream("shock").uniform()) < 0.05:
            direction = 1 if float(self.rng.stream("shock").uniform()) < 0.5 else -1
            self.compute_price_mult = 1.0 + direction * 0.30
            self._compute_shock_until = m + 4
            word = "surged" if direction > 0 else "dropped"
            self.news.append(NewsItem(m, "compute", None,
                                      f"Cloud compute prices have {word} ~30% (expected to last a few months)."))
        elif m >= self._compute_shock_until:
            self.compute_price_mult = 1.0

    def _generate_observables(self, m: int):
        c = self.cfg
        g = self.rng.keyed("news", m)
        mags = [(1.6, "surging"), (1.2, "gaining steam"), (0.8, "steady"), (0.0, "quiet")]
        for k in TOPICS:
            n = int(g.poisson(c.news_rate_per_hot * self.hot[k]))
            if n > 0:
                word = next(w for th, w in mags if self.hot[k] >= th)
                self.news.append(NewsItem(m, "field", k,
                    f"[{n} mentions] Interest in {k} looks {word} this month."))
            self.preprints.append((m, k, int(g.poisson(c.preprint_rate_per_crowd * self.crowd[k]))))
        # conference reports: at each conf deadline month publish topic counts lagged 3 months
        for vname, v in VENUES.items():
            if v["deadlines"] and (m % 12) in v["deadlines"]:
                lag = max(1, m - 3)
                hist = self._hot_traj[lag]
                for k in TOPICS:
                    cnt = int(self.rng.keyed("conf", vname, m, k).poisson(4 * hist[k]))
                    self.conf_reports.append((m, vname, k, cnt))
        # funding climate news every 3 months, 2-month delayed, noisy
        if m % 3 == 0 and m > 2:
            lagged_target = 1.0 + c.climate_amp * math.sin(
                2 * math.pi * (m - 2) / c.climate_cycle + self._climate_phase)
            obs = lagged_target * float(g.normal(1.0, 0.05))
            mood = "expanding" if obs > 1.05 else "tightening" if obs < 0.95 else "flat"
            self.news.append(NewsItem(m, "funding", None,
                f"Funding-climate index (two months ago): {obs:.2f} — budgets look {mood}."))

    # ------------------------------------------------------------ events
    def _generate_events(self, m: int):
        c = self.cfg
        g = self.rng.keyed("events", m)
        rep = self.reputation
        if float(g.uniform()) < min(0.6, c.talk_rate_per_rep * max(0.0, rep - 2.0) + 0.05):
            eid = self._new_id("E")
            self.events[eid] = EventItem(eid, "invited_talk", m, m + c.event_expiry,
                dict(cost_hours=c.talk_hours, cost_usd=c.travel_cost_talk))
        if float(g.uniform()) < min(0.9, c.review_req_rate):
            eid = self._new_id("E")
            self.events[eid] = EventItem(eid, "review_request", m, m + c.event_expiry,
                dict(cost_hours=c.review_hours))
        for s in self.active_researchers():
            if float(self.rng.keyed("crisis", s.id, m).uniform()) < c.crisis_rate:
                eid = self._new_id("E")
                self.events[eid] = EventItem(eid, "student_crisis", m, m,  # same-month only
                    dict(student=s.id, cost_hours=c.crisis_hours))
        if float(g.uniform()) < min(0.5, c.collab_rate_per_rep * max(0.0, rep - 2.0)):
            # hotness-weighted sample over ALL topics (a single draw doesn't reveal
            # the hidden hotness ranking, unlike a hard top-3 pick)
            wts = np.array([self.hot[k] for k in TOPICS], dtype=float)
            topic = TOPICS[int(g.choice(len(TOPICS), p=wts / wts.sum()))]
            eid = self._new_id("E")
            self.events[eid] = EventItem(eid, "collab_offer", m, m + 1,
                dict(topic=topic, months=c.collab_months,
                     cost_hours_monthly=c.collab_hours_monthly))

    def _events_expire(self, m: int):
        for e in self.events.values():
            if e.status != "pending":
                continue
            if e.kind == "student_crisis" and e.month == m:
                e.status = "auto_ignored"
                sid = e.payload["student"]
                if sid in self.students and self.students[sid].status == "active":
                    s = self.students[sid]
                    self._morale_impulse[sid] -= 0.35 / s.h_resilience
            elif m >= e.expires:
                e.status = "expired"
                if e.kind == "review_request":
                    self._rep_impulse += self.cfg.rep_review_decline
        # collab drafts materialize
        for e in self.events.values():
            if e.kind == "collab_offer" and e.status == "accepted" \
                    and e.payload.get("deliver_month") == m:
                q = float(self.rng.keyed("collabq", e.id).normal(4.8, 0.8))
                did = self._new_id("D")
                self.drafts[did] = Draft(id=did, project_id=None, topic=e.payload["topic"],
                                         tier=2, authors=[], created_month=m,
                                         q=float(np.clip(q, 1.0, 8.0)), collab=True)
                e.payload["delivered_draft"] = did

    # ------------------------------------------------------------ reputation
    def _reputation_step(self):
        c = self.cfg
        self.reputation = float(np.clip(
            self.reputation + self._rep_impulse - c.rep_decay * (self.reputation - c.rep_init),
            0.0, 10.0))
        self._rep_impulse = 0.0

    # ------------------------------------------------------------ month open
    def _open_month(self, m: int):
        self.attention_oneoff = 0.0
        self._generate_observables(m)
        self._generate_events(m)
        if m % 12 == 1:
            self._generate_applicants(m)
        # reserve monthly collab time for the collab_months months AFTER acceptance,
        # up to and including delivery (exactly collab_months charges, no silent
        # under-charge — the PI committed to it)
        for e in self.events.values():
            if (e.kind == "collab_offer" and e.status == "accepted"
                    and e.payload.get("accept_month", 10**9) < m <= e.payload.get("deliver_month", -1)):
                self.attention_oneoff += e.payload["cost_hours_monthly"]
        # revalidate standing mentoring against this month's (possibly reduced) pool
        # so the service tax and collab reservations actually bite instead of being
        # dodged by leaving attention parked in mentoring
        avail = self.attention_pool() - self.attention_oneoff
        total_ment = self.mentoring_total()
        if total_ment > avail + 1e-9 and total_ment > 0:
            scale = max(0.0, avail) / total_ment
            for s in self.active_students():
                s.mentoring = round(s.mentoring * scale, 2)

    # ------------------------------------------------------------ stats/score
    def _record_stats(self, m: int):
        self.monthly_stats.append(dict(
            month=m, budget=round(self.budget, 2), reputation=round(self.reputation, 3),
            students=len(self.active_researchers()),
            staff=len(self.active_ras()) + len(self.active_managers()),
            projects=len([p for p in self.projects.values() if p.status == "active"]),
            publications=len([p for p in self.publications.values() if p.published_month <= m]),
            citations=sum(p.citations for p in self.publications.values()),
            attention_used=round(self.mentoring_total() + self.attention_oneoff, 1),
            attention_pool=round(self.attention_pool(), 1),
            hot=dict(self.hot), climate=round(self.climate, 3),
        ))
        # eval log: HIDDEN ground truth for post-hoc skill-axis metrics. Never exposed
        # to the agent (dumped to a separate file the harness does not feed back).
        self.eval_log.append(dict(
            month=m,
            mentoring={s.id: dict(hours=s.mentoring, ability=round(s.h_ability, 3),
                                  growth=round(s.h_growth, 3),
                                  independence=round(s.h_independence, 3),
                                  role=s.role)
                       for s in self.active_researchers()},
        ))

    def projected_future_citations(self) -> float:
        """Deterministic going-concern term with hotness and reputation frozen."""
        T = self.month if not self.collapsed else self.collapse_month
        if self.collapsed:
            return 0.0
        total = 0.0
        for pub in self.publications.values():
            if pub.published_month > T:
                continue
            for tau in range(T + 1, T + 1 + self.cfg.projection_months):
                total += self._cite_lambda(pub, tau, self.hot[pub.topic], self.reputation)
        return total

    def impact(self) -> float:
        cites = sum(p.citations for p in self.publications.values())
        return round(cites + self.projected_future_citations(), 1)

    def h_index(self) -> int:
        counts = sorted((p.citations for p in self.publications.values()), reverse=True)
        h = 0
        for i, c in enumerate(counts, 1):
            if c >= i:
                h = i
        return h

    def summary(self) -> dict:
        pubs = [p for p in self.publications.values() if p.published_month <= self.month]
        return dict(
            seed=self.seed,
            months_survived=self.collapse_month if self.collapsed else self.month,
            collapsed=self.collapsed,
            impact=self.impact(),
            citations=sum(p.citations for p in self.publications.values()),
            projected=round(self.projected_future_citations(), 1),
            h_index=self.h_index(),
            publications=len(pubs),
            top_pubs=len([p for p in pubs if p.venue == "NAIC"]),
            grants_won=len(self.awards),
            grant_dollars=sum(a.total for a in self.awards.values()),
            students_graduated=len([s for s in self.students.values() if s.status == "graduated"]),
            students_quit=len([s for s in self.students.values() if s.status == "quit"]),
            final_budget=round(self.budget, 2),
            final_reputation=round(self.reputation, 2),
        )

    def eval_snapshot(self) -> dict:
        """HIDDEN ground truth for post-hoc skill-axis metrics. Never shown to the
        agent; the harness writes it to a separate file used only by analysis."""
        return dict(
            seed=self.seed,
            monthly_mentoring=self.eval_log,
            projects=[dict(
                id=p.id, tier=p.tier, topic=p.topic, status=p.status,
                started_month=p.started_month, ended_month=p.ended_month,
                hot_at_start=p.h_hot_at_start, future_hot=p.h_future_hot,
                runway_at_start=p.h_runway_at_start, idle_at_start=p.h_idle_at_start,
                feasible=p.h_feasible, scooped=p.scooped_times,
                produced_paper=p.draft_id is not None)
                for p in self.projects.values()],
            researchers=[dict(
                id=s.id, role=s.role, ability=round(s.h_ability, 3),
                growth=round(s.h_growth, 3), independence=round(s.h_independence, 3),
                arrived=s.arrived_month, left=s.left_month, status=s.status,
                papers=s.papers_accepted)
                for s in self.students.values()
                if s.role in self.RESEARCHER_ROLES],
        )
