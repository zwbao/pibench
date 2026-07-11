"""Agent-facing API (the ``pilab`` surface).

Every method validates inputs, charges money/attention, logs the action, and
returns a JSON-friendly dict. Invalid actions raise ApiError whose message is
shown verbatim to the agent.
"""
from __future__ import annotations

import numpy as np

from .config import TOPICS, VENUES, AGENCIES
from .entities import Draft, NewsItem, Project, Student, Submission, Proposal
from .world import ApiError, World


def _log(world: World, name: str, **kwargs):
    world.action_log.append(dict(month=world.month, action=name, args=kwargs))


class _NS:
    def __init__(self, world: World):
        self.w = world


class Lab(_NS):
    def dashboard(self) -> dict:
        w = self.w
        m = w.month
        burn = w.burn_rate()
        runway = round(w.budget / burn, 1) if burn > 0 else None
        deadlines = [v for v, spec in VENUES.items()
                     if spec["deadlines"] and (m % 12) in spec["deadlines"]]
        open_calls = [dict(id=c.id, agency=c.agency, award=c.award,
                           duration_months=c.duration, last_month_to_apply=c.close_month)
                      for c in w.calls.values() if c.open_month <= m <= c.close_month]
        students = []
        for s in w.active_researchers():
            last = s.reports[-1] if s.reports else (None, None, None)
            students.append(dict(
                id=s.id, name=s.name, role=s.role, months_in=m - s.arrived_month,
                stipend=s.stipend, mentoring_hours=s.mentoring,
                papers_accepted=s.papers_accepted,
                last_report_quality=last[1], last_meeting_sentiment=last[2],
                contract_end=s.contract_end))
        projects = [dict(id=p.id, topic=p.topic, tier=p.tier,
                         progress_pct=round(100 * p.progress / p.work_required, 1),
                         members=list(p.members), monthly_compute=p.compute)
                    for p in w.projects.values() if p.status == "active"]
        drafts = [dict(id=d.id, topic=d.topic, tier=d.tier, created=d.created_month,
                       salvage=d.salvage, collab=d.collab, polish_hours=d.polish_hours,
                       revisions=d.revisions)
                  for d in w.drafts.values() if d.status == "available"]
        subs = [dict(id=s.id, draft=s.draft_id, venue=s.venue,
                     decision_expected_month=s.decision_month)
                for s in w.submissions.values() if s.status == "under_review"]
        props = [dict(id=p.id, agency=p.agency, topic=p.topic,
                      decision_expected_month=p.decision_month)
                 for p in w.proposals.values() if p.status == "pending"]
        awards = [dict(id=a.id, agency=a.agency, monthly_income=round(a.monthly),
                       ends_month=a.end_month)
                  for a in w.awards.values() if a.start_month <= m <= a.end_month]
        events = [dict(id=e.id, kind=e.kind, respond_by_month=e.expires,
                       details=dict((k, v) for k, v in e.payload.items()
                                    if not k.startswith("deliver")))
                  for e in w.events.values() if e.status == "pending" and e.month <= m]
        notes = []
        if m % 12 == 1:
            notes.append("PhD application season OPEN: review applicants, interview, make offers "
                         "by month %d." % (m + 2))
        elif m % 12 in (2, 3):
            notes.append("PhD offers must be made by the end of month %d "
                         "(m %% 12 == 3)." % (m - (m % 12) + 3))
        if deadlines:
            notes.append("Venue deadlines THIS month: " + ", ".join(deadlines))
        if w.compute_price_mult != 1.0:
            notes.append(f"Compute price multiplier currently x{w.compute_price_mult:.2f}.")
        if m % 12 == 7:
            notes.append("University service duty this month: -12h attention.")
        return dict(
            month=m, label=f"Y{(m - 1) // 12 + 1}M{(m - 1) % 12 + 1}",
            months_total=w.cfg.months,
            budget=round(w.budget), est_monthly_burn=round(burn),
            runway_months=runway,
            attention=dict(base=w.cfg.attention_budget,
                           oversight_tax=round(w.oversight_tax(), 1),
                           pool=round(w.attention_pool(), 1),
                           mentoring_reserved=w.mentoring_total(),
                           oneoff_used=round(w.attention_oneoff, 1),
                           left=round(w.attention_left(), 1)),
            staff=[dict(id=s.id, name=s.name, role=s.role, monthly_cost=s.stipend)
                   for s in w.students.values()
                   if s.status == "active" and s.role in ("ra", "manager")],
            lab_standing=w.standing(),
            students=students, active_projects=projects, available_drafts=drafts,
            submissions_under_review=subs, proposals_pending=props,
            active_awards=awards, pending_events=events,
            venue_deadlines_this_month=deadlines, open_grant_calls=open_calls,
            notes=notes)

    def ledger(self, n: int = 20) -> list:
        return [dict(month=mm, category=c, amount=round(a), note=note)
                for mm, c, a, note in self.w.ledger[-n:]]

    def attention(self) -> dict:
        w = self.w
        return dict(pool=w.attention_pool(), mentoring_reserved=w.mentoring_total(),
                    oneoff_used=round(w.attention_oneoff, 1), left=round(w.attention_left(), 1))


