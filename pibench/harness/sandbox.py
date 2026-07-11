"""Hardened execution sandbox for agent code.

Two layers of defense so agent code cannot reach hidden world state or escape:

1. Facades. The agent never receives the real API namespace objects (which hold a
   ``.w`` reference to the World). Each namespace is wrapped in a facade exposing
   ONLY whitelisted public methods, each re-bound through a plain closure so it has
   no ``__self__`` chain back to the World. There is no ``.w`` / ``.world`` / ``.rng``
   attribute anywhere on what the agent can touch.
2. AST sanitizer. Before execution, the code is parsed and rejected if it uses any
   dunder attribute/name (``__globals__``, ``__class__``, ``__builtins__``,
   ``__subclasses__``, ``__self__``, ...), a bare/too-broad ``except``, or imports
   outside the allowlist. This blocks the standard ``().__class__.__bases__`` style
   escapes and stops the execution timeout from being swallowed.

Combined with a restricted ``__builtins__`` (no ``getattr``/``setattr``/``vars``/
``eval``/``exec``/``open``/``type``), agent code is confined to the API surface.
"""
from __future__ import annotations

import ast

ALLOWED_IMPORTS = {"math", "json", "statistics", "itertools", "collections",
                   "random", "re", "functools", "heapq", "numpy", "datetime"}

# Public method whitelist per namespace (must match api.py).
FACADE_METHODS = {
    "lab": ["dashboard", "ledger", "attention"],
    "recruit": ["applicants", "interview", "offer", "post_postdoc", "renew_postdoc"],
    "students": ["list", "set_mentoring", "reports"],
    "projects": ["list", "start", "set_compute", "assign", "unassign", "kill"],
    "papers": ["drafts", "polish", "submit", "revise", "withdraw", "submissions",
               "publications"],
    "grants": ["calls", "propose", "proposals", "awards"],
    "field": ["news", "preprints", "conference_report", "attend_conference", "topics"],
    "events": ["pending", "respond"],
}


class SandboxError(Exception):
    """Raised by the AST sanitizer; message is shown to the agent."""


class _Facade:
    """Holds only closures; no reference to the World is reachable by attribute."""
    __slots__ = ()   # no __dict__ enumeration surface beyond the bound closures


def _make_facade(target, method_names):
    ns = {}
    for name in method_names:
        real = getattr(target, name)

        def call(*args, _real=real, **kwargs):
            return _real(*args, **kwargs)

        ns[name] = staticmethod(call)
    cls = type("Facade", (_Facade,), ns)
    return cls()


class _Sanitizer(ast.NodeVisitor):
    def __init__(self):
        self.errors = []

    def visit_Attribute(self, node):
        if node.attr.startswith("__") or node.attr in ("w", "world", "rng",
                                                        "cfg", "students", "projects"):
            # dunder attrs enable escapes; the named ones would reach engine internals
            if node.attr.startswith("__") or node.attr in ("w", "world", "rng", "cfg"):
                self.errors.append(f"attribute access '.{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id.startswith("__") and node.id.endswith("__"):
            self.errors.append(f"name '{node.id}' is not allowed")
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                self.errors.append(f"import of '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
            self.errors.append(f"import from '{node.module}' is not allowed")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        # a bare `except:` or `except BaseException` can swallow the exec timeout
        if node.type is None:
            self.errors.append("bare 'except:' is not allowed (use 'except Exception')")
        elif isinstance(node.type, ast.Name) and node.type.id in ("BaseException",):
            self.errors.append("'except BaseException' is not allowed")
        elif isinstance(node.type, ast.Tuple):
            for elt in node.type.elts:
                if isinstance(elt, ast.Name) and elt.id == "BaseException":
                    self.errors.append("'except BaseException' is not allowed")
        self.generic_visit(node)


def sanitize(code: str):
    """Parse and validate agent code; raise SandboxError on violations."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxError(f"SyntaxError: {e}")
    s = _Sanitizer()
    s.visit(tree)
    if s.errors:
        raise SandboxError("; ".join(dict.fromkeys(s.errors)))
    return tree


def build_bindings(api, write_memory, read_memory):
    """The names the agent sees. World is unreachable from all of them."""
    def query(sql):
        return api.query(sql)

    def next_month():
        return api.time.next_month()

    bindings = dict(query=query, next_month=next_month,
                    write_memory=write_memory, read_memory=read_memory)
    for ns_name, methods in FACADE_METHODS.items():
        bindings[ns_name] = _make_facade(getattr(api, ns_name), methods)
    return bindings
