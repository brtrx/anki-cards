#!/usr/bin/env python3
"""Double-check every card. Writes VERIFICATION.md and exits non-zero on errors.

    python fr/verbs-intermediate/tools/verify.py            # all checks
    python fr/verbs-intermediate/tools/verify.py --no-spell # skip spelling
    python fr/verbs-intermediate/tools/verify.py --strict   # warnings also fail

Checks
  1. lint         structure: one blank, valid tense/person/agreement, unique ids,
                  subject and reflexive pronouns agree with the declared person,
                  French typography, œ ligatures, English present.
  2. conjugation  the answer is compared with the form computed *independently*
                  by verbecc (Verbiste data) from the declared verb/tense/person/
                  agreement. Auxiliary choice comes from verbecc, not the author.
  3. spelling     every word of every full sentence is checked against a French
                  dictionary (pyspellchecker) + all verbecc forms + an allowlist;
                  English translations against an English dictionary.
  4. manual list  things a machine cannot judge (tense-choice cards, agreement
                  with a preceding direct object, quotations) are listed for a
                  human reviewer.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conj  # noqa: E402
from deckdata import BLANK_RE, MODES, ROOT, Card, load_decks  # noqa: E402

TOOLS = Path(__file__).resolve().parent
SUBJECTS = {"je": "1s", "j'": "1s", "tu": "2s", "il": "3s", "elle": "3s", "on": "3s",
            "nous": "1p", "vous": "2p", "ils": "3p", "elles": "3p"}
REFLEXIVE = {"1s": {"me", "m'"}, "2s": {"te", "t'"}, "3s": {"se", "s'"},
             "1p": {"nous"}, "2p": {"vous"}, "3p": {"se", "s'"}}
REFLEXIVE_IMPERATIVE = {"2s": {"toi", "te", "t'"}, "1p": {"nous"}, "2p": {"vous"}}
ALL_REFLEXIVE = {"me", "m'", "te", "t'", "se", "s'", "nous", "vous", "toi"}
AGREE = {None, "ms", "fs", "mp", "fp", "m", "f", "inv"}
LIGATURE_WORDS = re.compile(r"\b(coeur|soeur|oeuvre|oeil|oeuf|boeuf|voeu|noeud|moeurs|manoeuvre|oe?illet)s?\b", re.I)
ELISIONS = {"l", "d", "j", "m", "t", "s", "n", "c", "qu", "jusqu", "lorsqu", "puisqu", "quoiqu", "presqu", "quelqu"}


class Report:
    def __init__(self):
        self.errors: list[tuple[str, str, str]] = []
        self.warnings: list[tuple[str, str, str]] = []
        self.manual: list[tuple[str, str, str]] = []

    def e(self, c, kind, msg): self.errors.append((c, kind, msg))
    def w(self, c, kind, msg): self.warnings.append((c, kind, msg))
    def m(self, c, kind, msg): self.manual.append((c, kind, msg))


def subject_before(card: Card) -> str | None:
    """Declared-person check: find a subject pronoun right before (or inverted after) the blank."""
    ans = card.answer.lower()
    if re.match(r"^j'", ans):
        return "1s"
    before, _, after = card.text.partition("{{")
    after = after.split("}}", 1)[1] if "}}" in after else ""
    m = re.match(r"^-(?:t-)?(je|tu|il|elle|on|nous|vous|ils|elles)\b", after)
    if m:
        return SUBJECTS[m.group(1)]
    before = before.rstrip()
    if before.lower().endswith("j'"):
        return "1s"
    words = re.split(r"[\s]+", before)
    if not words or not words[-1]:
        return None
    last = words[-1].lower().strip(",;:«»\"(")
    if "'" in last:
        last = last.split("'")[-1]
    return SUBJECTS.get(last)


def lint(decks, rep: Report) -> None:
    seen_numbers, seen_slugs, texts = set(), set(), {}
    for d in decks:
        if d.mode not in MODES:
            rep.e(d.path.name, "lint", f"unknown mode {d.mode!r}")
        if d.number in seen_numbers or d.slug in seen_slugs:
            rep.e(d.path.name, "lint", "duplicate deck number or slug")
        seen_numbers.add(d.number); seen_slugs.add(d.slug)
        ids = Counter(c.id for c in d.cards)
        for i, n in ids.items():
            if n > 1:
                rep.e(f"{d.number:02d}-{i:03d}", "lint", f"id used {n} times in {d.path.name}")
        for c in d.cards:
            u = c.uid
            blanks = BLANK_RE.findall(c.text)
            if len(blanks) != 1:
                rep.e(u, "lint", f"needs exactly one {{{{…}}}} blank, found {len(blanks)}")
                continue
            if c.tense not in conj.TENSES:
                rep.e(u, "lint", f"unknown tense {c.tense!r}"); continue
            if c.tense in conj.NO_PERSON:
                if c.person not in (None, *conj.PERSONS):
                    rep.e(u, "lint", f"bad person {c.person!r}")
            elif c.person not in conj.PERSONS:
                rep.e(u, "lint", f"person must be one of {sorted(conj.PERSONS)}, got {c.person!r}")
            if c.tense == "imperatif" and c.person not in ("2s", "1p", "2p"):
                rep.e(u, "lint", "imperative person must be 2s, 1p or 2p")
            if c.aux not in (None, "avoir", "être"):
                rep.e(u, "lint", f"aux must be avoir or être, got {c.aux!r}")
            if c.agree not in AGREE:
                rep.e(u, "lint", f"agree must be one of ms fs mp fp m f inv, got {c.agree!r}")
            ok, why = conj.verb_known(c.verb)
            if not ok:
                rep.e(u, "lint", f"verb {c.verb!r}: {why}")
            if not c.en:
                rep.e(u, "lint", "missing English translation")
            elif not re.search(r"[.!?…»\"”)]$", c.en.strip()):
                rep.w(u, "lint", "English translation lacks final punctuation")
            if not c.note:
                rep.w(u, "lint", "no explanatory note")
            if not c.check and not c.check_reason:
                rep.e(u, "lint", "check: false needs a check_reason")
            if d.mode == "recognise" and c.tense not in conj.EVERYDAY_EQUIVALENT:
                rep.w(u, "lint", "recognition card on a non-literary tense")
            key = re.sub(r"\W+", " ", c.plain.lower()).strip()
            if key in texts:
                rep.e(u, "lint", f"same sentence as {texts[key]}")
            texts[key] = u
            # French typography
            plain = BLANK_RE.sub(lambda m: m.group(1), c.text)
            if re.search(r"[^\s«(\-]([?!;])", plain) or re.search(r"[^\s\d]:", plain):
                rep.w(u, "typography", "French needs a space before ? ! ; : — " + plain)
            if re.search(r"«\S|\S»", plain):
                rep.w(u, "typography", "French needs spaces inside « »")
            if LIGATURE_WORDS.search(plain + " " + " ".join(c.also)):
                rep.w(u, "typography", "use the œ ligature (cœur, sœur, œuvre…)")
            # subject pronoun vs declared person
            if c.tense not in conj.NO_PERSON and c.tense != "imperatif":
                s = subject_before(c)
                if s and s != c.person:
                    rep.w(u, "person", f"pronoun before blank suggests {s}, card says {c.person}")
            # reflexive pronoun vs person
            refl, _ = conj.split_reflexive(c.verb)
            if refl and c.person in conj.PERSONS:
                toks = conj.tokens(c.answer)
                if toks and toks[0] in ("j'",):
                    toks = toks[1:]
                found = [t for t in toks if t in ALL_REFLEXIVE]
                allowed = REFLEXIVE_IMPERATIVE[c.person] if c.tense == "imperatif" else REFLEXIVE[c.person]
                if not found:
                    rep.w(u, "reflexive", f"pronominal verb but no reflexive pronoun in the blank: {c.answer!r}")
                elif found[0] not in allowed:
                    rep.e(u, "reflexive", f"reflexive {found[0]!r} does not match person {c.person}")
            if d.mode == "choice":
                rep.m(u, "tense choice", f"{c.verb} → {conj.TENSES[c.tense][0]}: is this the *only* natural tense here? «{c.plain}»")
            if c.source:
                rep.m(u, "quotation", f"check wording & attribution: «{c.plain}» — {c.source}")
            if c.also:
                rep.m(u, "alternatives", f"accepted alternatives {c.also} for «{c.plain}»")


def conjugation(decks, rep: Report) -> None:
    for d in decks:
        for c in d.cards:
            if c.tense not in conj.TENSES or len(BLANK_RE.findall(c.text)) != 1:
                continue
            if not c.check:
                rep.m(c.uid, "unchecked", f"conjugation check skipped: {c.check_reason}")
                continue
            try:
                euph = bool(re.search(r"-(y|en)\b", c.answer.lower())) if c.tense == "imperatif" else None
                exp, info = conj.expected(c.verb, c.tense, c.person, c.agree, euphonic=euph, aux=c.aux)
            except Exception as ex:  # noqa: BLE001
                rep.e(c.uid, "conjugation", f"verbecc could not conjugate {c.verb!r} ({c.tense}, {c.person}): {ex}")
                continue
            got = conj.core(c.answer)
            if c.tense == "gerondif" and "en" not in conj.tokens(c.answer):
                rep.e(c.uid, "conjugation", f"gérondif must include 'en': {c.answer!r}")
            if got not in exp:
                rep.e(c.uid, "conjugation",
                      f"{c.verb} / {c.tense} / {c.person} / agree={c.agree}: answer {' '.join(got)!r} "
                      f"≠ verbecc {[' '.join(e) for e in exp]}")
            for i in info:
                rep.m(c.uid, "agreement", f"{i}: «{c.plain}»")


def _fr_words(s: str) -> list[str]:
    s = s.replace("’", "'")
    s = re.sub(r"(?i)aujourd'hui", "aujourd_hui", s)
    out = []
    for tok in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœÆæ_']+", s):
        parts = tok.split("'")
        for i, p in enumerate(parts):
            if not p:
                continue
            if i < len(parts) - 1 and p.lower() in ELISIONS:
                continue
            out.append(p)
    return out


def spelling(decks, rep: Report) -> None:
    from spellchecker import SpellChecker
    fr = SpellChecker(language="fr", distance=1)
    en = SpellChecker(language="en", distance=1)
    allow_fr, allow_en = set(), set()
    allow_file = TOOLS / "spelling_allowlist.txt"
    if allow_file.exists():
        section = "fr"
        for line in allow_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]; continue
            if line and not line.startswith("#"):
                (allow_fr if section == "fr" else allow_en).add(line.lower())
    verb_words: set[str] = set()
    for v in {c.verb for d in decks for c in d.cards}:
        try:
            verb_words |= conj.all_forms(v)
        except Exception:  # noqa: BLE001
            pass

    def fr_ok(w: str) -> bool:
        lw = w.lower()
        if lw in allow_fr or lw in verb_words or lw == "aujourd_hui":
            return True
        alt = lw.replace("œ", "oe").replace("æ", "ae")
        return bool(fr.known([lw])) or bool(fr.known([alt]))

    hyphenated = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:-[A-Za-zÀ-ÖØ-öø-ÿŒœ]+)+")
    for d in decks:
        for c in d.cards:
            text = c.plain + " " + " ".join(c.also)
            # accept compound words known as a whole (pique-niquer, grand-mère…)
            text = hyphenated.sub(lambda m: " " if fr_ok(m.group(0)) else m.group(0), text)
            for w in dict.fromkeys(_fr_words(text)):
                if not fr_ok(w):
                    rep.w(c.uid, "spelling-fr", f"unknown word {w!r} in «{c.plain}»")
            for w in re.findall(r"[A-Za-zÀ-ÿ]+(?:'[a-z]+)?", c.en):
                if "'" in w and not w.endswith("'s"):
                    continue  # contractions (couldn't, I'd…)
                base = re.sub(r"'s$", "", w)
                lw = base.lower()
                if not lw or lw in allow_en or en.known([lw]) or base[0].isupper() and lw not in en:
                    continue
                rep.w(c.uid, "spelling-en", f"unknown English word {w!r}: {c.en}")


def load_reviewed() -> dict[str, dict]:
    import yaml
    f = ROOT / "reviewed.yaml"
    if not f.exists():
        return {}
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {str(e["id"]): e for e in (data.get("reviewed") or [])}


def write_report(decks, rep: Report, path: Path, ran: list[str]) -> None:
    by_deck_e, by_deck_w = Counter(), Counter()
    for u, *_ in rep.errors:
        by_deck_e[u[:2]] += 1
    for u, *_ in rep.warnings:
        by_deck_w[u[:2]] += 1
    lines = ["# Verification report", "",
             "Generated by `tools/verify.py` — do not edit by hand. "
             "See the README section *How accuracy is checked* for what each check does.", "",
             f"Checks run: {', '.join(ran)}", "",
             "| Deck | Mode | Cards | Errors | Warnings |", "|---|---|---:|---:|---:|"]
    total = 0
    for d in decks:
        k = f"{d.number:02d}"
        total += len(d.cards)
        lines.append(f"| {d.full_title} | {d.mode} | {len(d.cards)} | {by_deck_e[k]} | {by_deck_w[k]} |")
    lines.append(f"| **Total** | | **{total}** | **{len(rep.errors)}** | **{len(rep.warnings)}** |")
    lines.append("")

    def section(title, items, intro=""):
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        if intro:
            lines.extend([intro, ""])
        if not items:
            lines.extend(["None.", ""])
            return
        grouped = defaultdict(list)
        for u, kind, msg in items:
            grouped[kind].append((u, msg))
        for kind, rows in grouped.items():
            lines.append(f"### {kind} ({len(rows)})")
            lines.append("")
            for u, msg in sorted(rows):
                if msg.startswith(("[x] ", "[ ] ")):
                    lines.append(f"- {msg[:3]} `{u}` {msg[4:]}")
                else:
                    lines.append(f"- `{u}` {msg}")
            lines.append("")

    section("Errors", rep.errors)
    section("Warnings", rep.warnings)
    done = load_reviewed()
    pending = sorted({u for u, *_ in rep.manual} - set(done))
    manual = [(u, k, ("[x] " if u in done else "[ ] ") + m) for u, k, m in rep.manual]
    section("For human review", manual,
            "Correct as far as the machines can tell, but these involve judgement. "
            f"**{len(pending)} cards pending.** When a fluent speaker has checked a card, "
            "add it to `reviewed.yaml` and re-run `verify.py` — it will be ticked here.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-spell", action="store_true", help="skip spelling checks")
    ap.add_argument("--strict", action="store_true", help="fail on warnings too")
    ap.add_argument("--report", default=str(ROOT / "VERIFICATION.md"))
    args = ap.parse_args()

    decks = load_decks()
    rep = Report()
    ran = ["lint", "conjugation"]
    lint(decks, rep)
    conjugation(decks, rep)
    if not args.no_spell:
        spelling(decks, rep)
        ran.append("spelling")
    write_report(decks, rep, Path(args.report), ran)

    n = sum(len(d.cards) for d in decks)
    print(f"{n} cards in {len(decks)} decks: {len(rep.errors)} errors, {len(rep.warnings)} warnings, "
          f"{len(rep.manual)} items for human review → {Path(args.report).name}")
    for u, kind, msg in rep.errors:
        print(f"  ERROR   {u} [{kind}] {msg}")
    for u, kind, msg in rep.warnings:
        print(f"  warning {u} [{kind}] {msg}")
    return 1 if rep.errors or (args.strict and rep.warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
