"""
Pin every text mutation's anchor: a guard's `--mutate` that rewrites an exact source snippet must still find
that snippet in its target exactly as the guard itself requires, so no `--mutate` can go silently dead.

Usage:
    python evals/check_mutation_anchors.py
    python evals/check_mutation_anchors.py --mutate duplicate-anchor  # a real anchor appears twice in a temp copy
    python evals/check_mutation_anchors.py --mutate missing-anchor    # a real anchor is absent from a temp copy
    python evals/check_mutation_anchors.py --mutate unlisted-guard    # a new evals/check_*.py is in no group

WHY. Most guards' --mutate labels are TEXT mutations: they replace an exact snippet of a source file and
refuse to run ("MUTATION TARGET MISSING") when the snippet is not there exactly once. tools/check_all.py runs
every guard plain and never runs a mutation, so a label whose anchor stopped matching is dead and nothing goes
red. It happened: commit 03d21b1 gave tools/friday_run.py a second copy of the line `check_friday_run --mutate
telemetry-elsewhere` was anchored on, and that label could not run from 03d21b1 until it was found and
re-anchored on 2026-09-30 (b0bbfda's review then ran all 103 labels of five guards and found none dead).

WHAT IT HOLDS:
  groups    every evals/check_*.py is in exactly one of three lists -- CHECKED (it has text-mutation tables),
            EXEMPT (it has --mutate labels, applied in code; each with its one-line reason) or NO_MUTATIONS --
            and every name listed exists. A NEW guard in none of them is a failure, so it cannot escape;
  tables    for each CHECKED guard, every table named for it reads statically (ast, never an import: importing
            a guard pulls in the modules it tests), is a literal dict, is not modified after it is defined, and
            yields at least one anchor; and the guard has no OTHER dict named *MUTATIONS* this guard does not
            read (a new table cannot slip past the spec);
  rule      each CHECKED guard still applies its anchors by the rule checked here: its source still carries
            its own predicate (`source.count(old) != 1`, `src.count(anchor) == 1`, ...). Every one of the 13
            requires EXACTLY ONCE -- read from each guard's loader, not assumed -- so if one changes its rule,
            this goes red and asks for the spec to be re-read rather than checking the wrong thing;
  anchors   for every (target, old) of every table, the target file exists and `old` occurs in it exactly once;
  exempt    an EXEMPT or NO_MUTATIONS guard carries no text-mutation marker ("MUTATION TARGET MISSING",
            ".count(old)", ...) and no dict named *MUTATIONS*; a NO_MUTATIONS guard has no "--mutate";
  writes    the repository's `git status` is unchanged by the run: the guard reads sources and, under
            --mutate, writes only temporary copies.

STATIC. It never runs a mutation and never imports a guard. That is also its limit: it proves each anchor is
still THERE exactly once, not that applying it still breaks what its label says (only running the label shows
that), and it reads no anchor that is applied in code -- EXEMPT says which those are and why.

NOT A VACUOUS PASS. At least MIN_ANCHORS anchors are examined (pinned to the count measured 2026-10-01, and
printed), and every CHECKED table must contribute one. Each --mutate plants its defect in a TEMPORARY copy
(the target file, or the guards folder) and points the same examination at it; at least one check must fail.
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
SELF = Path(__file__).name
ROOT_EXPR = "Path(__file__).resolve().parent.parent"  # every guard's ROOT, measured: 32 of 32

# Table shapes: which tuple element is the target and which is the anchor (`new` is never read).
PATH_OLD = "path-old-new"  # (Path expression, old, new)
OLD_ONLY = "old-new"       # (old, new); the target is the one module-level path named in the spec
KEY_OLD = "key-old-new"    # (key into a module-level dict of paths, old, new)
LOCAL = "local-anchor"     # `anchor = "..."` inside the named function; the target is named in the spec

ONCE = "source.count(old) != 1"
# guard -> ((table, shape, target, rule snippets that must all be in the guard's source), ...)
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
    # agents/telemetry.py (the guard's own `from agents import telemetry`).
    "check_telemetry.py": (("_recompile_unhooked", LOCAL, "agents/telemetry.py",
                            ("src.count(anchor) == 1", "from agents import telemetry",
                             "Path(telemetry.__file__).read_text")),
                           ("_recompile_run_started", LOCAL, "agents/telemetry.py",
                            ("src.count(anchor) == 1", "from agents import telemetry",
                             "Path(telemetry.__file__).read_text"))),
}
LOCAL_LABELS = {"_recompile_unhooked": "unhooked-success|unhooked-none", "_recompile_run_started": "drop-prompt-sha"}

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

MIN_ANCHORS = 178  # measured 2026-10-01 at 075744b: 178 anchors across 13 guards. A floor, not a pin.

MUTATIONS = ("duplicate-anchor", "missing-anchor", "unlisted-guard")
# The incident shape: the anchor 03d21b1 duplicated, now re-anchored on the comment above it.
DUPLICATE = ("check_friday_run.py", "telemetry-elsewhere")
MISSING = ("check_accept_run.py", "whole-run-refusal")  # a multi-line anchor
UNLISTED = "check_zz_unlisted_probe.py"


class Unreadable(Exception):
    """A table, or one of its entries, that this guard cannot read statically: a failure, never a skip."""


def module_assigns(tree: ast.Module) -> dict:
    """name -> [value node, ...] for every module-level `name = ...`, in order."""
    out: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            out.setdefault(node.targets[0].id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            out.setdefault(node.target.id, []).append(node.value)
    return out


def evaluate(node, assigns: dict, root: Path, seen=()):
    """The literal value of `node`: constants, dicts, Path / "x", "a" + "b", and module-level names whose own
    values are those. ROOT is the repository root, and only if the guard defines it the way all 32 do."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        values = assigns.get(node.id, [])
        if node.id == "ROOT":
            if len(values) != 1 or ast.unparse(values[0]) != ROOT_EXPR:
                raise Unreadable("ROOT is not defined once as %s" % ROOT_EXPR)
            return root
        if node.id in seen or len(values) != 1:
            raise Unreadable("%s is not one module-level assignment" % node.id)
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


