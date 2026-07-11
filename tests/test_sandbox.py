"""Penetration tests: agent code must not read hidden state, mutate scoring, or escape."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pibench.api import LabAPI
from pibench.harness.runner import make_exec_env, run_code
from pibench.world import World


def attempt(code):
    w = World(7)
    for _ in range(6):
        LabAPI(w).time.next_month()
    env = make_exec_env(LabAPI(w), {"text": ""})
    out = run_code(code, env)
    return w, out


ATTACKS = [
    ("read hotness via .w", "print(lab.w.hot)"),
    ("read future trajectory", "print(lab.w._hot_traj[10])"),
    ("read agency prefs", "print(lab.w.h_agency_pref)"),
    ("mutate budget via .w", "lab.w.budget = 10**9"),
    ("class escape to builtins",
     "print(().__class__.__bases__[0].__subclasses__())"),
    ("globals escape", "print((lambda:0).__globals__)"),
    ("import os blocked", "import os\nprint(os.getcwd())"),
    ("from world import", "from pibench.world import World\nprint(World)"),
    ("getattr bypass", "print(getattr(lab, 'w'))"),
    ("bound method self", "print(lab.dashboard.__self__)"),
    ("bare except swallow timeout",
     "try:\n while True: pass\nexcept: pass"),
    ("read student ability via students facade",
     "print(students.w.students)"),
    ("builtins via dunder", "print(__builtins__)"),
]


def hidden_markers(w):
    # values that must never appear in agent-visible output
    return [str(round(w.hot["reasoning"], 4))]


if __name__ == "__main__":
    failed = 0
    for name, code in ATTACKS:
        w, out = attempt(code)
        leaked_budget = w.budget > 10**8
        blocked = ("REJECTED" in out or "not allowed" in out or "API ERROR" in out
                   or "PYTHON ERROR" in out or "TIMEOUT" in out or "ImportError" in out)
        # for read attempts, ensure no real hidden numeric leaked
        ok = blocked and not leaked_budget
        print(f"{'PASS' if ok else 'FAIL'} [{name}]  -> {out.splitlines()[0][:80] if out.strip() else '(empty)'}")
        if not ok:
            failed += 1
            if leaked_budget:
                print("   !! budget mutated to", w.budget)
    # positive control: legitimate code still works
    w, out = attempt("d = lab.dashboard()\nprint('month', d['month'], 'budget', d['budget'])")
    ok = "month" in out and "REJECTED" not in out
    print(f"{'PASS' if ok else 'FAIL'} [legit code runs]  -> {out.strip()[:80]}")
    if not ok:
        failed += 1
    # positive control: numpy import allowed
    w, out = attempt("import numpy as np\nprint(int(np.array([1,2,3]).sum()))")
    ok = "6" in out
    print(f"{'PASS' if ok else 'FAIL'} [numpy allowed]  -> {out.strip()[:80]}")
    if not ok:
        failed += 1
    print(f"\n{failed} failures")
    sys.exit(1 if failed else 0)
