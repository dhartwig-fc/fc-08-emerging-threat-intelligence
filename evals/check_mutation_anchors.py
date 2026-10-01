"""
Pin what every guard's mutations reach by name, statically: a TEXT mutation's anchor must still occur in its
target exactly as the guard requires, and an attribute an EXEMPT guard rebinds by name must still exist in its
target module -- so no `--mutate` can go silently dead while tools/check_all.py stays green.

Usage:
    python evals/check_mutation_anchors.py
    python evals/check_mutation_anchors.py --mutate duplicate-anchor        # a real anchor appears twice (temp copy)
    python evals/check_mutation_anchors.py --mutate missing-anchor          # a real anchor is absent (temp copy)
    python evals/check_mutation_anchors.py --mutate unlisted-guard          # a new evals/check_*.py is in no group
    python evals/check_mutation_anchors.py --mutate label-added-in-function # a table gains a label inside a function
    python evals/check_mutation_anchors.py --mutate renamed-rebind-target   # pb._EMAIL's target name is renamed

WHY. tools/check_all.py runs every guard plain and never runs a mutation, so a label that can no longer apply
is dead and nothing goes red. Two shapes, both measured:
  text      most labels replace an exact snippet of a source file and refuse to run ("MUTATION TARGET
            MISSING") unless it is there exactly once. Commit 03d21b1 gave tools/friday_run.py a second copy of
            the line `check_friday_run --mutate telemetry-elsewhere` was anchored on; that label could not run
            until it was re-anchored on 2026-09-30 (b0bbfda's review then ran all 103 labels of five guards and
            found none dead);
  rebind    an EXEMPT guard's labels rebind a module attribute by name (`pb._EMAIL = None`,
            `.model_validators.pop("_reviewer_additions_carry_their_reason", None)`). Rename the attribute and the
            assignment silently creates a NEW one: measured in the anchor review (2026-10-01), check_publish_boundary
            --mutate no-email and check_added_by --mutate then print NOTHING PROVED while their plain runs HOLD.

WHAT IT HOLDS:
  groups    every evals/check_*.py is in exactly one of CHECKED (text-mutation tables), EXEMPT (labels applied in
            code, each with a one-line reason) or NO_MUTATIONS, and every name listed exists. A NEW guard in none
            of them is a failure;
  tables    for each CHECKED guard, every table named for it reads statically (ast, never an import), wherever
            it is defined -- module level, or once inside a function -- is a dict literal, is not modified
            anywhere after it is defined (function bodies included: a label added in main() would be invisible),
            and yields at least one anchor; no OTHER dict named *MUTATIONS*, at any level, goes unread;
  rule      each table's LOADER -- every function that indexes the table and calls .replace -- carries the
            guard's own exactly-once predicate (`source.count(old) != 1`, `src.count(anchor) == 1`, ...). Per
            loader, not per file: check_accept_run and check_feeds_server have two loaders each. All 13 checked
            guards require EXACTLY ONCE, read from each loader;
  anchors   for every (target, old) of every table, the target exists and `old` occurs in it exactly once;
  rebinds   in every EXEMPT guard, every attribute rebound by name -- `alias.attr = ...` (tuple targets and
            chains such as `bw.telemetry.TELEMETRY_DIR` included), `del alias.attr`, setattr/delattr with a
            literal name, `<Class>.__pydantic_decorators__.<kind>.pop("name")`, `<x>.__dict__.pop("name")` and
            `dataclasses.replace(o, field=...)` -- is resolved to its target: the alias through the guard's own
            imports, importlib loads (`module_from_spec(spec_from_file_location(_, <path>))`), helper functions
            returning one, and parameters every call site fills with one; then the name is found in the target
            module's source with ast (module-level binding, class body member, or submodule). Setup rebinds
            count too: a renamed TELEMETRY_DIR would point a guard's temp redirect at nothing while it writes
            the real one. A site the reader cannot resolve FAILS unless it is in KNOWN_UNCOVERED, with guard,
            label and reason; that list's size is pinned, and an entry that no longer matches a site fails;
  exempt    an EXEMPT or NO_MUTATIONS guard carries no text-mutation marker and no *MUTATIONS* dict; a
            NO_MUTATIONS guard has no "--mutate";
  writes    `git status` succeeds and is unchanged by the run (a failed `git status` is a failure, not "unchanged").

STATIC. It never runs a mutation and never imports a guard or a target. Its limits: an anchor or name found is
not a mutation proved effective (only running the label shows that), and it reads no DATA-key or switch-string
mutation -- a dict key edited in memory (check_digest_routing's `suggestion_only_desks`, check_feeds_catalogue's
copies, check_actor_resolution's FLAGS kwargs) or a `_MUTATE == "label"` branch string in a tool.

NOT A VACUOUS PASS. At least MIN_ANCHORS anchors and MIN_REBINDS rebind sites are examined (pinned to the counts
measured 2026-10-01, and printed, with how many guards contributed); every CHECKED table must contribute an
anchor, and an unresolvable rebind site can never count towards the floor. Each --mutate plants its defect in a TEMPORARY copy (a target file, or the guards
folder) and points the same examination at it; at least one check must fail.
"""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
SELF = Path(__file__).name
ROOT_EXPR = "Path(__file__).resolve().parent.parent"  # every guard's ROOT, measured: 32 of 32
SEARCH = ("", "evals", "tools")  # the import roots the guards put on sys.path (ROOT, evals/, tools/), measured

