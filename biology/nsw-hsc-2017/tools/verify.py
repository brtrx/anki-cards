#!/usr/bin/env python3
"""Check every card. Writes VERIFICATION.md and exits non-zero on errors.

    python biology/nsw-hsc-2017/tools/verify.py            # all checks
    python biology/nsw-hsc-2017/tools/verify.py --no-spell # skip spelling
    python biology/nsw-hsc-2017/tools/verify.py --strict   # warnings also fail

Checks
  1. lint         structure: known fields and tags, unique ids, question or cloze
                  (well-formed, numbered from c1), every cited dot point exists and
                  the first one belongs to the card's own deck, answers short
                  enough to be one idea, balanced markdown, Unicode chemistry.
  2. coverage     every dot point of the syllabus (syllabus.yaml), every Working
                  Scientifically skill and every NESA key word has at least one
                  card. Uncovered "including" dot points are errors; uncovered
                  "for example" dot points are warnings.
  3. definitions  cards that give a syllabus-glossary or NESA key-word definition
                  must match the official wording exactly.
  4. calculations worked problems (crosses, transcription, translation, SA:V,
                  magnification, population estimates, rates, half-lives) are recomputed
                  independently by biocalc.py and compared with the card.
  5. spelling     every word is checked against an English dictionary, accepting
                  Australian spellings of dictionary words, plus an allowlist of
                  biology terms; US spellings (color, hemoglobin, -ize…) are errors.
  6. duplicates   identical questions are errors; near-identical ones warnings.
  7. manual list  what a machine can't judge (facts with numbers or dates,
                  history of science, Aboriginal and Torres Strait Islander
                  content, cards the author flagged) is listed for a human reviewer.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biocalc  # noqa: E402
from deckdata import CLOZE_RE, ROOT, Card, Deck, Syllabus, dp_label, load_decks, load_syllabus, plain  # noqa: E402

TOOLS = Path(__file__).resolve().parent
FIELDS = {"id", "q", "a", "cloze", "x", "tip", "hint", "source", "dp", "tags", "calc", "glossary", "keyword", "review"}
TAGS = {"aus": "Australian example", "history": "history of science", "indigenous":
        "Aboriginal and Torres Strait Islander knowledge", "ethics": "ethical / social issue",
        "data": "interpreting data", "practical": "practical investigation", "compare": "comparison"}
MAX_ANSWER_WORDS = 45
MAX_CLOZE_WORDS = 80
MAX_CLOZES = 6
ASCII_CHEM = re.compile(r"\b(CO2|O2|H2O|H2O2|C6H12O6|N2|CH4|NH3|NO3|PO4|Na\+|K\+|Ca2\+|Cl-)(?![\w₀-₉])")

# US spelling → Australian spelling. Words ending in -ize/-ization are caught by a rule.
US_SPELLINGS = {
    "color": "colour", "behavior": "behaviour", "favor": "favour", "favorable": "favourable",
    "flavor": "flavour", "humor": "humour", "labor": "labour", "neighbor": "neighbour", "odor": "odour",
    "tumor": "tumour", "vapor": "vapour", "vigor": "vigour", "harbor": "harbour", "honor": "honour",
    "center": "centre", "fiber": "fibre", "liter": "litre", "milliliter": "millilitre", "theater": "theatre",
    "hemoglobin": "haemoglobin", "anemia": "anaemia", "leukemia": "leukaemia", "hemophilia": "haemophilia",
    "hemorrhage": "haemorrhage", "hemodialysis": "haemodialysis", "hematology": "haematology",
    "feces": "faeces", "fecal": "faecal", "paleontology": "palaeontology", "paleontological": "palaeontological",
    "esophagus": "oesophagus", "estrogen": "oestrogen", "edema": "oedema", "diarrhea": "diarrhoea",
    "estrus": "oestrus", "anesthetic": "anaesthetic", "pediatric": "paediatric", "orthopedic": "orthopaedic",
    "analyze": "analyse", "paralyze": "paralyse", "catalyze": "catalyse", "hydrolyze": "hydrolyse",
    "dialyze": "dialyse", "defense": "defence", "offense": "offence", "gray": "grey", "mold": "mould",
    "molds": "moulds", "aluminum": "aluminium", "modeling": "modelling", "modeled": "modelled",
    "labeled": "labelled", "labeling": "labelling", "traveled": "travelled", "canceled": "cancelled",
    "fueled": "fuelled", "catalog": "catalogue", "plow": "plough", "sulphur": "sulfur",
    "cesarean": "caesarean", "skeptical": "sceptical", "artifact": "artefact", "enrollment": "enrolment",
}
IZE_RE = re.compile(r"^[a-z]{3,}iz(e|es|ed|ing|er|ers|ation|ations|able)$")
IZE_EXCEPTIONS = {"size", "sizes", "sized", "seize", "seized", "seizes", "prize", "prizes", "capsize",
                  "maize", "baize", "downsize", "oversize", "oversized", "undersized", "assize"}
# Australian → US transformations: an unknown word is accepted if one of these
# turns it into a dictionary word (colour → color, haemoglobin → hemoglobin …).
AU_TO_US = [
    (r"isation", "ization"), (r"is(e|es|ed|ing|er|ers)$", r"iz\1"), (r"ys(e|ed|es|ing)$", r"yz\1"),
    (r"our", "or"), (r"([bt])re(s|d)?$", r"\1er\2"), (r"ae", "e"), (r"oea", "ea"), (r"oe", "e"),
    (r"ll(ed|ing|er|ers)$", r"l\1"), (r"ence$", "ense"), (r"oul(d|t)", r"ol\1"), (r"ogue(s)?$", r"og\1"), (r"mme(s)?$", r"m\1"),
]
STOP = set("a an the of to in and or is are be by for with on at as from that this it its which what how "
           "why does do when who into than their there these those one two".split())


class Report:
    def __init__(self):
        self.errors: list[tuple[str, str, str]] = []
        self.warnings: list[tuple[str, str, str]] = []
        self.manual: dict[str, list[str]] = defaultdict(list)
        self.coverage: dict[str, list[str]] = {}

    def e(self, c, kind, msg): self.errors.append((c, kind, msg))
    def w(self, c, kind, msg): self.warnings.append((c, kind, msg))


# --------------------------------------------------------------------------- 1. lint

def lint(decks: list[Deck], syl: Syllabus, rep: Report) -> None:
    codes = Counter(d.code for d in decks)
    for code, n in codes.items():
        if n > 1:
            rep.e(code, "lint", f"deck {code} defined in {n} files")
    for d in decks:
        ids = Counter(c.id for c in d.cards)
        for i, n in ids.items():
            if n > 1:
                rep.e(f"{d.code}-{i:03d}", "lint", f"id used {n} times in {d.path.name}")
        if not d.cards:
            rep.w(d.code, "lint", f"{d.path.name} has no cards")
        for c in d.cards:
            lint_card(c, syl, rep)


def lint_card(c: Card, syl: Syllabus, rep: Report) -> None:
    u = c.uid
    unknown = set(c.raw) - FIELDS
    if unknown:
        rep.e(u, "lint", f"unknown field(s) {sorted(unknown)}")
    if c.id <= 0:
        rep.e(u, "lint", "id must be a positive integer")
    if bool(c.q) == bool(c.cloze):
        rep.e(u, "lint", "a card needs either q (with a) or cloze, not both")
        return
    if c.q:
        if not c.a.strip():
            rep.e(u, "lint", "question card without an answer (a)")
        if not c.q.rstrip().endswith(("?", ".")) and not (c.keyword or c.glossary):
            rep.w(u, "lint", "question (or instruction) doesn't end with '?' or '.'")
        n = len(plain(c.a).split())
        if n > MAX_ANSWER_WORDS and not (c.glossary or c.keyword):
            rep.w(u, "lint", f"answer is {n} words (>{MAX_ANSWER_WORDS}): split the card or move detail to x")
        if CLOZE_RE.search(c.q + c.a):
            rep.e(u, "lint", "cloze markup in a question card")
    else:
        if c.a:
            rep.e(u, "lint", "cloze card must not have an answer (a); use x for extra information")
        nums = [int(m.group(1)) for m in CLOZE_RE.finditer(c.cloze)]
        if not nums:
            rep.e(u, "lint", "cloze text has no {{c1::…}} deletion")
        else:
            distinct = sorted(set(nums))
            if distinct != list(range(1, len(distinct) + 1)):
                rep.e(u, "lint", f"cloze numbers must run c1, c2, … without gaps (found {distinct})")
            if len(distinct) > MAX_CLOZES:
                rep.w(u, "lint", f"{len(distinct)} cloze deletions (>{MAX_CLOZES}): split the note")
        if re.search(r"\{\{(?!c\d+::)", c.cloze) or c.cloze.count("{{") != c.cloze.count("}}"):
            rep.e(u, "lint", "malformed cloze markup")
        n = len(plain(c.cloze).split())
        if n > MAX_CLOZE_WORDS:
            rep.w(u, "lint", f"cloze text is {n} words (>{MAX_CLOZE_WORDS})")
    for name, text in c.texts().items():
        if "***" in text:
            rep.e(u, "lint", f"*** in {name}: nest bold and italic explicitly (**bold** *italic*)")
        elif text.count("**") % 2:
            rep.e(u, "lint", f"unbalanced ** in {name}")
        m = ASCII_CHEM.search(text)
        if m:
            rep.w(u, "lint", f"write {m.group(1)!r} with Unicode sub/superscripts in {name}")
    for t in c.tags:
        if t not in TAGS:
            rep.e(u, "lint", f"unknown tag {t!r} (known: {', '.join(sorted(TAGS))})")
    # syllabus references
    dps = c.dp or (["KW." + c.keyword] if c.keyword else [])
    if not dps:
        rep.e(u, "lint", "no syllabus dot point (dp) cited")
    for i, pid in enumerate(dps):
        p = syl.points.get(pid)
        if p is None:
            rep.e(u, "lint", f"unknown dot point {pid!r}")
            continue
        if not p.leaf:
            rep.e(u, "lint", f"dot point {pid} has sub-points: cite one of them ({pid}a, {pid}b, …)")
        if i == 0 and p.iq != c.deck.code:
            rep.e(u, "lint", f"first dot point {pid} belongs to {p.iq}, not to this deck ({c.deck.code})")
    if c.glossary and c.glossary not in syl.glossary:
        rep.e(u, "lint", f"unknown glossary term {c.glossary!r}")
    if c.keyword and c.keyword not in syl.keywords:
        rep.e(u, "lint", f"unknown key word {c.keyword!r}")
    if c.keyword and c.deck.code != "KW":
        rep.e(u, "lint", "keyword cards belong in the key-words deck")


def cited(c: Card) -> list[str]:
    return c.dp or (["KW." + c.keyword] if c.keyword else [])


# --------------------------------------------------------------------------- 2. coverage

def coverage(decks: list[Deck], syl: Syllabus, rep: Report) -> None:
    by_dp: dict[str, list[str]] = defaultdict(list)
    for d in decks:
        for c in d.cards:
            for pid in cited(c):
                by_dp[pid].append(c.uid)
    for p in syl.leaves():
        rep.coverage[p.id] = by_dp.get(p.id, []) + [u for ch in p.children for u in by_dp.get(ch, [])]
        if not rep.coverage[p.id]:
            if p.kind == "req":
                rep.e(p.id, "coverage", f"no card covers {dp_label(p.id)}: {p.text}")
            else:
                rep.w(p.id, "coverage", f"no card covers the 'for example' point {dp_label(p.id)}: {p.text}")


# --------------------------------------------------------------------------- 3. definitions

def _norm(s: str) -> str:
    s = plain(s).replace("−", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip()


def definitions(decks: list[Deck], syl: Syllabus, rep: Report) -> None:
    for d in decks:
        for c in d.cards:
            if c.glossary and c.glossary in syl.glossary:
                if _norm(c.a) != _norm(syl.glossary[c.glossary]):
                    rep.e(c.uid, "definition", f"answer differs from the syllabus glossary definition of "
                                               f"{c.glossary!r}: {syl.glossary[c.glossary]!r}")
            if c.keyword and c.keyword in syl.keywords:
                if _norm(c.a) != _norm(" ".join(syl.keywords[c.keyword])):
                    rep.e(c.uid, "definition", f"answer differs from NESA's definition of {c.keyword!r}: "
                                               f"{' / '.join(syl.keywords[c.keyword])!r}")


# --------------------------------------------------------------------------- 4. calculations

def calculations(decks: list[Deck], rep: Report) -> int:
    n = 0
    for d in decks:
        for c in d.cards:
            if not c.calc:
                continue
            n += 1
            spec = dict(c.calc)
            if "result" not in spec:
                rep.e(c.uid, "calc", "calc needs a declared result")
                continue
            declared = biocalc.normalise_result(spec.pop("result"))
            try:
                got = biocalc.calculate(spec)
            except (KeyError, ValueError, ZeroDivisionError) as ex:
                rep.e(c.uid, "calc", f"cannot compute: {ex}")
                continue
            if isinstance(got, float):
                got = biocalc.normalise_result(got)
            if isinstance(got, Fraction) and not isinstance(declared, Fraction):
                try:
                    declared = Fraction(str(declared))
                except ValueError:
                    pass
            if got != declared:
                rep.e(c.uid, "calc", f"declared result {declared!r} but the calculation gives {got!r}")
                continue
            target = c.a if c.q else c.cloze
            if not biocalc.answer_contains(plain(target), declared):
                rep.e(c.uid, "calc", f"answer doesn't state the result ({' or '.join(biocalc.answer_forms(declared))})")
    return n


# --------------------------------------------------------------------------- 5. spelling

def load_allowlist() -> set[str]:
    words = set()
    for line in (TOOLS / "spelling_allowlist.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            words.update(w.lower() for w in line.split())
    return words


def words_of(text: str) -> list[str]:
    text = plain(text).replace("’", "'")
    out = []
    for tok in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-]*", text):
        for part in tok.split("-"):
            part = re.sub(r"'s$|'$", "", part)
            if len(part) < 2 or "'" in part:
                continue
            if sum(ch.isupper() for ch in part) >= 2 or part.isupper():
                continue                                # acronyms and gene names: DNA, mRNA, CFTR
            if re.fullmatch(r"([A-Za-z])\1+", part, flags=re.I) and len(part) <= 4:
                continue                                # genotypes: Aa, bb, Tt
            out.append(part)
    return out


def au_variant_known(w: str, known) -> bool:
    for pat, rep in AU_TO_US:
        cand = re.sub(pat, rep, w)
        if cand != w and known(cand):
            return True
    cand = w
    for pat, rep in AU_TO_US:
        cand = re.sub(pat, rep, cand)
    return cand != w and known(cand)


def forms(w: str) -> list[str]:
    """The word and its likely singular/base forms (the dictionary lacks many plurals)."""
    out = [w]
    if w.endswith("ies"):
        out.append(w[:-3] + "y")
    if w.endswith("es"):
        out.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss"):
        out.append(w[:-1])
    if w.endswith("ae"):
        out.append(w[:-1])                              # Latin plurals: fimbriae → fimbria
    return out


def spelling(decks: list[Deck], rep: Report) -> None:
    from spellchecker import SpellChecker
    sc = SpellChecker(language="en")
    allow = load_allowlist()
    cache: dict[str, bool] = {}

    def known(w: str) -> bool:
        return w in sc or w in allow

    unknown: dict[str, list[str]] = defaultdict(list)
    for d in decks:
        for c in d.cards:
            text = " ".join(c.texts().values())
            for w in words_of(text):
                lw = w.lower()
                if lw in US_SPELLINGS:
                    rep.e(c.uid, "spelling", f"US spelling {w!r}: use {US_SPELLINGS[lw]!r}")
                    continue
                if IZE_RE.match(lw) and lw not in IZE_EXCEPTIONS and lw not in allow:
                    rep.e(c.uid, "spelling", f"US spelling {w!r}: use -ise/-isation")
                    continue
                if lw not in cache:
                    cache[lw] = any(known(f) or au_variant_known(f, known) for f in forms(lw))
                if not cache[lw]:
                    unknown[w].append(c.uid)
    for w, uids in sorted(unknown.items(), key=lambda kv: kv[0].lower()):
        rep.e(uids[0], "spelling", f"unknown word {w!r} (also in {', '.join(uids[1:4])})" if len(uids) > 1
              else f"unknown word {w!r}")


# --------------------------------------------------------------------------- 6. duplicates

def _qwords(c: Card) -> set[str]:
    t = c.q or CLOZE_RE.sub(lambda m: m.group(2), c.cloze)
    return {w for w in re.findall(r"[a-z0-9]+", plain(t).lower()) if w not in STOP}


def duplicates(decks: list[Deck], rep: Report) -> None:
    cards = [c for d in decks for c in d.cards]
    seen: dict[str, str] = {}
    for c in cards:
        k2 = re.sub(r"\W+", " ", (c.q or c.cloze).lower()).strip()
        if k2 in seen:
            rep.e(c.uid, "duplicate", f"same question as {seen[k2]}")
        seen.setdefault(k2, c.uid)
    sets = [(c, _qwords(c)) for c in cards]
    for i, (a, wa) in enumerate(sets):
        if len(wa) < 4:
            continue
        for b, wb in sets[i + 1:]:
            if len(wb) < 4:
                continue
            j = len(wa & wb) / len(wa | wb)
            if j >= 0.8 and _norm(a.a).lower() == _norm(b.a).lower():
                rep.w(b.uid, "duplicate", f"very similar to {a.uid} (same answer)")
            elif j >= 0.9:
                rep.w(b.uid, "duplicate", f"question very similar to {a.uid}")


# --------------------------------------------------------------------------- 7. manual review

def manual(decks: list[Deck], rep: Report) -> None:
    for d in decks:
        for c in d.cards:
            why = []
            body = " ".join(v for k, v in c.texts().items() if k != "hint")
            if re.search(r"\d", body) and not c.calc:
                why.append("numbers/dates")
            if "history" in c.tags:
                why.append("history of science")
            if "indigenous" in c.tags:
                why.append("Aboriginal and Torres Strait Islander content")
            if c.source:
                why.append("source")
            if c.review:
                why.append(f"author: {c.review}")
            if why:
                rep.manual[c.uid] = why


# --------------------------------------------------------------------------- report

def load_reviewed() -> set[str]:
    p = ROOT / "reviewed.yaml"
    if not p.exists():
        return set()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {str(x["id"] if isinstance(x, dict) else x) for x in data.get("reviewed") or []}


def short(c: Card) -> str:
    t = plain(c.q or CLOZE_RE.sub(lambda m: "[…]", c.cloze)).replace("\n", " ")
    return t if len(t) <= 110 else t[:107] + "…"


def write_report(decks: list[Deck], syl: Syllabus, rep: Report, checks: list[str], ncalc: int) -> Path:
    by_uid = {c.uid: c for d in decks for c in d.cards}
    err_by = Counter(u.split("-")[0] for u, _, _ in rep.errors if "-" in u)
    warn_by = Counter(u.split("-")[0] for u, _, _ in rep.warnings if "-" in u)
    L = ["# Verification report", "",
         "Generated by `tools/verify.py`. Do not edit by hand. See the README section "
         "*How accuracy is checked* for what each check does.", "",
         f"Checks run: {', '.join(checks)}", "",
         "| Deck | Inquiry question | Cards | Errors | Warnings |", "|---|---|---:|---:|---:|"]
    for d in decks:
        L.append(f"| {d.code} · {d.title} | {d.question or '—'} | {len(d.cards)} | "
                 f"{err_by.get(d.code, 0)} | {warn_by.get(d.code, 0)} |")
    total = sum(len(d.cards) for d in decks)
    L += [f"| **Total** | | **{total}** | **{len(rep.errors)}** | **{len(rep.warnings)}** |", ""]
    leaves = syl.leaves()
    covered = sum(1 for p in leaves if rep.coverage.get(p.id))
    L += [f"**Syllabus coverage:** {covered} of {len(leaves)} dot points have at least one card "
          f"(module content, Working Scientifically skills and NESA key words). "
          f"**Worked problems recomputed:** {ncalc}.", ""]
    for kind, items in (("Errors", rep.errors), ("Warnings", rep.warnings)):
        L += [f"## {kind} ({len(items)})", ""]
        L += [f"- `{u}` **{k}**: {m}" for u, k, m in items] or ["None."]
        L.append("")
    reviewed = load_reviewed()
    pending = [u for u in rep.manual if u not in reviewed]
    L += [f"## For human review ({len(rep.manual)})", "",
          "Correct as far as the machines can tell, but these involve facts a machine can't check. "
          f"**{len(pending)} cards pending.** When a biology teacher (or another qualified reviewer) has "
          "checked a card, add its id to `reviewed.yaml` and re-run `verify.py`; it will be ticked here.", ""]
    for d in decks:
        items = [c for c in d.cards if c.uid in rep.manual]
        if not items:
            continue
        L += [f"### {d.code} · {d.title} ({len(items)})", ""]
        for c in items:
            box = "x" if c.uid in reviewed else " "
            L.append(f"- [{box}] `{c.uid}` ({'; '.join(rep.manual[c.uid])}) {short(c)}")
        L.append("")
    L += ["## Coverage by dot point", "",
          "Number of cards citing each dot point (a card can cite several).", ""]
    current = None
    for p in leaves:
        group = p.iq
        if group != current:
            current = group
            L += ["", f"**{group}**", "", "| Dot point | Kind | Cards |", "|---|---|---:|"]
        n = len(rep.coverage.get(p.id, []))
        flag = "" if n else (" ❌" if p.kind == "req" else " ⚠️")
        label = p.id[3:] if p.module == "KW" else p.id if p.module == "WS" else dp_label(p.id)
        text = p.text if p.module != "KW" else "NESA key word"
        text = text if len(text) <= 120 else text[:117] + "…"
        L.append(f"| `{label}` {text} | {'for example' if p.kind == 'eg' else 'required'} | {n}{flag} |")
    out = ROOT / "VERIFICATION.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def run(decks: list[Deck], syl: Syllabus, spell: bool = True) -> tuple[Report, list[str], int]:
    rep = Report()
    checks = ["lint", "coverage", "definitions", "calculations"]
    lint(decks, syl, rep)
    coverage(decks, syl, rep)
    definitions(decks, syl, rep)
    ncalc = calculations(decks, rep)
    if spell:
        spelling(decks, rep)
        checks.append("spelling")
    duplicates(decks, rep)
    checks.append("duplicates")
    manual(decks, rep)
    return rep, checks, ncalc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-spell", action="store_true", help="skip the spelling check")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()
    syl = load_syllabus()
    decks = load_decks(syl)
    rep, checks, ncalc = run(decks, syl, spell=not args.no_spell)
    out = write_report(decks, syl, rep, checks, ncalc)
    n = sum(len(d.cards) for d in decks)
    for u, k, m in rep.errors:
        print(f"ERROR   {u:10} {k:11} {m}")
    for u, k, m in rep.warnings:
        print(f"warning {u:10} {k:11} {m}")
    covered = sum(1 for p in syl.leaves() if rep.coverage.get(p.id))
    print(f"{n} cards in {len(decks)} decks · coverage {covered}/{len(syl.leaves())} dot points · "
          f"{ncalc} worked problems recomputed · {len(rep.errors)} errors · {len(rep.warnings)} warnings · "
          f"{len(rep.manual)} for human review → {out.relative_to(ROOT.parent.parent)}")
    return 1 if rep.errors or (args.strict and rep.warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