class Recruit(_NS):
    def applicants(self) -> list:
        w = self.w
        if w.month % 12 not in (1, 2, 3):
            return []
        year = w.season_year()
        out = []
        for a in w.applicants.values():
            if a.season_year == year and a.status in ("pending", "offered"):
                out.append(dict(id=a.id, name=a.name, pool=a.pool,
                                transcript=a.transcript, letter=a.letter,
                                interview=a.interview, status=a.status))
        return out

    def interview(self, applicant_ids: list) -> dict:
        w = self.w
        if w.month % 12 not in (1, 2, 3):
            raise ApiError("interviews only during application season (months 1-3 of each year)")
        if isinstance(applicant_ids, str):
            applicant_ids = [applicant_ids]
        results = {}
        for aid in applicant_ids:
            a = w.applicants.get(aid)
            if a is None or a.season_year != w.season_year():
                raise ApiError(f"unknown applicant {aid}")
            if a.interviewed:
                results[aid] = a.interview
                continue
            w.charge_attention(w.cfg.interview_hours, f"interview {aid}")
            a.interviewed = True
            a.interview = a.__dict__["_h_interview"]
            results[aid] = a.interview
        _log(w, "recruit.interview", ids=applicant_ids)
        return dict(interview_scores=results)

    def offer(self, applicant_id: str) -> dict:
        w = self.w
        if w.month % 12 not in (1, 2, 3):
            raise ApiError("offers only during application season (months 1-3 of each year)")
        a = w.applicants.get(applicant_id)
        if a is None or a.season_year != w.season_year():
            raise ApiError(f"unknown applicant {applicant_id}")
        if a.status != "pending":
            raise ApiError(f"applicant {applicant_id} is {a.status}")
        n_active = len(w.active_researchers())
        n_offers = len([x for x in w.applicants.values()
                        if x.season_year == a.season_year and x.status == "offered"])
        if n_active + n_offers >= w.cfg.max_students:
            raise ApiError(f"lab is at researcher capacity ({w.cfg.max_students})")
        a.status = "offered"
        _log(w, "recruit.offer", id=applicant_id)
        return dict(ok=True, note="acceptance decided at the end of month %d"
                                  % (w.month - (w.month % 12) + 3))

    def post_postdoc(self) -> dict:
        w = self.w
        active = len(w.active_researchers())
        pending = len([o for o in w._postdoc_openings if not o["resolved"]])
        if active + pending >= w.cfg.max_students:
            raise ApiError(f"lab is at or near capacity ({w.cfg.max_students}); "
                           "a postdoc search now could not be filled")
        w.spend(1000, "recruiting", "postdoc search")
        oid = w._new_id("PDsearch")
        w._postdoc_openings.append(dict(id=oid, month=w.month, resolved=False))
        _log(w, "recruit.post_postdoc")
        return dict(ok=True, note="search resolves in ~2 months")

    def renew_postdoc(self, student_id: str) -> dict:
        w = self.w
        s = w.students.get(student_id)
        if s is None or s.role != "postdoc" or s.status != "active":
            raise ApiError(f"{student_id} is not an active postdoc")
        if s.contract_end - w.month > 3:
            raise ApiError("can only renew within 3 months of contract end")
        s.contract_end += 12
        _log(w, "recruit.renew_postdoc", id=student_id)
        return dict(ok=True, new_contract_end=s.contract_end)

    def hire_ra(self) -> dict:
        """Research assistant: cheap liquid labor. Adds project throughput but is
        low-skill, does not grow, earns no authorship, and needs little mentoring.
        Dismissable any month (unlike PhD students)."""
        w = self.w
        c = w.cfg
        from .names import make_name
        g = w.rng.keyed("ra", w._new_id("RAkey"))
        sid = w._new_id("RA")
        w.students[sid] = Student(
            id=sid, name=make_name(g), role="ra", arrived_month=w.month,
            stipend=c.ra_salary, h_ability=float(g.uniform(0.35, 0.55)),
            h_speed=float(g.normal(0.9, 0.1)), h_resilience=0.8, h_independence=0.9,
            h_growth=0.0, skill=c.ra_skill, h_morale=0.7)
        _log(w, "recruit.hire_ra", id=sid)
        return dict(ok=True, staff_id=sid, monthly_cost=c.ra_salary,
                    note="assign to projects for throughput; no authorship; dismissable")

    def hire_manager(self) -> dict:
        """Lab manager: no research output, but absorbs management overhead so the PI
        reclaims attention hours (money -> attention). Dismissable any month."""
        w = self.w
        c = w.cfg
        if len(w.active_managers()) >= c.max_managers:
            raise ApiError(f"at most {c.max_managers} lab managers")
        from .names import make_name
        g = w.rng.keyed("mgr", w._new_id("MGRkey"))
        sid = w._new_id("MGR")
        w.students[sid] = Student(
            id=sid, name=make_name(g), role="manager", arrived_month=w.month,
            stipend=c.manager_salary, h_independence=1.0, h_growth=0.0, skill=0.0)
        _log(w, "recruit.hire_manager", id=sid)
        return dict(ok=True, staff_id=sid, monthly_cost=c.manager_salary,
                    attention_relief_per_researcher=c.manager_oversight_relief,
                    note="reduces per-researcher oversight, freeing PI attention")

    def dismiss(self, staff_id: str) -> dict:
        """Dismiss a staff member (RA or manager). PhD students and postdocs on
        contract CANNOT be dismissed — that irreversibility is central to the task."""
        w = self.w
        s = w.students.get(staff_id)
        if s is None or s.status != "active":
            raise ApiError(f"{staff_id} is not an active lab member")
        if s.role not in ("ra", "manager"):
            raise ApiError(f"{staff_id} is a {s.role}; only RAs and managers can be "
                           "dismissed (students cannot be fired)")
        s.status = "dismissed"
        s.left_month = w.month
        w._remove_from_projects(s.id)
        _log(w, "recruit.dismiss", id=staff_id)
        return dict(ok=True)