# Table shapes: which tuple element is the target and which is the anchor (`new` is never read).
PATH_OLD = "path-old-new"  # (Path expression, old, new)
OLD_ONLY = "old-new"       # (old, new); the target is the one module-level path named in the spec
KEY_OLD = "key-old-new"    # (key into a module-level dict of paths, old, new)
LOCAL = "local-anchor"     # `anchor = "..."` inside the named function; the target is named in the spec

ONCE = "source.count(old) != 1"
# guard -> ((table, shape, target, rule snippets that must all be in each of the table's loaders), ...)
CHECKED = {
    "check_accept_run.py": (("MUTATIONS", OLD_ONLY, "ACCEPT", (ONCE,)),
                            ("RUNS_MUTATIONS", OLD_ONLY, "RUNS", (ONCE,))),
    "check_citation_match.py": (("MUTATIONS", OLD_ONLY, "MATCHER", ("src.count(old) != 1",)),),
    "check_document_pages.py": (("MUTATIONS", PATH_OLD, None, (ONCE,)),),
    "check_feed_adapters.py": (("MUTATIONS", PATH_OLD, None, (ONCE,)),),
    "check_feeds_extract.py": (("MUTATIONS", PATH_OLD, None, (ONCE,)),),
    "check_feeds_ledger.py": (("MUTATIONS", PATH_OLD, None, (ONCE,)),),
    "check_feeds_score.py": (("MUTATIONS", OLD_ONLY, "SCORER", (ONCE,)),),
    "check_feeds_server.py": (("MUTATIONS", OLD_ONLY, "SERVER", (ONCE,)),
                              ("HTTP_MUTATIONS", OLD_ONLY, "HTTP_PY", (ONCE,))),
    "check_feeds_triage.py": (("MUTATIONS", PATH_OLD, None, ("sources[path].count(old) != 1",)),),
    "check_friday_run.py": (("MUTATIONS", KEY_OLD, "FILES", (ONCE,)),),
    "check_html_pages.py": (("MUTATIONS", OLD_ONLY, "RULE", (ONCE,)),),
    "check_schedule.py": (("TEXT_MUTATIONS", PATH_OLD, None, (ONCE,)),),
    # No table: two recompile helpers each hold one `anchor`, applied to Path(telemetry.__file__), which is
    # agents/telemetry.py (the guard's own `from agents import telemetry`). The helper is its own loader.
    "check_telemetry.py": (("_recompile_unhooked", LOCAL, "agents/telemetry.py",
                            ("src.count(anchor) == 1", "Path(telemetry.__file__).read_text")),
                           ("_recompile_run_started", LOCAL, "agents/telemetry.py",
                            ("src.count(anchor) == 1", "Path(telemetry.__file__).read_text"))),
}
LOCAL_LABELS = {"_recompile_unhooked": "unhooked-success|unhooked-none", "_recompile_run_started": "drop-prompt-sha"}
LOCAL_IMPORT = "from agents import telemetry"  # check_telemetry's binding of the module its anchors target

EXEMPT = {
    "check_actor_resolution.py": "--mutate sets resolver/builder FLAGS or rebinds kc.resolve_names in memory",
    "check_added_by.py": "--mutate pops the pydantic model validator in memory",
    "check_attestations.py": "--mutate sets check_citations._MUTATE, a code switch",
    "check_citation_repair.py": "--mutate sets tools/apply_citation_repair.py's _MUTATE, a code switch",
    "check_digest_batch.py": "--mutate passes --_mutate to tools/build_digests.py, a code switch",
    "check_digest_routing.py": "--mutate rebinds routing data and digest functions in memory",
    "check_emergent_threshold.py": "--mutate tests at the unsafe threshold value; no source text",
    "check_feeds_catalogue.py": "--mutate edits a deep copy of the loaded catalogue and labels in memory",
    "check_feeds_orchestrator.py": "its 12 labels are applied in process by `if mutation == ...` (options, "
                                   "constants, prompt strings in memory); no source anchor",
    "check_feeds_runner.py": "--mutate rebinds runner functions in memory (mutate())",
    "check_proposal_contract.py": "--mutate rebinds the server's refusal functions in memory",
    "check_publish_boundary.py": "--mutate empties the boundary's pattern tuples in memory",
    "check_publisher.py": "--mutate patches publisher/builder functions in memory (MUTATION == ...)",
    "check_review_gate.py": "--mutate rebinds gate functions in memory",
    "check_tool_surface.py": "--mutate* replace the options object or QUEUE_DIR in memory",
    "check_twin_pairs.py": "--mutate empties the twin map in memory",
    "check_walkthrough.py": "--mutate sets tools/build_walkthrough.py's _MUTATE (or a guard-side read), a code switch",
    SELF: "its own labels plant temporary copies in code; it has no text table",
}
NO_MUTATIONS = ("check_citations.py", "check_published_walkthrough.py")

# A text-mutation loader leaves one of these in its source; an EXEMPT or NO_MUTATIONS guard must carry none.
MARKERS = ("MUTATION TARGET MISSING", "MUTATION DOES NOT APPLY", ".count(old)", ".count(anchor)")

