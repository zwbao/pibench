"""Minimal terminal-style agent harness.

Context is refreshed every simulated month: only the system prompt, the agent's
memory file, and the current month's interactions are in context — long-horizon
coherence must live in the memory file (same design as CEO-Bench's harness).
"""
from __future__ import annotations

import builtins
import io
import json
import os
import re
import signal
import time
import traceback
from contextlib import redirect_stdout

from ..api import LabAPI
from ..world import ApiError, World
from .llm import LLMClient
from .prompts import MONTH_MSG, NO_CODE_MSG, SYSTEM_PROMPT, TURN_OUTPUT_MSG
from .sandbox import ALLOWED_IMPORTS, SandboxError, build_bindings, sanitize

CODE_RE = re.compile(r"```(?:[Pp]y(?:thon)?[0-9]?)?\s*\n(.*?)```", re.DOTALL)
MAX_OUTPUT_CHARS = 6000
MAX_MEMORY_CHARS = 6000
EXEC_TIMEOUT_S = 20


class _Timeout(BaseException):
    """BaseException so ordinary `except Exception` cannot swallow the timeout;
    the AST sanitizer additionally forbids bare/BaseException handlers."""


def _alarm(signum, frame):
    raise _Timeout()


def _guarded_import(name, *args, **kwargs):
    if name.split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import of '{name}' is not allowed in this environment")
    return builtins.__import__(name, *args, **kwargs)


_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int",
    "len", "list", "map", "max", "min", "print", "range", "repr", "round",
    "set", "sorted", "str", "sum", "tuple", "zip", "isinstance",
    "next", "iter", "frozenset", "pow", "chr", "ord", "abs", "bin", "hex",
    "reversed", "divmod", "format",
    "Exception", "ValueError", "KeyError", "TypeError",
    "AttributeError", "IndexError", "NameError", "ZeroDivisionError",
    "ArithmeticError", "RuntimeError", "ImportError", "StopIteration")


def make_exec_env(api: LabAPI, memory_ref: dict):
    def write_memory(text):
        text = str(text)
        if len(text) > MAX_MEMORY_CHARS:
            text = text[:MAX_MEMORY_CHARS]
            print(f"[memory truncated to {MAX_MEMORY_CHARS} chars]")
        memory_ref["text"] = text
        print("[memory updated]")

    def read_memory():
        return memory_ref["text"]

    safe_builtins = {k: getattr(builtins, k) for k in _SAFE_BUILTIN_NAMES}
    safe_builtins["__import__"] = _guarded_import

    bindings = build_bindings(api, write_memory, read_memory)
    bindings["__builtins__"] = safe_builtins
    env = dict(bindings)
    # agents routinely shadow API names (e.g. `students = students.list()`); the
    # canonical bindings are restored before every turn so the damage stays local
    env["__canonical__"] = bindings
    return env


def run_code(code: str, env: dict) -> str:
    env.update(env.get("__canonical__", {}))
    buf = io.StringIO()
    try:
        tree = sanitize(code)
        compiled = compile(tree, "<agent>", "exec")
    except SandboxError as e:
        return f"REJECTED: {e}"
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(EXEC_TIMEOUT_S)
    try:
        with redirect_stdout(buf):
            try:
                exec(compiled, env)
            except ApiError as e:
                print(f"API ERROR: {e}")
            except _Timeout:
                print(f"EXECUTION TIMEOUT after {EXEC_TIMEOUT_S}s")
            except Exception:
                tb = traceback.format_exc(limit=3)
                print(f"PYTHON ERROR:\n{tb}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    out = buf.getvalue()
    if not out.strip():
        out = "(no output; use print() to see results)"
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + f"\n...[truncated at {MAX_OUTPUT_CHARS} chars]"
    return out


def run_episode(model: str, seed: int, out_dir: str, api_key: str, base_url: str,
                months: int = 60, max_turns: int = 8, temperature: float = 0.4,
                verbose: bool = True) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    world = World(seed)
    world.cfg.months = months
    api = LabAPI(world)
    client = LLMClient(model, api_key, base_url, temperature=temperature)
    memory_ref = {"text": "(empty — use write_memory(text) to save notes)"}
    env = make_exec_env(api, memory_ref)
    transcript_path = os.path.join(out_dir, "transcript.jsonl")
    tlog = open(transcript_path, "a")

    def log(rec: dict):
        tlog.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tlog.flush()

    sys_prompt = SYSTEM_PROMPT.format(months=months, max_turns=max_turns)
    log(dict(type="meta", model=model, seed=seed, months=months,
             max_turns=max_turns, temperature=temperature, ts=time.time()))

    llm_dead = False
    while not world.finished:
        month = world.month
        dashboard = json.dumps(api.lab.dashboard(), ensure_ascii=False, indent=1)
        messages = [dict(role="system", content=sys_prompt),
                    dict(role="user", content=MONTH_MSG.format(
                        month=month, months=months,
                        label=f"Y{(month - 1) // 12 + 1}M{(month - 1) % 12 + 1}",
                        memory=memory_ref["text"], dashboard=dashboard))]
        for turn in range(1, max_turns + 1):
            if llm_dead:
                break
            try:
                reply = client.chat(messages)
            except RuntimeError as e:
                log(dict(type="llm_error", month=month, error=str(e)))
                if client.errors >= 8:
                    llm_dead = True
                break
            log(dict(type="assistant", month=month, turn=turn, content=reply))
            m = CODE_RE.search(reply or "")
            if not m:
                messages.append(dict(role="assistant", content=reply or "(empty)"))
                messages.append(dict(role="user", content=NO_CODE_MSG))
                log(dict(type="nudge", month=month, turn=turn))
                continue
            code = m.group(1)
            output = run_code(code, env)
            log(dict(type="exec", month=month, turn=turn, code=code, output=output))
            if verbose:
                print(f"[{model} s{seed}] m{month} t{turn}: "
                      f"{output.splitlines()[0][:100] if output else ''}")
            if world.finished or world.month != month:
                break
            messages.append(dict(role="assistant", content=reply))
            messages.append(dict(role="user", content=TURN_OUTPUT_MSG.format(
                turn=turn, max_turns=max_turns, output=output)))
        # whatever happened above (turns exhausted, LLM failure, no-advance), the
        # month must move forward exactly once per outer iteration
        if not world.finished and world.month == month:
            log(dict(type="auto_advance", month=month))
            api.time.next_month()

    result = dict(world.summary(), model=model, usage=client.usage(),
                  memory=memory_ref["text"])
    with open(os.path.join(out_dir, "result.json"), "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "monthly_stats.json"), "w") as f:
        json.dump(world.monthly_stats, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "actions.json"), "w") as f:
        json.dump(world.action_log, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "eval.json"), "w") as f:
        json.dump(world.eval_snapshot(), f, ensure_ascii=False)
    tlog.close()
    return result