class Students(_NS):
    def list(self) -> list:
        w = self.w
        return [dict(id=s.id, name=s.name, role=s.role, status=s.status,
                     arrived_month=s.arrived_month, months_in=w.month - s.arrived_month,
                     mentoring_hours=s.mentoring, papers_accepted=s.papers_accepted,
                     first_author_accepted=s.first_author_accepted,
                     contract_end=s.contract_end)
                for s in w.students.values()]

    def set_mentoring(self, hours_by_student: dict) -> dict:
        w = self.w
        for sid, h in hours_by_student.items():
            s = w.students.get(sid)
            if s is None or s.status != "active":
                raise ApiError(f"{sid} is not an active lab member")
            if h < 0 or h > 40:
                raise ApiError("mentoring hours must be within [0, 40]")
        new_total = 0.0
        for s in w.active_students():
            new_total += hours_by_student.get(s.id, s.mentoring)
        if new_total + w.attention_oneoff > w.attention_pool() + 1e-9:
            raise ApiError(
                f"total mentoring {new_total:.0f}h + used {w.attention_oneoff:.0f}h exceeds "
                f"pool {w.attention_pool():.0f}h")
        for sid, h in hours_by_student.items():
            w.students[sid].mentoring = float(h)
        _log(w, "students.set_mentoring", alloc=hours_by_student)
        return dict(ok=True, mentoring_total=w.mentoring_total())

    def reports(self, student_id: str, n: int = 6) -> list:
        s = self.w.students.get(student_id)
        if s is None:
            raise ApiError(f"unknown student {student_id}")
        return [dict(month=mm, report_quality=rq, meeting_sentiment=sent)
                for mm, rq, sent in s.reports[-n:]]