# Rebind sites the static reader cannot resolve to a name in a repository module, by (guard, site, label).
# The size is pinned: a NEW unresolvable site fails until it is listed here with its reason.
_SDK_FIELD = ("a field of claude_agent_sdk's ClaudeAgentOptions, an installed package outside the repository; a "
              "renamed field raises TypeError when the label runs -- loud, but only when it runs")
KNOWN_UNCOVERED = {
    ("check_feeds_orchestrator.py", "module.__file__", "(setup)"):
        "set on a FRESH types.ModuleType the guard builds itself; nothing in the repository is rebound",
    ("check_feeds_orchestrator.py", "dataclasses.replace(o, tools=...)", "builtin-tools"): _SDK_FIELD,
    ("check_feeds_orchestrator.py", "dataclasses.replace(o, setting_sources=...)", "settings"): _SDK_FIELD,
    ("check_feeds_orchestrator.py", "dataclasses.replace(o, allowed_tools=...)", "preapprove-triage"): _SDK_FIELD,
    ("check_feeds_runner.py", "session.calls", "(setup)"):
        "an attribute on the guard's own wrapper function (counted()); nothing in the repository is rebound",
    ("check_tool_surface.py", "dataclasses.replace(o, mcp_servers=...)", "(setup)"): _SDK_FIELD,
    ("check_tool_surface.py", "dataclasses.replace(o, can_use_tool=...)", "(any label)"): _SDK_FIELD,
    ("check_tool_surface.py", "dataclasses.replace(o, tools=...)", "(any label)"): _SDK_FIELD,
    ("check_tool_surface.py", "transport._cli_path", "(setup)"):
        "an SDK transport instance attribute; the guard itself raises if hasattr(transport, '_cli_path') is false",
    ("check_walkthrough.py", "replace(pinned[-1], decided_at=...)", "(setup)"):
        "a field of a decision-log entry reached through a list element the reader cannot type; a renamed field "
        "raises TypeError in the PLAIN run, which check_all does run",
    ("check_walkthrough.py", "replace(pinned[-1], decision=...)", "(setup)"):
        "as decided_at: a decision-log entry field; a rename raises TypeError in the plain run",
    ("check_walkthrough.py", "replace(pinned[-1], note=...)", "(setup)"):
        "as decided_at: a decision-log entry field; a rename raises TypeError in the plain run",
}
KNOWN_UNCOVERED_SIZE = 12  # 2026-10-01: 12 entries covering 14 sites (two sites repeat an entry's shape)

MIN_ANCHORS = 178  # measured 2026-10-01 at 075744b: 178 anchors across 13 guards. A floor, not a pin.
MIN_REBINDS = 101  # measured 2026-10-01: 101 rebind sites across 14 exempt guards. A floor, not a pin.

MUTATIONS = ("duplicate-anchor", "missing-anchor", "unlisted-guard", "label-added-in-function",
             "renamed-rebind-target")
# The incident shape: the anchor 03d21b1 duplicated, now re-anchored on the comment above it.
DUPLICATE = ("check_friday_run.py", "telemetry-elsewhere")
MISSING = ("check_accept_run.py", "whole-run-refusal")  # a multi-line anchor
UNLISTED = "check_zz_unlisted_probe.py"
# The anchor review's measured case: a label added inside main(), invisible to a module-level reader.
IN_FUNCTION = ("check_html_pages.py", "def main(argv: list) -> int:\n",
               "def main(argv: list) -> int:\n    MUTATIONS['zz-dead'] = ('THIS ANCHOR IS NOWHERE', 'x')\n")
# The anchor review's measured rebind case: check_publish_boundary --mutate no-email sets pb._EMAIL.
RENAMED = ("governance/publish_boundary.py", "_EMAIL", "_EMAIL_RENAMED")


class Unreadable(Exception):
    """A table, entry or site that this guard cannot read statically: a failure, never a skip."""


class Reader:
    """Reads a file's text, a temporary copy standing in for it when `redirect` names one."""

    def __init__(self, redirect=None):
        self.redirect = redirect or {}

    def text(self, path: Path) -> str:
        return self.redirect.get(path, path).read_text(encoding="utf-8")

    def exists(self, path: Path) -> bool:
        return self.redirect.get(path, path).exists()


# ---------------------------------------------------------------- tables and anchors

