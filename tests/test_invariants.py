"""Invariant tests for the PIBench world. Plain-python asserts; run directly."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pibench.api import LabAPI
from pibench.world import ApiError, World


def fresh(seed=42):
    w = World(seed)
    return w, LabAPI(w)


def test_determinism():
    def play(seed):
        w, api = fresh(seed)
        for _ in range(24):
            if w.month % 12 == 1:
                for a in api.recruit.applicants()[:2]:
                    try:
                        api.recruit.offer(a["id"])
                    except ApiError:
                        pass
            act = [s for s in api.students.list() if s["status"] == "active"]
            if act and not [p for p in api.projects.list() if p["status"] == "active"]:
                api.projects.start("reasoning", 2, [act[0]["id"]], 500)
            api.time.next_month()
        return w.summary()
    assert play(5) == play(5), "same seed+policy must produce identical outcomes"


def test_consistency_under_unrelated_actions():
    """An extra no-op-ish action (a SQL query / an extra dashboard read / an interview)
    must not change the field trajectory or an unrelated review outcome."""
    def play(extra):
        w, api = fresh(9)
        for _ in range(30):
            if w.month == 2 and extra:
                api.query("SELECT COUNT(*) c FROM news")
                api.lab.dashboard()
            if w.month % 12 == 1:
                for a in api.recruit.applicants()[:1]:
                    try:
                        api.recruit.offer(a["id"])
                    except ApiError:
                        pass
            act = [s for s in api.students.list() if s["status"] == "active"]
            if act and not [p for p in api.projects.list() if p["status"] == "active"]:
                api.projects.start("theory", 1, [act[0]["id"]], 200)
            for d in api.papers.drafts():
                if d["status"] == "available":
                    try:
                        api.papers.submit(d["id"], "W-SHOP")
                    except ApiError:
                        pass
            api.time.next_month()
        hot_series = tuple(round(s["hot"]["reasoning"], 6) for s in w.monthly_stats)
        subs = tuple((s.id, s.status, tuple(s.reviewer_scores or []))
                     for s in w.submissions.values())
        return hot_series, subs
    a, b = play(False), play(True)
    assert a[0] == b[0], "field trajectory must be agent-independent"
    assert a[1] == b[1], "review outcomes must not depend on unrelated actions"


def test_no_hidden_leaks_in_db():
    w, api = fresh(7)
    for _ in range(15):
        api.time.next_month()
    from pibench.db import build_db
    con = build_db(w)
    for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        for c in cols:
            lc = c.lower()
            assert not lc.startswith("h_"), f"{table}.{c} leaks hidden field"
            assert lc not in ("q", "quality", "hotness", "crowding", "morale",
                              "ability", "feasible", "novelty"), \
                f"{table}.{c} leaks hidden state"
    con.close()


def test_dashboard_and_api_no_leaks():
    import json as _json
    w, api = fresh(13)
    for _ in range(18):
        api.time.next_month()
    blob = _json.dumps([api.lab.dashboard(), api.students.list(),
                        api.projects.list(), api.papers.drafts(),
                        api.papers.submissions(), api.grants.proposals()])
    for token in ('"h_ability"', '"h_morale"', '"h_quality"', '"novelty"',
                  '"h_feasible"', '"q":'):
        assert token not in blob, f"API output leaks {token}"


def test_attention_hard_budget():
    w, api = fresh(21)
    try:
        api.papers.polish  # touch
        api.grants.propose("TIF-rolling", "reasoning", 200, [])
        assert False, "should have raised (200h > pool)"
    except ApiError:
        pass
    # fill attention then overflow
    api.grants.propose("TIF-rolling", "reasoning", 90, [])
    try:
        api.field.attend_conference()  # 15h > 10h left
        assert False, "attention overdraft allowed"
    except ApiError:
        pass


def test_bankruptcy_ends_run():
    w, api = fresh(33)
    w.budget = 1000.0
    # hire nothing; burn via compute-heavy project impossible without students;
    # force spend directly
    w.spend(2000, "test", "force")
    api.time.next_month()
    assert w.collapsed and w.finished, "budget < 0 must end the run"
    assert w.impact() == w.impact()  # callable post-collapse
    assert w.projected_future_citations() == 0.0, "collapse forfeits projection"


def test_recruiting_timeline():
    w, api = fresh(55)
    apps = api.recruit.applicants()
    assert apps, "applications must be open in month 1"
    api.recruit.offer(apps[0]["id"])
    for _ in range(4):
        api.time.next_month()   # closes months 1-4; arrival resolves at tick of m4
    st = api.students.list()
    assert w.month == 5
    a = w.applicants[apps[0]["id"]]
    assert a.status in ("joined", "declined"), f"offer unresolved: {a.status}"
    if a.status == "joined":
        assert any(s["arrived_month"] == 5 for s in st)


def test_max_students_enforced():
    w, api = fresh(77)
    w.cfg.max_students = 1
    apps = api.recruit.applicants()
    if len(apps) >= 2:
        api.recruit.offer(apps[0]["id"])
        try:
            api.recruit.offer(apps[1]["id"])
            assert False, "capacity not enforced"
        except ApiError:
            pass


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failed else 0)