class Projects(_NS):
    def list(self) -> list:
        w = self.w
        return [dict(id=p.id, topic=p.topic, tier=p.tier, status=p.status,
                     progress_pct=round(100 * p.progress / p.work_required, 1),
                     members=list(p.members), monthly_compute=p.compute,
                     started_month=p.started_month, draft=p.draft_id)
                for p in w.projects.values()]

    def start(self, topic: str, tier: int, members: list, monthly_compute: float = 0) -> dict:
        w = self.w
        if topic not in TOPICS:
            raise ApiError(f"unknown topic {topic}; valid: {TOPICS}")
        if tier not in (1, 2, 3):
            raise ApiError("tier must be 1, 2 or 3")
        if not members:
            raise ApiError("a project needs at least one lab member")
        for sid in members:
            s = w.students.get(sid)
            if s is None or s.status != "active":
                raise ApiError(f"{sid} is not an active lab member")
        if monthly_compute < 0 or monthly_compute > 50_000:
            raise ApiError("monthly_compute must be within [0, 50000] ($1/unit)")
        if len([p for p in w.projects.values() if p.status == "active"]) >= w.cfg.max_active_projects:
            raise ApiError(f"too many active projects (max {w.cfg.max_active_projects})")
        pid = w._new_id("PJ")
        g = w.rng.keyed("feas", pid)
        feasible = float(g.uniform()) >= w.cfg.tier_infeasible[tier]
        novelty = float(np.clip(g.normal(1.0, 0.1)
                                - w.cfg.novelty_crowd_penalty * (w.crowd[topic] - 1.0),
                                0.3, 1.3))
        # hidden start context for skill-axis metrics (risk calibration, anticipation)
        traj = w._hot_traj
        fut = [traj[min(w.month + k, len(traj) - 1)][topic] for k in range(1, 13)]
        burn = max(1.0, w.burn_rate())
        busy = {sid for pj in w.projects.values() if pj.status == "active"
                for sid in pj.members}
        w.projects[pid] = Project(
            id=pid, topic=topic, tier=tier, members=list(members),
            compute=float(monthly_compute), started_month=w.month,
            work_required=w.cfg.tier_work[tier], novelty=novelty, h_feasible=feasible,
            h_hot_at_start=round(w.hot[topic], 3),
            h_future_hot=round(float(np.mean(fut)), 3),
            h_runway_at_start=round(w.budget / burn, 1),
            h_idle_at_start=len([s for s in w.active_researchers() if s.id not in busy]))
        _log(w, "projects.start", id=pid, topic=topic, tier=tier,
             members=members, compute=monthly_compute)
        return dict(ok=True, project_id=pid,
                    est_months_note="work units required: %.0f; monthly progress depends on "
                                    "team effectiveness, mentoring, morale, compute"
                                    % w.cfg.tier_work[tier])

    def set_compute(self, project_id: str, monthly_compute: float) -> dict:
        w = self.w
        p = w.projects.get(project_id)
        if p is None or p.status != "active":
            raise ApiError(f"{project_id} is not an active project")
        if monthly_compute < 0 or monthly_compute > 50_000:
            raise ApiError("monthly_compute must be within [0, 50000]")
        p.compute = float(monthly_compute)
        _log(w, "projects.set_compute", id=project_id, compute=monthly_compute)
        return dict(ok=True)

    def assign(self, project_id: str, student_id: str) -> dict:
        w = self.w
        p = w.projects.get(project_id)
        s = w.students.get(student_id)
        if p is None or p.status != "active":
            raise ApiError(f"{project_id} is not an active project")
        if s is None or s.status != "active":
            raise ApiError(f"{student_id} is not an active lab member")
        if student_id not in p.members:
            p.members.append(student_id)
        _log(w, "projects.assign", project=project_id, student=student_id)
        return dict(ok=True, members=list(p.members))

    def unassign(self, project_id: str, student_id: str) -> dict:
        w = self.w
        p = w.projects.get(project_id)
        if p is None or p.status != "active":
            raise ApiError(f"{project_id} is not an active project")
        if student_id in p.members:
            p.members.remove(student_id)
        _log(w, "projects.unassign", project=project_id, student=student_id)
        return dict(ok=True, members=list(p.members))

    def kill(self, project_id: str) -> dict:
        w = self.w
        p = w.projects.get(project_id)
        if p is None or p.status != "active":
            raise ApiError(f"{project_id} is not an active project")
        p.status = "killed"
        p.ended_month = w.month
        for sid in p.members:
            s = w.students.get(sid)
            if s and s.status == "active":
                w._morale_impulse[sid] -= 0.15 / s.h_resilience
        _log(w, "projects.kill", id=project_id)
        return dict(ok=True)


