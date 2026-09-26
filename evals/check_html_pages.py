"""
Pin the HTML pagination rule (schemas/html_pages.py) that PageIndex.from_html cites against.

Usage:
    python evals/check_html_pages.py
    python evals/check_html_pages.py --mutate keep-nav        # <nav> kept; navigation text MUST reach a page
    python evals/check_html_pages.py --mutate split-long      # long paragraphs cut; a paragraph MUST be split
    python evals/check_html_pages.py --mutate body-first      # <body> preferred to <main>; the pins MUST move
    python evals/check_html_pages.py --mutate page-size       # PAGE_CHARS 3000 -> 2500; the pins MUST move
    python evals/check_html_pages.py --mutate lenient-decode  # bad UTF-8 replaced, not refused
    python evals/check_html_pages.py --mutate no-entities     # entities not decoded; "&amp;" MUST go missing

WHY. A citation into an HTML document is (page, verbatim quote), and the page number comes from
this rule. Change the rule and every cited HTML page number moves, silently, so the rule is pinned
twice: by its behaviour (dropped chrome, whole paragraphs, the <main>/<article>/<body> fallback,
strict UTF-8, decoded entities) and by the digest of the pages it gives two documents -- a real
OFSI publication page (tests/fixtures/html/, public GOV.UK content under the Open Government
Licence) and a synthetic advisory built below. Moving a pin is a deliberate act: it re-pages every
committed HTML citation.

DETERMINISM. The same bytes must give the same pages on every run: the guard computes the digest
in four subprocesses under different PYTHONHASHSEED values. (fc-10 measured that two seeds can
agree by luck on non-deterministic code.)

COLD. A committed fixture and synthetic strings; no network.

NOT A VACUOUS PASS. Each --mutate rewrites the rule's SOURCE in memory and loads it as a separate
module; at least one check must then fail. A mutation whose target text is missing is a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schemas import citation_match as cm  # noqa: E402

RULE = ROOT / "schemas" / "html_pages.py"
FIXTURE = ROOT / "tests" / "fixtures" / "html" / "ofsi_uk_financial_sanctions_faqs.html"
FIXTURE_SHA256 = "1d3987e30a44c4387c5fe72382290f33d302f871177bc28e34afa4050da8a664"
FIXTURE_PAGES = 2
FIXTURE_DIGEST = "77ac9c09aa2ad2e223bc57e77545a34b58b229cb0566080b26c16d67c6f85ef6"
SYNTH_PAGES = 3
SYNTH_DIGEST = "01cf07ca19add9908db77fb5187057c83889b8d4842f1abaad2d9aa982c77c6b"
DROPPED = ("SCRIPT-TEXT", "HEADER-TEXT", "NAV-TEXT", "ASIDE-TEXT", "FOOTER-TEXT")
SEEDS = ("0", "1", "42", "4242")


def synthetic(main_tag: str = "main") -> bytes:
    return ("<!DOCTYPE html><html><head><title>T</title><style>p{color:red}</style>"
            "<script>var x='SCRIPT-TEXT';</script></head><body>"
            "<header>HEADER-TEXT</header><nav><a href='/'>NAV-TEXT</a></nav>"
            "<%s><h1>Synthetic advisory</h1>" % main_tag
            + "".join("<p>Paragraph %02d says funds moved through shell companies &amp; front firms in sentence "
                      "%02d of this synthetic advisory.</p>" % (i, i) for i in range(1, 41))
            + "<p>" + "Long " * 700 + "end.</p>"
            + "<aside>ASIDE-TEXT</aside></%s><footer>FOOTER-TEXT</footer></body></html>" % main_tag).encode("utf-8")


MUTATIONS = {
    "keep-nav": ('"svg", "nav", ', '"svg", '),
    "split-long": ("    for para in paras:\n",
                   "    for para in [p[i:i + PAGE_CHARS] for p in paras for i in range(0, len(p), PAGE_CHARS)]:\n"),
    "body-first": ('SCOPES = ("main", "article", "body")', 'SCOPES = ("body", "article", "main")'),
    "page-size": ("PAGE_CHARS = 3000", "PAGE_CHARS = 2500"),
    "lenient-decode": ('text = raw.decode("utf-8")', 'text = raw.decode("utf-8", "replace")'),
    "no-entities": ("super().__init__(convert_charrefs=True)", "super().__init__(convert_charrefs=False)"),
}


def load_rule(mutation):
    source = RULE.read_text(encoding="utf-8")
    if mutation:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, RULE))
        source = source.replace(old, new)
    spec = importlib.util.spec_from_loader("html_pages_under_test", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(RULE), "exec"), module.__dict__)
    return module


def seeded_digests(path: Path) -> set:
    code = ("import sys; sys.path.insert(0, %r); from schemas.html_pages import html_pages, pages_digest; "
            "print(pages_digest(html_pages(open(%r, 'rb').read())))" % (str(ROOT), str(path)))
    out = set()
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        out.add(r.stdout.strip() if r.returncode == 0 else "ERROR: " + r.stderr.strip()[-200:])
    return out


def checks(hp) -> list:
    out = []
    raw = FIXTURE.read_bytes()
    out.append((hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "the OFSI fixture is the pinned bytes",
                "sha256 %s" % hashlib.sha256(raw).hexdigest()))

    pages = hp.html_pages(raw)
    out.append((len(pages) == FIXTURE_PAGES and hp.pages_digest(pages) == FIXTURE_DIGEST,
                "the OFSI page gives the pinned pages (moving this pin re-pages every HTML citation)",
                "%d pages, digest %s" % (len(pages), hp.pages_digest(pages))))
    index = cm.PageIndex(pages)
    q2 = "FAQs 49-51, 55, 61-66, 72-73, 76 and 84 amended to reflect new Legal Services General Licence"
    got2, got1 = index.locate(2, q2), index.locate(1, q2)
    out.append((got2.status == cm.EXACT and got1.status == cm.OFF_PAGE and got1.found_on == (2,),
                "a quote on page 2 is EXACT there, and OFF_PAGE (found on 2) when cited on page 1",
                "page 2: %s; page 1: %s %s" % (got2.status, got1.status, got1.found_on)))
    q1 = "provided by the Foreign, Commonwealth & Development Office (FCDO)"
    out.append((index.locate(1, q1).status == cm.EXACT, "a quote with a decoded & is EXACT on page 1",
                index.locate(1, q1).status))

    synth = synthetic()
    spages = hp.html_pages(synth)
    joined = "\n".join(spages)
    leaked = [t for t in DROPPED if t in joined]
    out.append((not leaked, "script, header, nav, aside and footer text never reaches a page", "leaked: %s" % leaked))
    out.append(("shell companies & front firms" in joined, "entities are decoded (&amp; is &)", ""))
    paras = hp.paragraphs(synth)
    split = [p[:40] for p in paras if sum(1 for pg in spages if p in pg.split("\n\n")) != 1]
    out.append((bool(paras) and not split, "every paragraph is whole on exactly one page",
                "%d paragraphs; not whole on one page: %s" % (len(paras), split)))
    over = [n + 1 for n, pg in enumerate(spages) if len(pg) > 3000 and "\n\n" in pg]
    long_alone = any(pg.startswith("Long Long") and "\n\n" not in pg for pg in spages)
    out.append((not over and long_alone, "a page passes 3000 characters only when it is one paragraph, and the "
                "3504-character paragraph stands alone", "multi-paragraph pages over 3000: %s" % over))
    out.append((len(spages) == SYNTH_PAGES and hp.pages_digest(spages) == SYNTH_DIGEST,
                "the synthetic advisory gives the pinned pages",
                "%d pages %s, digest %s" % (len(spages), [len(p) for p in spages], hp.pages_digest(spages))))

    out.append((hp.paragraphs(synthetic("div")) == paras,
                "with no <main>, <body> is used, and the same chrome is dropped", ""))
    art = b"<html><body><div>OUTSIDE-TEXT</div><article><p>Inside the article.</p></article></body></html>"
    out.append((hp.paragraphs(art) == ["Inside the article."], "with no <main>, <article> is preferred to <body>",
                repr(hp.paragraphs(art))))
    try:
        hp.paragraphs(b"<main><p>caf\xe9</p></main>")
        refused = False
    except ValueError:
        refused = True
    out.append((refused, "a page that is not UTF-8 is refused, not repaired", ""))

    real = cm.PageIndex.from_html(raw).pages
    out.append((real == cm.PageIndex(pages).pages, "PageIndex.from_html is PageIndex over these pages", ""))

    with tempfile.TemporaryDirectory() as tmp:
        sp = Path(tmp) / "synthetic.html"
        sp.write_bytes(synth)
        for label, path, pin in (("OFSI", FIXTURE, FIXTURE_DIGEST), ("synthetic", sp, SYNTH_DIGEST)):
            got = seeded_digests(path)
            out.append((got == {pin}, "the %s digest is the same under %d hash seeds" % (label, len(SEEDS)),
                        "digests: %s" % sorted(got)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the HTML pagination rule")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    hp = load_rule(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(hp):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