def modified_after(tree: ast.Module, name: str) -> list:
    """Module-level statements that change `name` after it is defined: NAME[...] = ..., NAME += ...,
    NAME.update(...) and the like. Their labels would be invisible to a reader of the literal."""
    out = []
    for node in tree.body:
        for sub in ast.walk(node):
            hit = ((isinstance(sub, ast.Subscript) and isinstance(sub.ctx, (ast.Store, ast.Del))
                    and isinstance(sub.value, ast.Name) and sub.value.id == name)
                   or (isinstance(sub, ast.AugAssign) and isinstance(sub.target, ast.Name) and sub.target.id == name)
                   or (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                       and isinstance(sub.func.value, ast.Name) and sub.func.value.id == name
                       and sub.func.attr in ("update", "setdefault", "pop", "popitem", "clear", "__setitem__")))
            if hit and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append("line %d" % sub.lineno)
    return out


def dict_tables(tree: ast.Module) -> list:
    """Every module-level name containing MUTATIONS whose value is a dict -- the shape of a text table."""
    return sorted(n for n, vs in module_assigns(tree).items() if "MUTATIONS" in n and any(
        isinstance(v, ast.Dict) for v in vs))


def table_rows(guard: str, tree: ast.Module, spec, root: Path) -> list:
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
    assigns = module_assigns(tree)
    values = assigns.get(name, [])
    if len(values) != 1 or not isinstance(values[0], ast.Dict):
        raise Unreadable("%s is not one module-level dict literal" % name)
    changed = modified_after(tree, name)
    if changed:
        raise Unreadable("%s is modified after its definition (%s)" % (name, ", ".join(changed)))
    fixed = evaluate(ast.Name(target), assigns, root) if shape in (OLD_ONLY, KEY_OLD) else None
    rows = []
    for k, v in zip(values[0].keys, values[0].values):
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


def git_status() -> str:
    got = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                         capture_output=True, text=True)
    return got.stdout if got.returncode == 0 else "git status failed: %s" % got.stderr.strip()