class Papers(_NS):
    def drafts(self) -> list:
        w = self.w
        return [dict(id=d.id, topic=d.topic, tier=d.tier, status=d.status,
                     created_month=d.created_month, authors=list(d.authors),
                     polish_hours=d.polish_hours, revisions=d.revisions,
                     salvage=d.salvage, collab=d.collab)
                for d in w.drafts.values()]

    def polish(self, draft_id: str, hours: float) -> dict:
        w = self.w
        d = w.drafts.get(draft_id)
        if d is None or d.status != "available":
            raise ApiError(f"{draft_id} is not an available draft")
        w.charge_attention(hours, f"polish {draft_id}")
        d.polish_hours += hours
        _log(w, "papers.polish", id=draft_id, hours=hours)
        return dict(ok=True, total_polish_hours=d.polish_hours,
                    note="polish saturates at 12h")

    def submit(self, draft_id: str, venue: str) -> dict:
        w = self.w
        d = w.drafts.get(draft_id)
        if d is None:
            raise ApiError(f"unknown draft {draft_id}")
        if d.status != "available":
            raise ApiError(f"draft {draft_id} is {d.status}")
        if venue not in VENUES:
            raise ApiError(f"unknown venue {venue}; valid: {list(VENUES)}")
        v = VENUES[venue]
        if v["deadlines"] and (w.month % 12) not in v["deadlines"]:
            raise ApiError(f"{venue} accepts submissions only in months with "
                           f"month %% 12 in {v['deadlines']}")
        sid = w._new_id("SUB")
        w.submissions[sid] = Submission(
            id=sid, draft_id=d.id, venue=venue, submitted_month=w.month,
            decision_month=w.month + v["delay"])
        d.status = "under_review"
        _log(w, "papers.submit", draft=draft_id, venue=venue)
        return dict(ok=True, submission_id=sid,
                    decision_expected_month=w.month + v["delay"])

    def revise(self, draft_id: str, hours: float) -> dict:
        w = self.w
        d = w.drafts.get(draft_id)
        if d is None or d.status != "available":
            raise ApiError(f"{draft_id} is not an available draft")
        rejected = any(s.draft_id == draft_id and s.status == "reject"
                       for s in w.submissions.values())
        if not rejected:
            raise ApiError("revise applies to drafts with at least one rejection; "
                           "use papers.polish for a first-pass improvement")
        # SPEC §5: a revision takes a full month of an author's effort — at most one
        # revision per draft per month (no same-month stacking of gains)
        if d.__dict__.get("_last_revised_month") == w.month:
            raise ApiError("this draft was already revised this month; "
                           "a revision takes a month of effort")
        authors = [sid for sid in d.authors
                   if sid in w.students and w.students[sid].status == "active"]
        if d.authors and not authors:
            raise ApiError("no active author remains to carry out the revision")
        w.charge_attention(hours, f"revise {draft_id}")
        gain = (w.cfg.revise_gain * min(hours, 10) / 10
                * (w.cfg.revise_decay ** d.revisions))
        d.q = min(10.0, d.q + gain)
        d.revisions += 1
        d.__dict__["_last_revised_month"] = w.month
        _log(w, "papers.revise", id=draft_id, hours=hours)
        return dict(ok=True, revisions=d.revisions,
                    note="revision gains shrink with each round; one revision per month")

    def withdraw(self, submission_id: str) -> dict:
        w = self.w
        s = w.submissions.get(submission_id)
        if s is None or s.status != "under_review":
            raise ApiError(f"{submission_id} is not under review")
        s.status = "withdrawn"
        w.drafts[s.draft_id].status = "available"
        _log(w, "papers.withdraw", id=submission_id)
        return dict(ok=True)

    def submissions(self) -> list:
        w = self.w
        return [dict(id=s.id, draft=s.draft_id, venue=s.venue, status=s.status,
                     submitted_month=s.submitted_month,
                     decision_month=s.decision_month if s.status != "under_review"
                     else None,
                     decision_expected_month=s.decision_month,
                     reviewer_scores=s.reviewer_scores)
                for s in w.submissions.values()]

    def publications(self) -> list:
        w = self.w
        return [dict(id=p.id, venue=p.venue, topic=p.topic, tier=p.tier,
                     published_month=p.published_month, citations=p.citations,
                     authors=list(p.authors), collab=p.collab)
                for p in w.publications.values() if p.published_month <= w.month]