def assigns_in(nodes) -> dict:
    """name -> [value node, ...] for every `name = ...` among `nodes`, in order."""
    out: dict = {}
    for node in nodes:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            out.setdefault(node.targets[0].id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            out.setdefault(node.target.id, []).append(node.value)
    return out


def functions(tree: ast.Module) -> list:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def evaluate(node, assigns: dict, root: Path, seen=()):
    """The literal value of `node`: constants, dicts, Path / "x", "a" + "b", and names whose own values are
    those. ROOT is the repository root, and only if the guard defines it the way all 32 do."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        values = assigns.get(node.id, [])
        if node.id == "ROOT":
            if len(values) != 1 or ast.unparse(values[0]) != ROOT_EXPR:
                raise Unreadable("ROOT is not defined once as %s" % ROOT_EXPR)
            return root
        if node.id in seen or len(values) != 1:
            raise Unreadable("%s is not one assignment" % node.id)
        return evaluate(values[0], assigns, root, seen + (node.id,))
    if isinstance(node, ast.BinOp):
        left, right = evaluate(node.left, assigns, root, seen), evaluate(node.right, assigns, root, seen)
        if isinstance(node.op, ast.Div) and isinstance(left, Path) and isinstance(right, str):
            return left / right
        if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
            return left + right
    if isinstance(node, ast.Dict) and None not in node.keys:
        return {evaluate(k, assigns, root, seen): evaluate(v, assigns, root, seen)
                for k, v in zip(node.keys, node.values)}
    raise Unreadable("not a literal: %s" % ast.unparse(node)[:80])


def modified(tree: ast.Module, name: str) -> list:
    """Statements ANYWHERE (function bodies included) that change table `name` after its definition:
    NAME[...] = ..., del NAME[...], NAME += ..., NAME.update(...) and the like."""
    out = []
    for sub in ast.walk(tree):
        hit = ((isinstance(sub, ast.Subscript) and isinstance(sub.ctx, (ast.Store, ast.Del))
                and isinstance(sub.value, ast.Name) and sub.value.id == name)
               or (isinstance(sub, ast.AugAssign) and isinstance(sub.target, ast.Name) and sub.target.id == name)
               or (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                   and isinstance(sub.func.value, ast.Name) and sub.func.value.id == name
                   and sub.func.attr in ("update", "setdefault", "pop", "popitem", "clear", "__setitem__")))
        if hit:
            out.append("line %d" % sub.lineno)
    return out


def dict_tables(tree: ast.Module) -> list:
    """Every name containing MUTATIONS bound to a dict literal, at ANY level -- the shape of a text table."""
    return sorted({n.targets[0].id for n in ast.walk(tree) if isinstance(n, ast.Assign) and len(n.targets) == 1
                   and isinstance(n.targets[0], ast.Name) and "MUTATIONS" in n.targets[0].id
                   and isinstance(n.value, ast.Dict)})


def find_table(tree: ast.Module, name: str) -> tuple:
    """(dict node, assigns to evaluate it against): the module-level definition, else the ONE function that
    defines it (its own names first, then the module's)."""
    module = assigns_in(tree.body)
    places = [(module, module)] if name in module else []
    for fn in functions(tree):
        local = assigns_in(ast.walk(fn))
        if name in local:
            places.append((local, {**module, **local}))
    if len(places) != 1 or len(places[0][0][name]) != 1 or not isinstance(places[0][0][name][0], ast.Dict):
        raise Unreadable("%s is not one dict literal defined in one place" % name)
    return places[0][0][name][0], places[0][1]


def loaders(tree: ast.Module, spec) -> list:
    """The functions that apply a table: they index it AND call .replace. For a LOCAL spec, the helper."""
    name, shape = spec[0], spec[1]
    if shape == LOCAL:
        return [f for f in functions(tree) if f.name == name]
    return [f for f in functions(tree)
            if any(isinstance(s, ast.Subscript) and isinstance(s.value, ast.Name) and s.value.id == name
                   for s in ast.walk(f))
            and any(isinstance(s, ast.Call) and isinstance(s.func, ast.Attribute) and s.func.attr == "replace"
                    for s in ast.walk(f))]


def table_rows(tree: ast.Module, spec, root: Path) -> list:
    """[(label, target Path or None, old or None, error or None), ...] for one table of one guard."""
    name, shape, target, _rule = spec
    if shape == LOCAL:
        fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(fns) != 1:
            raise Unreadable("no single module-level function %s" % name)
        anchors = [n.value.value for n in ast.walk(fns[0]) if isinstance(n, ast.Assign) and len(n.targets) == 1
                   and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "anchor"
                   and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
        if len(anchors) != 1:
            raise Unreadable("%s has %d literal `anchor = ...` assignments, not 1" % (name, len(anchors)))
        return [(LOCAL_LABELS.get(name, name), root / target, anchors[0], None)]
    table, assigns = find_table(tree, name)
    changed = modified(tree, name)
    if changed:
        raise Unreadable("%s is modified after its definition (%s)" % (name, ", ".join(changed)))
    fixed = evaluate(ast.Name(target), assigns, root) if shape in (OLD_ONLY, KEY_OLD) else None
    rows = []
    for k, v in zip(table.keys, table.values):
        label = k.value if isinstance(k, ast.Constant) else ast.unparse(k)
        try:
            if not isinstance(v, ast.Tuple) or len(v.elts) != (2 if shape == OLD_ONLY else 3):
                raise Unreadable("entry is not a %s tuple" % shape)
            if shape == OLD_ONLY:
                path, old = fixed, evaluate(v.elts[0], assigns, root)
            elif shape == KEY_OLD:
                key = evaluate(v.elts[0], assigns, root)
                if key not in fixed:
                    raise Unreadable("%r is not a key of %s" % (key, target))
                path, old = fixed[key], evaluate(v.elts[1], assigns, root)
            else:
                path, old = evaluate(v.elts[0], assigns, root), evaluate(v.elts[1], assigns, root)
            if not isinstance(path, Path) or not isinstance(old, str) or not old:
                raise Unreadable("target %r / anchor %r is not a path and a non-empty string" % (path, old))
            rows.append((label, path, old, None))
        except Unreadable as exc:
            rows.append((label, None, None, str(exc)))
    return rows


# ---------------------------------------------------------------- rebinds

def module_file(dotted: str, root: Path, read: Reader):
    """The repository file a dotted import names, searched as the guards' sys.path does; None if external."""
    parts = dotted.split(".")
    for base in SEARCH:
        p = (root / base if base else root).joinpath(*parts)
        for cand in (p.parent / (p.name + ".py"), p / "__init__.py"):
            if read.exists(cand):
                return cand
    return None


def top_bindings(tree: ast.Module) -> dict:
    """name -> the node binding it at module level (descending into if/try/with, never into a function or
    class), plus names a function declares `global` and assigns."""
    out: dict = {}

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.setdefault(node.name, node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    out.setdefault(a.asname or a.name.split(".")[0], node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            out.setdefault(n.id, node)
            for field in ("body", "orelse", "finalbody", "handlers"):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    sub = getattr(node, field, None)
                    if isinstance(sub, list):
                        visit(sub)
    visit(tree.body)
    for fn in functions(tree):
        declared = {n for g in ast.walk(fn) if isinstance(g, ast.Global) for n in g.names}
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in declared:
                out.setdefault(n.id, fn)
    return out


def has_name(path: Path, chain: list, root: Path, read: Reader, depth=0) -> tuple:
    """(found, where) -- whether `chain` (e.g. ["telemetry", "TELEMETRY_DIR"]) names something in module
    `path`, following imported modules and one class body."""
    name, rest = chain[0], chain[1:]
    if name.startswith("__") and name.endswith("__"):
        return True, "dunder"
    tree = ast.parse(read.text(path), str(path))
    node = top_bindings(tree).get(name)
    if node is None and path.name == "__init__.py" and module_file_in(path.parent, name, read):
        return True, "submodule"
    if node is None:
        return False, "%s has no module-level %s" % (path.relative_to(root), name)
    if not rest:
        return True, "found"
    if isinstance(node, (ast.Import, ast.ImportFrom)) and depth < 4:
        target = imported_module(node, name, root, read)
        if target is not None:
            return has_name(target, rest, root, read, depth + 1)
        return True, "%s is imported from outside the repository" % name
    if isinstance(node, ast.ClassDef):
        members = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        members |= {t.id for n in node.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
        if rest[0] in members or (rest[0].startswith("__") and rest[0].endswith("__")):
            return True, "class member"
        return False, "%s.%s has no member %s" % (path.relative_to(root), name, rest[0])
    return True, "found (not followed past %s)" % name


def module_file_in(folder: Path, name: str, read: Reader):
    for cand in (folder / (name + ".py"), folder / name / "__init__.py"):
        if read.exists(cand):
            return cand
    return None


def imported_module(node, name: str, root: Path, read: Reader):
    """The repository module an import statement binds to `name`, or None if it is not one."""
    for a in node.names:
        if (a.asname or a.name.split(".")[0]) != name:
            continue
        if isinstance(node, ast.Import):
            return module_file(a.name if a.asname else a.name.split(".")[0], root, read)
        if node.level == 0 and node.module:
            return module_file(node.module + "." + a.name, root, read)
    return None


class Resolver:
    """Resolves a name in ONE guard to what it is bound to, guard-wide (scope-insensitive on purpose: two
    different bindings of one name make it ambiguous, and an ambiguous site is never guessed)."""

    def __init__(self, tree: ast.Module, root: Path, read: Reader):
        self.tree, self.root, self.read = tree, root, read
        self.fns = {f.name: f for f in functions(tree)}
        self.module_assigns = assigns_in(tree.body)
        self.binds: dict = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    self.binds.setdefault(a.asname or a.name.split(".")[0], []).append(("import", node, a))
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self.binds.setdefault(t.id, []).append(("value", node.value))
                    else:
                        for n in ast.walk(t):
                            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                                self.binds.setdefault(n.id, []).append(("other",))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for i, arg in enumerate(node.args.args):
                    self.binds.setdefault(arg.arg, []).append(("param", node.name, i))
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension, ast.withitem, ast.NamedExpr,
                                   ast.AnnAssign, ast.AugAssign)):
                target = getattr(node, "target", None) or getattr(node, "optional_vars", None)
                for n in ast.walk(target) if target is not None else ():
                    if isinstance(n, ast.Name):
                        self.binds.setdefault(n.id, []).append(("other",))

    def name(self, name: str, seen=()) -> tuple:
        """("module", path) | ("member", path, attr) | ("external", what) | ("unresolved", why)."""
        binds = [(i, b) for i, b in enumerate(self.binds.get(name, [])) if (name, i) not in seen]
        got = {self.bind(b, name, seen + ((name, i),)) for i, b in binds}  # a binding already being followed
        if not got:                                                        # (a parameter fed itself) is skipped
            return ("unresolved", "%s is not bound in the guard" % name)
        if len(got) > 1:
            return ("unresolved", "%s has %d different bindings" % (name, len(got)))
        return got.pop()

    def bind(self, b, name: str, seen) -> tuple:
        if b[0] == "import":
            _, node, a = b
            target = imported_module(node, name, self.root, self.read)
            if target is not None:
                return ("module", target)
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                owner = module_file(node.module, self.root, self.read)
                if owner is not None:
                    return ("member", owner, a.name)
            return ("external", (a.name if isinstance(node, ast.Import) else "%s.%s" % (node.module, a.name)))
        if b[0] == "param":
            _, fname, i = b
            calls = [c for c in ast.walk(self.tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                     and c.func.id == fname]
            got = {self.expr(c.args[i], seen) if i < len(c.args) else ("unresolved", "keyword call") for c in calls}
            if len(got) != 1:
                return ("unresolved", "parameter %s of %s is filled %d ways" % (name, fname, len(got)))
            return got.pop()
        if b[0] == "value":
            return self.expr(b[1], seen)
        return ("unresolved", "%s is bound by an assignment the reader does not follow" % name)

    def expr(self, node, seen) -> tuple:
        if isinstance(node, ast.Name):
            return self.name(node.id, seen)
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if func.endswith("module_from_spec") and len(node.args) == 1 and isinstance(node.args[0], ast.Name):
                specs = [b for b in self.binds.get(node.args[0].id, []) if b[0] == "value"]
                paths = set()
                for _, value in specs:
                    if (isinstance(value, ast.Call) and ast.unparse(value.func).endswith("spec_from_file_location")
                            and len(value.args) >= 2):
                        try:
                            paths.add(evaluate(value.args[1], self.module_assigns, self.root))
                        except Unreadable:
                            paths.add(None)
                    else:
                        paths.add(None)
                if len(paths) == 1 and isinstance(next(iter(paths)), Path):
                    return ("module", next(iter(paths)))
                return ("unresolved", "importlib spec for %s does not resolve to one path" % node.args[0].id)
            if isinstance(node.func, ast.Name) and node.func.id in self.fns:
                returns = [r.value for r in ast.walk(self.fns[node.func.id]) if isinstance(r, ast.Return)
                           and r.value is not None]
                got = {self.expr(r, seen) for r in returns}
                if len(got) == 1:
                    return got.pop()
                return ("unresolved", "%s() returns %d different things" % (node.func.id, len(got)))
        return ("unresolved", "bound to %s" % ast.unparse(node)[:60])


def label_of(node, parents: dict) -> str:
    """The --mutate label a site runs under: the nearest `<...mutat...> == "label"` test, "(any label)" under a
    bare `if <...mutat...>`, else "(setup)"."""
    while node in parents:
        child, node = node, parents[node]
        if isinstance(node, ast.If) and child is not node.test:
            test = node.test
            if (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
                    and "mutat" in ast.unparse(test.left).lower() and isinstance(test.comparators[0], ast.Constant)):
                return str(test.comparators[0].value) if child in node.body else "(not %s)" % test.comparators[0].value
            if "mutat" in ast.unparse(test).lower() and child in node.body:
                return "(any label)"
    return "(setup)"


def rebind_sites(tree: ast.Module) -> list:
    """[(site text, base Name or None, attribute chain, node), ...]: every attribute the guard rebinds by name."""
    out = []

    def chain_of(attr):
        names = []
        while isinstance(attr, ast.Attribute):
            names.insert(0, attr.attr)
            attr = attr.value
        return (attr.id if isinstance(attr, ast.Name) else None), names

    replace_names = {"dataclasses.replace"} | {
        (a.asname or a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "dataclasses"
        for a in n.names if a.name == "replace"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            base, names = chain_of(node)
            out.append((ast.unparse(node), base, names, node))
        elif isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if (func in ("setattr", "delattr") and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)):
                base, names = chain_of(node.args[0])
                out.append(("%s(%s, %r)" % (func, ast.unparse(node.args[0]), node.args[1].value), base,
                            names + [node.args[1].value], node))
            elif (isinstance(node.func, ast.Attribute) and node.func.attr == "pop" and node.args
                  and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                owner = node.func.value  # X.__dict__ or X.__pydantic_decorators__.<kind>
                if isinstance(owner, ast.Attribute) and owner.attr == "__dict__":
                    base, names = chain_of(owner.value)
                elif (isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Attribute)
                      and owner.value.attr == "__pydantic_decorators__"):
                    base, names = chain_of(owner.value.value)
                else:
                    continue  # a dict or os.environ pop: data, not a rebind
                out.append(("%s.pop(%r)" % (ast.unparse(owner), node.args[0].value), base,
                            names + [node.args[0].value], node))
            elif func in replace_names and node.args:
                for kw in node.keywords:
                    if kw.arg:
                        out.append(("%s(%s, %s=...)" % (func, ast.unparse(node.args[0]), kw.arg), None, [kw.arg], node))
    return out


def examine_rebinds(guard: str, tree: ast.Module, root: Path, read: Reader) -> tuple:
    """(checked, missing, unresolved): sites found in their target, sites whose name is gone, and sites the
    reader cannot resolve, each as (site, label, detail)."""
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    res = Resolver(tree, root, read)
    checked, missing, unresolved = [], [], []
    for site, base, names, node in rebind_sites(tree):
        label = label_of(node, parents)
        kind = res.name(base) if base else ("unresolved", "the rebound object is not a name")
        if kind[0] == "module":
            if not names:
                unresolved.append((site, label, "no attribute"))
                continue
            found, where = has_name(kind[1], names, root, read)
        elif kind[0] == "member":
            found, where = has_name(kind[1], [kind[2]] + names, root, read)
        elif kind[0] == "external":
            unresolved.append((site, label, "%s is outside the repository" % kind[1]))
            continue
        else:
            unresolved.append((site, label, kind[1]))
            continue
        (checked if found else missing).append((site, label, where))
    return checked, missing, unresolved


# ---------------------------------------------------------------- the examination

def git_status() -> tuple:
    got = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                         capture_output=True, text=True)
    return got.returncode == 0, (got.stdout if got.returncode == 0 else got.stderr.strip())


def examine(guards_dir: Path = EVALS, root: Path = ROOT, redirect=None) -> tuple:
    """(checks, rows, rebinds). `redirect` maps a real file to the temporary copy to read in its place."""
    read = Reader(redirect)
    out, all_rows, all_rebinds = [], [], []
    present = sorted(p.name for p in guards_dir.glob("check_*.py"))
    groups = {"CHECKED": set(CHECKED), "EXEMPT": set(EXEMPT), "NO_MUTATIONS": set(NO_MUTATIONS)}
    problems = []
    for name in present:
        inside = [g for g, names in groups.items() if name in names]
        if len(inside) != 1:
            problems.append("%s is in %s" % (name, " and ".join(inside) if inside else "NO group"))
    listed = set().union(*groups.values())
    problems += ["%s is listed but does not exist" % n for n in sorted(listed - set(present))]
    out.append((not problems and len(present) > 0,
                "groups: every evals/check_*.py is in exactly one of CHECKED, EXEMPT, NO_MUTATIONS, and every "
                "listed name exists", "; ".join(problems) or "%d guards: %d checked, %d exempt, %d no mutations" % (
                    len(present), len(CHECKED), len(EXEMPT), len(NO_MUTATIONS))))

    for guard in sorted(CHECKED):
        path = guards_dir / guard
        if not path.exists():
            continue  # already a groups failure
        source = read.text(path)
        tree = ast.parse(source, str(path))
        specs = CHECKED[guard]
        unread = sorted(set(dict_tables(tree)) - {s[0] for s in specs})
        out.append((not unread, "%s: no dict named *MUTATIONS*, at any level, that this guard does not read" % guard,
                    ", ".join(unread) or "tables read: %s" % ", ".join(s[0] for s in specs)))
        if guard == "check_telemetry.py":
            out.append((LOCAL_IMPORT in source, "%s: its anchors' target is still the module it imports as `%s`"
                        % (guard, LOCAL_IMPORT), "present" if LOCAL_IMPORT in source else "the import is gone"))
        for spec in specs:
            name, rule = spec[0], spec[3]
            loads = loaders(tree, spec)
            bad = []
            for f in loads:
                lacking = [r for r in rule if r not in ast.get_source_segment(source, f)]
                if lacking:
                    bad.append("%s lacks %s" % (f.name, lacking))
            try:
                rows, error = table_rows(tree, spec, root), None
            except Unreadable as exc:
                rows, error = [], str(exc)
            out.append((error is None and loads and not bad and len(rows) > 0,
                        "%s: %s reads statically, yields at least one anchor, and EACH of its loaders applies it "
                        "exactly once" % (guard, name),
                        error or ("no loader found (a function indexing %s and calling .replace)" % name if not loads
                                  else "rule gone from a loader: %s -- re-read how it applies its mutations" % bad
                                  if bad else "%d anchor(s); loader(s) %s carry `%s`" % (
                                      len(rows), ", ".join(f.name for f in loads), rule[0]))))
            for label, target, old, row_error in rows:
                all_rows.append((guard, label, target, old))
                if row_error:
                    out.append((False, "%s --mutate %s: its anchor reads statically" % (guard, label), row_error))
                    continue
                shown = target.relative_to(root) if target.is_relative_to(root) else target
                if not read.exists(target):
                    out.append((False, "%s --mutate %s: anchor found exactly once in %s" % (guard, label, shown),
                                "the target file does not exist"))
                    continue
                n = read.text(target).count(old)
                out.append((n == 1, "%s --mutate %s: anchor found exactly once in %s" % (guard, label, shown),
                            "count 1" if n == 1 else "count %d: the mutation would refuse to run (MUTATION TARGET "
                            "MISSING) -- re-anchor it" % n))

    problems, uncovered_seen = [], set()
    for guard in sorted(set(EXEMPT) - {SELF}):
        path = guards_dir / guard
        if not path.exists():
            continue  # already a groups failure
        checked, missing, unresolved = examine_rebinds(guard, ast.parse(read.text(path), str(path)), root, read)
        all_rebinds += [(guard,) + c for c in checked]
        unlisted = []
        for site, label, why in unresolved:
            key = (guard, site, label)
            if key in KNOWN_UNCOVERED:
                uncovered_seen.add(key)
            else:
                unlisted.append("%s [%s]: %s" % (site, label, why))
        if checked or missing or unresolved:
            out.append((not missing and not unlisted,
                        "%s: every attribute it rebinds by name still exists in its target" % guard,
                        "; ".join(["GONE %s [%s]: %s" % m for m in missing] + ["UNRESOLVED, not in KNOWN_UNCOVERED "
                                                                               + u for u in unlisted])
                        or "%d site(s) found in their targets%s" % (len(checked), ", %d known-uncovered" % (
                            len(unresolved)) if unresolved else "")))
    stale = sorted(set(KNOWN_UNCOVERED) - uncovered_seen)
    out.append((not stale and len(KNOWN_UNCOVERED) == KNOWN_UNCOVERED_SIZE,
                "KNOWN_UNCOVERED holds exactly %d entries, each still matching an unresolvable site"
                % KNOWN_UNCOVERED_SIZE, "; ".join("%s %s [%s] no longer matches a site" % k for k in stale)
                or "%d entries" % len(KNOWN_UNCOVERED)))

    problems = []
    for guard in sorted((set(EXEMPT) | set(NO_MUTATIONS)) - {SELF}):
        path = guards_dir / guard
        if not path.exists():
            continue  # already a groups failure
        source = read.text(path)
        problems += ["%s carries %r" % (guard, m) for m in MARKERS if m in source]
        problems += ["%s has a dict table %s" % (guard, t) for t in dict_tables(ast.parse(source, str(path)))]
        if guard in NO_MUTATIONS and "--mutate" in source:
            problems.append("%s is listed NO_MUTATIONS but has --mutate" % guard)
    out.append((not problems, "exempt and no-mutation guards carry no text-mutation marker or dict table; "
                "no-mutation guards have no --mutate", "; ".join(problems) or "%d guards read" % (
                    len(EXEMPT) - 1 + len(NO_MUTATIONS))))

    contributing = sorted({g for g, *_ in all_rows})
    out.append((len(all_rows) >= MIN_ANCHORS and contributing == sorted(CHECKED),
                "not vacuous: at least %d anchors examined, from every CHECKED guard" % MIN_ANCHORS,
                "%d anchors across %d guards (of %d checked)" % (len(all_rows), len(contributing), len(CHECKED))))
    out.append((len(all_rebinds) >= MIN_REBINDS,
                "not vacuous: at least %d rebind sites resolved and found in their targets" % MIN_REBINDS,
                "%d rebind sites across %d exempt guards; %d known-uncovered" % (
                    len(all_rebinds), len({r[0] for r in all_rebinds}), len(KNOWN_UNCOVERED))))
    return out, all_rows, all_rebinds


def find_row(guard: str, label: str) -> tuple:
    _, rows, _ = examine()
    hits = [(t, o) for g, lab, t, o in rows if (g, lab) == (guard, label) and t is not None]
    if len(hits) != 1:
        raise SystemExit("MUTATION TARGET MISSING: %s --mutate %s is not one readable anchor" % (guard, label))
    target, old = hits[0]
    if target.read_text(encoding="utf-8").count(old) != 1:
        raise SystemExit("MUTATION TARGET MISSING: %s's %s anchor is not in %s exactly once" % (guard, label, target))
    return target, old


def checks(mutation, tmp: Path) -> list:
    ok_before, before = git_status()
    if mutation in ("duplicate-anchor", "missing-anchor"):
        target, old = find_row(*(DUPLICATE if mutation == "duplicate-anchor" else MISSING))
        text = target.read_text(encoding="utf-8")
        copy = tmp / target.name
        copy.write_text(text + old if mutation == "duplicate-anchor" else text.replace(old, ""), encoding="utf-8")
        out, _, _ = examine(redirect={target: copy})
    elif mutation in ("unlisted-guard", "label-added-in-function"):
        guards = tmp / "evals"
        guards.mkdir()
        for p in EVALS.glob("check_*.py"):
            shutil.copy2(p, guards / p.name)
        if mutation == "unlisted-guard":
            (guards / UNLISTED).write_text('"""A new guard nobody listed."""\n', encoding="utf-8")
        else:
            guard, old, new = IN_FUNCTION
            text = (guards / guard).read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, guard))
            (guards / guard).write_text(text.replace(old, new), encoding="utf-8")
        out, _, _ = examine(guards_dir=guards)
    elif mutation == "renamed-rebind-target":
        rel, old, new = RENAMED
        target = ROOT / rel
        text = target.read_text(encoding="utf-8")
        pattern = r"\b%s\b" % re.escape(old)
        if not re.search(pattern, text):
            raise SystemExit("MUTATION TARGET MISSING: %s is not in %s" % (old, rel))
        copy = tmp / target.name
        copy.write_text(re.sub(pattern, new, text), encoding="utf-8")
        out, _, _ = examine(redirect={target: copy})
    else:
        out, _, _ = examine()
    ok_after, after = git_status()
    out.append((ok_before and ok_after and before == after,
                "the repository's git status ran and is unchanged (this guard writes only temporary copies)",
                ("unchanged" if before == after else "before %r, after %r" % (before[:200], after[:200]))
                if ok_before and ok_after else "git status failed: %s" % (before if not ok_before else after)[:200]))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin every mutation's anchor and rebind target")
    ap.add_argument("--mutate", choices=MUTATIONS, help="plant one defect in a temporary copy; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    with tempfile.TemporaryDirectory(prefix="fc08_mutation_anchors_") as tmp:
        for ok, label, detail in checks(args.mutate, Path(tmp)):
            print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:300]))
            failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the defect planted"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