def examine(guards_dir: Path = EVALS, root: Path = ROOT, redirect=None) -> tuple:
    """(checks, rows). `redirect` maps a real target path to the temporary copy to read in its place."""
    redirect = redirect or {}
    out, all_rows = [], []
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
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, str(path))
        specs = CHECKED[guard]
        unread = sorted(set(dict_tables(tree)) - {s[0] for s in specs})
        out.append((not unread, "%s: no dict named *MUTATIONS* that this guard does not read" % guard,
                    ", ".join(unread) or "tables read: %s" % ", ".join(s[0] for s in specs)))
        for spec in specs:
            name, shape, _target, rule = spec
            missing_rule = [r for r in rule if r not in source]
            try:
                rows, error = table_rows(guard, tree, spec, root), None
            except Unreadable as exc:
                rows, error = [], str(exc)
            out.append((error is None and not missing_rule and len(rows) > 0,
                        "%s: %s reads statically, yields at least one anchor, and the guard still applies it by "
                        "its own rule (exactly once)" % (guard, name),
                        error or ("rule gone from the guard's source: %s -- re-read how it applies its mutations"
                                  % missing_rule if missing_rule else "%d anchor(s), rule `%s`" % (len(rows), rule[0]))))
            for label, target, old, row_error in rows:
                all_rows.append((guard, label, target, old))
                if row_error:
                    out.append((False, "%s --mutate %s: its anchor reads statically" % (guard, label), row_error))
                    continue
                shown = target.relative_to(root) if target.is_relative_to(root) else target
                read_from = redirect.get(target, target)
                if not read_from.exists():
                    out.append((False, "%s --mutate %s: anchor found exactly once in %s" % (guard, label, shown),
                                "the target file does not exist"))
                    continue
                n = read_from.read_text(encoding="utf-8").count(old)
                out.append((n == 1, "%s --mutate %s: anchor found exactly once in %s" % (guard, label, shown),
                            "count 1" if n == 1 else "count %d: the mutation would refuse to run (MUTATION TARGET "
                            "MISSING) -- re-anchor it" % n))

    problems = []
    for guard in sorted((set(EXEMPT) | set(NO_MUTATIONS)) - {SELF}):
        path = guards_dir / guard
        if not path.exists():
            continue  # already a groups failure
        source = path.read_text(encoding="utf-8")
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
    return out, all_rows


def find_row(guard: str, label: str) -> tuple:
    _, rows = examine()
    hits = [(t, o) for g, lab, t, o in rows if (g, lab) == (guard, label) and t is not None]
    if len(hits) != 1:
        raise SystemExit("MUTATION TARGET MISSING: %s --mutate %s is not one readable anchor" % (guard, label))
    target, old = hits[0]
    if target.read_text(encoding="utf-8").count(old) != 1:
        raise SystemExit("MUTATION TARGET MISSING: %s's %s anchor is not in %s exactly once" % (guard, label, target))
    return target, old


def checks(mutation, tmp: Path) -> list:
    before = git_status()
    if mutation in ("duplicate-anchor", "missing-anchor"):
        target, old = find_row(*(DUPLICATE if mutation == "duplicate-anchor" else MISSING))
        text = target.read_text(encoding="utf-8")
        copy = tmp / target.name
        copy.write_text(text + old if mutation == "duplicate-anchor" else text.replace(old, ""), encoding="utf-8")
        out, _ = examine(redirect={target: copy})
    elif mutation == "unlisted-guard":
        guards = tmp / "evals"
        guards.mkdir()
        for p in EVALS.glob("check_*.py"):
            shutil.copy2(p, guards / p.name)
        (guards / UNLISTED).write_text('"""A new guard nobody listed."""\n', encoding="utf-8")
        out, _ = examine(guards_dir=guards)
    else:
        out, _ = examine()
    after = git_status()
    out.append((before == after, "the repository's git status is unchanged (this guard writes only temporary "
                "copies)", "unchanged" if before == after else "before %r, after %r" % (before[:200], after[:200])))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin every text mutation's anchor")
    ap.add_argument("--mutate", choices=MUTATIONS, help="plant one defect in a temporary copy; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    with tempfile.TemporaryDirectory(prefix="fc08_mutation_anchors_") as tmp:
        for ok, label, detail in checks(args.mutate, Path(tmp)):
            print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:200]))
            failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the defect planted"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