class Grants(_NS):
    def calls(self) -> list:
        w = self.w
        return [dict(id=c.id, agency=c.agency, award=c.award, duration_months=c.duration,
                     open_month=c.open_month, last_month_to_apply=c.close_month,
                     decision_delay_months=AGENCIES[c.agency]["delay"])
                for c in w.calls.values()
                if c.open_month <= w.month <= c.close_month]

    def propose(self, call_id: str, topic: str, hours: float, attach: list = ()) -> dict:
        w = self.w
        call = w.calls.get(call_id)
        if call is None:
            raise ApiError(f"unknown call {call_id}")
        if not (call.open_month <= w.month <= call.close_month):
            raise ApiError(f"call {call_id} is not open (months {call.open_month}"
                           f"-{call.close_month})")
        if topic not in TOPICS:
            raise ApiError(f"unknown topic {topic}")
        if hours < 5:
            raise ApiError("a credible proposal needs at least 5 hours")
        spec = AGENCIES[call.agency]
        if spec.get("once") and any(
                p.agency == call.agency and p.status == "funded"
                for p in w.proposals.values()):
            raise ApiError(f"{call.agency} is a one-time career award and you already hold it")
        active_same = len([a for a in w.awards.values()
                           if a.agency == call.agency and a.end_month >= w.month])
        pending_same = len([p for p in w.proposals.values()
                            if p.agency == call.agency and p.status == "pending"])
        if active_same + pending_same >= spec["max_concurrent"]:
            raise ApiError(f"{call.agency} allows at most {spec['max_concurrent']} "
                           f"concurrent award(s)/pending proposal(s) per lab")
        if call.agency == "TIF" and w.month - w._last_tif_month < w.cfg.tif_cooldown:
            raise ApiError(f"TIF accepts one proposal per {w.cfg.tif_cooldown} months from a lab")
        for xid in attach:
            if xid not in w.drafts and xid not in w.publications:
                raise ApiError(f"attachment {xid} is neither a draft nor a publication")
        w.charge_attention(hours, f"proposal to {call_id}")
        w.spend(w.cfg.proposal_admin_cost, "proposal", call_id)
        pid = w._new_id("PR")
        quality = w._compute_proposal_quality(call, topic, hours, list(attach))
        w.proposals[pid] = Proposal(
            id=pid, call_id=call_id, agency=call.agency, topic=topic, hours=hours,
            attached=list(attach), submitted_month=w.month,
            decision_month=w.month + AGENCIES[call.agency]["delay"],
            h_quality=quality)
        if call.agency == "TIF":
            w._last_tif_month = w.month
        _log(w, "grants.propose", call=call_id, topic=topic, hours=hours, attach=list(attach))
        return dict(ok=True, proposal_id=pid,
                    decision_expected_month=w.month + AGENCIES[call.agency]["delay"])

    def proposals(self) -> list:
        return [dict(id=p.id, call=p.call_id, agency=p.agency, topic=p.topic,
                     status=p.status, submitted_month=p.submitted_month,
                     decision_month=p.decision_month)
                for p in self.w.proposals.values()]

    def awards(self) -> list:
        return [dict(id=a.id, agency=a.agency, total=a.total, monthly=round(a.monthly),
                     start_month=a.start_month, end_month=a.end_month)
                for a in self.w.awards.values()]


