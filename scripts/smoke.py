"""Smoke test: scripted policies drive the world end to end without crashing."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pibench.world import World, ApiError
from pibench.api import LabAPI


def do_nothing(seed):
    w = World(seed)
    api = LabAPI(w)
    while not w.finished:
        api.time.next_month()
    return w.summary()


def naive_pi(seed):
    """Hire eagerly, run tier-2 projects on the hottest-news topic, submit everything,
    propose to every call. No budget discipline at all."""
    w = World(seed)
    api = LabAPI(w)
    while not w.finished:
        m = w.month
        try:
            if m % 12 == 1:
                apps = api.recruit.applicants()
                ranked = sorted(apps, key=lambda a: -(a["transcript"] + a["letter"]))
                for a in ranked[:3]:
                    try:
                        api.recruit.offer(a["id"])
                    except ApiError:
                        break
            students = [s for s in api.students.list() if s["status"] == "active"]
            if students:
                alloc = {s["id"]: min(6, 80 // len(students)) for s in students}
                try:
                    api.students.set_mentoring(alloc)
                except ApiError:
                    pass
            free = [s for s in students
                    if not any(s["id"] in p["members"] for p in api.projects.list()
                               if p["status"] == "active")]
            if free:
                news = api.field.news(30)
                counts = {}
                for x in news:
                    if x["kind"] == "field" and x["topic"]:
                        counts[x["topic"]] = counts.get(x["topic"], 0) + 1
                topic = max(counts, key=counts.get) if counts else "reasoning"
                try:
                    api.projects.start(topic, 2, [s["id"] for s in free[:2]], 1000)
                except ApiError:
                    pass
            for d in api.papers.drafts():
                if d["status"] == "available":
                    dash = api.lab.dashboard()
                    for v in ["NAIC", "CLAR", "W-SHOP"]:
                        try:
                            api.papers.submit(d["id"], v)
                            break
                        except ApiError:
                            continue
            for c in api.grants.calls():
                try:
                    pubs = [p["id"] for p in api.papers.publications()][:3]
                    api.grants.propose(c["id"], "reasoning", 20, pubs)
                except ApiError:
                    pass
            for e in api.events.pending():
                try:
                    api.events.respond(e["id"],
                                       "support" if e["kind"] == "student_crisis" else "accept")
                except ApiError:
                    try:
                        api.events.respond(e["id"], "decline")
                    except ApiError:
                        pass
        except ApiError as e:
            print("  policy error:", e)
        api.time.next_month()
    return w.summary()


if __name__ == "__main__":
    for seed in (1, 2, 3):
        s = do_nothing(seed)
        print(f"seed {seed} do-nothing : impact={s['impact']:8.1f} survived={s['months_survived']} "
              f"budget={s['final_budget']:10.0f} collapsed={s['collapsed']}")
    for seed in (1, 2, 3):
        s = naive_pi(seed)
        print(f"seed {seed} naive-pi   : impact={s['impact']:8.1f} survived={s['months_survived']} "
              f"budget={s['final_budget']:10.0f} pubs={s['publications']} grants={s['grants_won']} "
              f"quit={s['students_quit']} collapsed={s['collapsed']}")
    # determinism check
    a, b = naive_pi(7), naive_pi(7)
    assert a == b, "same seed + same policy must be identical"
    print("determinism check passed")
    # SQL check
    w = World(11)
    api = LabAPI(w)
    for _ in range(14):
        api.time.next_month()
    rows = api.query("SELECT topic, SUM(preprint_count) n FROM preprint_feed "
                     "GROUP BY topic ORDER BY n DESC LIMIT 3")
    print("top preprint topics @m15:", rows)
    print("dashboard keys:", sorted(api.lab.dashboard().keys()))
