"""Deterministically replay a run's action log to reconstruct the full world state.

The world is deterministic given (seed, action sequence), so replaying actions.json
against a fresh World reproduces the run EXACTLY — including per-publication citations
and hidden state — at zero API cost. The action log stores display-arg names; we map
them to each API method's real signature here.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pibench.world import World, ApiError
from pibench.api import LabAPI

# (namespace.method) -> (method_name, [(logged_arg, call_kwarg), ...])
MAP = {
    "recruit.interview":     ("interview", [("ids", "applicant_ids")]),
    "recruit.offer":         ("offer", [("id", "applicant_id")]),
    "recruit.post_postdoc":  ("post_postdoc", []),
    "recruit.renew_postdoc": ("renew_postdoc", [("id", "student_id")]),
    "recruit.hire_ra":       ("hire_ra", []),
    "recruit.hire_manager":  ("hire_manager", []),
    "recruit.dismiss":       ("dismiss", [("id", "staff_id")]),
    "students.set_mentoring": ("set_mentoring", [("alloc", "hours_by_student")]),
    "projects.start":        ("start", [("topic", "topic"), ("tier", "tier"),
                                        ("members", "members"), ("compute", "monthly_compute")]),
    "projects.set_compute":  ("set_compute", [("id", "project_id"), ("compute", "monthly_compute")]),
    "projects.assign":       ("assign", [("project", "project_id"), ("student", "student_id")]),
    "projects.unassign":     ("unassign", [("project", "project_id"), ("student", "student_id")]),
    "projects.kill":         ("kill", [("id", "project_id")]),
    "papers.polish":         ("polish", [("id", "draft_id"), ("hours", "hours")]),
    "papers.submit":         ("submit", [("draft", "draft_id"), ("venue", "venue")]),
    "papers.revise":         ("revise", [("id", "draft_id"), ("hours", "hours")]),
    "papers.withdraw":       ("withdraw", [("id", "submission_id")]),
    "grants.propose":        ("propose", [("call", "call_id"), ("topic", "topic"),
                                          ("hours", "hours"), ("attach", "attach")]),
    "field.attend_conference": ("attend_conference", []),
    "events.respond":        ("respond", [("id", "event_id"), ("action", "action")]),
    "time.next_month":       ("next_month", []),
}


def replay(model: str, seed: int, exp: str = "exp2") -> World:
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "runs", exp, f"{model.replace('/', '_')}_s{seed}")
    acts = json.load(open(os.path.join(d, "actions.json")))
    w = World(seed)
    api = LabAPI(w)
    ns = dict(lab=api.lab, recruit=api.recruit, students=api.students,
              projects=api.projects, papers=api.papers, grants=api.grants,
              field=api.field, events=api.events, time=api.time)
    for a in acts:
        spec = MAP.get(a["action"])
        if not spec:
            continue
        meth, argmap = spec
        obj = ns[a["action"].split(".")[0]]
        kwargs = {ck: a["args"][lk] for lk, ck in argmap if lk in a["args"]}
        try:
            getattr(obj, meth)(**kwargs)
        except ApiError:
            pass  # an action that failed live also fails here — consistent
    return w


if __name__ == "__main__":
    # verify replay reproduces a known run
    r = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "runs/exp2/qwen-turbo_s101/result.json")))
    w = replay("qwen-turbo", 101)
    pubs = len([p for p in w.publications.values() if p.published_month <= w.month])
    print(f"original: impact={r['impact']} pubs={r['publications']} cites={r['citations']}")
    print(f"replay:   impact={w.impact():.1f} pubs={pubs} "
          f"cites={sum(p.citations for p in w.publications.values())}")
    print(f"MATCH: {abs(w.impact() - r['impact']) < 1 and pubs == r['publications']}")