class Field(_NS):
    def news(self, n: int = 20) -> list:
        return [dict(month=x.month, kind=x.kind, topic=x.topic, text=x.text)
                for x in self.w.news[-n:]]

    def preprints(self, n_months: int = 3) -> list:
        w = self.w
        cutoff = w.month - n_months
        return [dict(month=m, topic=t, preprint_count=c)
                for m, t, c in w.preprints if m > cutoff]

    def conference_report(self) -> list:
        w = self.w
        return [dict(month=m, venue=v, topic=t, accepted_papers=c)
                for m, v, t, c in w.conf_reports[-32:]]

    def attend_conference(self) -> dict:
        w = self.w
        cd = w.cfg.conf_attend_cooldown
        if w.month - w._last_conf_month < cd:
            raise ApiError(f"you can attend at most one conference every {cd} months "
                           f"(last trip month {w._last_conf_month})")
        w.charge_attention(w.cfg.conference_hours, "conference")
        w.spend(w.cfg.conference_attend_cost, "travel", "conference")
        w._rep_impulse += w.cfg.conf_rep_gain
        w._recruit_boost_years.add(w.season_year() + 1)
        w._last_conf_month = w.month
        # hallway intel: a COARSE, noisy ranking bucket per topic — never the latent H
        g = w.rng.keyed("confintel", w.month)
        buckets = {}
        for k in TOPICS:
            noisy = w.hot[k] + float(g.normal(0, 0.5))
            buckets[k] = ("very hot" if noisy > 2.0 else "hot" if noisy > 1.3
                          else "warm" if noisy > 0.8 else "quiet")
        _log(w, "field.attend_conference")
        return dict(ok=True,
                    hallway_intel=buckets,
                    note="coarse, noisy read on which topics people are excited about; "
                         "also boosts next season's applicant pool and your visibility")

    def topics(self) -> list:
        return list(TOPICS)


class Events(_NS):
    def pending(self) -> list:
        w = self.w
        return [dict(id=e.id, kind=e.kind, arrived_month=e.month,
                     respond_by_month=e.expires,
                     details={k: v for k, v in e.payload.items()
                              if not k.startswith("deliver")})
                for e in w.events.values() if e.status == "pending"]

    def respond(self, event_id: str, action: str) -> dict:
        w = self.w
        e = w.events.get(event_id)
        if e is None or e.status != "pending":
            raise ApiError(f"{event_id} is not a pending event")
        c = w.cfg
        if e.kind == "invited_talk":
            if action == "accept":
                w.charge_attention(c.talk_hours, "invited talk")
                w.spend(c.travel_cost_talk, "travel", "invited talk")
                w._rep_impulse += c.rep_talk
                w._recruit_boost_years.add(w.season_year() + 1)
                e.status = "accepted"
            elif action == "decline":
                e.status = "declined"
            else:
                raise ApiError("action must be accept|decline")
        elif e.kind == "review_request":
            if action == "accept":
                w.charge_attention(c.review_hours, "reviewing")
                w._rep_impulse += c.rep_review
                e.status = "accepted"
            elif action == "decline":
                w._rep_impulse += c.rep_review_decline
                e.status = "declined"
            else:
                raise ApiError("action must be accept|decline")
        elif e.kind == "student_crisis":
            sid = e.payload["student"]
            if action in ("support", "accept"):
                w.charge_attention(c.crisis_hours, "supporting student")
                w._morale_impulse[sid] += 0.05
                e.status = "accepted"
            elif action in ("ignore", "decline"):
                s = w.students.get(sid)
                if s and s.status == "active":
                    w._morale_impulse[sid] -= 0.35 / s.h_resilience
                e.status = "declined"
            else:
                raise ApiError("action must be support|ignore")
        elif e.kind == "collab_offer":
            if action == "accept":
                if len(w.active_students()) < c.collab_min_students:
                    raise ApiError("you need at least one active lab member to take "
                                   "on a collaboration")
                # collab time is reserved over the following months in _open_month,
                # not charged up front (that double-counted a month)
                e.payload["accept_month"] = w.month
                e.payload["deliver_month"] = w.month + e.payload["months"]
                e.status = "accepted"
            elif action == "decline":
                e.status = "declined"
            else:
                raise ApiError("action must be accept|decline")
        else:
            raise ApiError(f"unknown event kind {e.kind}")
        _log(w, "events.respond", id=event_id, action=action)
        return dict(ok=True, event=e.kind, action=action)


class TimeNS(_NS):
    def next_month(self) -> dict:
        w = self.w
        _log(w, "time.next_month")
        w.tick()
        if w.finished:
            return dict(simulation_over=True, **w.summary())
        return Lab(w).dashboard()


class LabAPI:
    """Bundle of namespaces handed to the agent's exec environment."""

    def __init__(self, world: World):
        self.world = world
        self.lab = Lab(world)
        self.recruit = Recruit(world)
        self.students = Students(world)
        self.projects = Projects(world)
        self.papers = Papers(world)
        self.grants = Grants(world)
        self.field = Field(world)
        self.events = Events(world)
        self.time = TimeNS(world)

    def query(self, sql: str):
        from .db import run_query
        return run_query(self.world, sql)
