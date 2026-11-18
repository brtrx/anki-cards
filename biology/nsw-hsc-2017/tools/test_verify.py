#!/usr/bin/env python3
"""Self-test: prove the checker catches typical author mistakes.

    python biology/nsw-hsc-2017/tools/test_verify.py

Each fixture is a deliberately right or wrong card. A checker that passes
everything would be worthless, so this guards against silent regressions.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckdata import Card, Deck, load_syllabus  # noqa: E402
from verify import Report, calculations, coverage, definitions, duplicates, lint, spelling  # noqa: E402

SYL = load_syllabus()

# (should_fail, check expected to fire, card fields)
FIXTURES = [
    # ---------------------------------------------------------------- must be accepted
    (False, None, dict(q="What does DNA helicase do?", a="Unwinds the double helix by breaking hydrogen bonds.",
                       dp=["5.2.1b"])),
    (False, None, dict(q="Why is haemoglobin red?", a="Its colour comes from haem; the oesophagus is specialised.",
                       dp=["5.2.1b"])),
    (False, None, dict(q="Template 3'-TACGGT-5' is transcribed to give what mRNA?", a="5'-AUGCCA-3'",
                       dp=["5.2.1b"], calc=dict(kind="transcribe", template="3'-TACGGT-5'", result="5'-AUGCCA-3'"))),
    (False, None, dict(q="Ratio of phenotypes from Aa × Aa?", a="3:1 dominant to recessive.", dp=["5.2.1a"],
                       calc=dict(kind="cross", p1="A/a", p2="A/a", ask="phenotype-ratio", result={"A": 3, "a": 1}))),
    (False, None, dict(q="Blood groups of children of IAi × IBi?", a="A : AB : B : O = 1 : 1 : 1 : 1", dp=["5.2.1a"],
                       calc=dict(kind="cross", p1="IA/i", p2="IB/i", mode="abo", ask="phenotype-ratio",
                                 result={"A": 1, "AB": 1, "B": 1, "O": 1}))),
    (False, None, dict(q="Chance a son of a carrier mother and unaffected father has haemophilia?",
                       a="50% (1/2).", dp=["5.2.1a"],
                       calc=dict(kind="cross", p1="XH/Xh", p2="XH/Y", ask="probability", of="h", given="male",
                                 result="1/2"))),
    (False, None, dict(q="Reliability (syllabus glossary)?", glossary="reliability", dp=["5.2.1a"],
                       a="An extent to which repeated observations and/or measurements taken under identical "
                         "circumstances will yield similar results.")),
    (False, None, dict(cloze="Mitosis gives {{c1::two}} cells; meiosis gives {{c2::four}}.", dp=["5.2.1a"])),
    (False, None, dict(q="NESA key word: Assess", keyword="Assess",
                       a="Make a judgement of value, quality, outcomes, results or size.")),
    (False, None, dict(q="Mass 2.5 g → 2.2 g: % change?", a="−12%", dp=["5.2.1a"],
                       calc=dict(kind="percent-change", initial=2.5, final=2.2, result=-12))),
    (False, None, dict(q="Age with 25% carbon-14 left?", a="About 11 460 years.", dp=["5.2.1a"],
                       calc=dict(kind="halflife", half_life=5730, remaining=0.25, result=11460))),
    (False, None, dict(q="Daughter of a carrier mother and unaffected father: chance of haemophilia?", a="0%",
                       dp=["5.2.1a"], calc=dict(kind="cross", p1="XH/Xh", p2="XH/Y", ask="probability", of="h",
                                                given="female", result="0"))),
    # ---------------------------------------------------------------- must be rejected
    (True, "spelling", dict(q="What carries oxygen in red blood cells?", a="Hemoglobin.", dp=["5.2.1a"])),
    (True, "spelling", dict(q="What are cells that have a role called?", a="Specialized cells.", dp=["5.2.1a"])),
    (True, "spelling", dict(q="Where is ATP made?", a="In the mitocondria.", dp=["5.2.1a"])),
    (True, "lint", dict(q="Unknown dot point?", a="x", dp=["5.9.9"])),
    (True, "lint", dict(q="Parent dot point that has sub-points?", a="x", dp=["5.2.1"])),
    (True, "lint", dict(q="First dot point from another inquiry question?", a="x", dp=["7.3.1"])),
    (True, "lint", dict(q="Both a question and a cloze?", a="x", cloze="{{c1::x}}", dp=["5.2.1a"])),
    (True, "lint", dict(cloze="Gap in numbering {{c1::one}} and {{c3::three}}.", dp=["5.2.1a"])),
    (True, "lint", dict(q="Unknown tag?", a="x", dp=["5.2.1a"], tags=["australia"])),
    (True, "calc", dict(q="Template 3'-TACGGT-5' gives what mRNA?", a="5'-AUGCCU-3'", dp=["5.2.1b"],
                        calc=dict(kind="transcribe", template="3'-TACGGT-5'", result="5'-AUGCCU-3'"))),
    (True, "calc", dict(q="Phenotype ratio of Aa × aa?", a="3:1", dp=["5.2.1a"],
                        calc=dict(kind="cross", p1="A/a", p2="a/a", result={"A": 3, "a": 1}))),
    (True, "calc", dict(q="Phenotype ratio of Aa × aa (answer states the wrong ratio)?", a="It is 3:1.",
                        dp=["5.2.1a"], calc=dict(kind="cross", p1="A/a", p2="a/a", result={"A": 1, "a": 1}))),
    (True, "calc", dict(q="Chance a son of a carrier mother has haemophilia?", a="1/4", dp=["5.2.1a"],
                        calc=dict(kind="cross", p1="XH/Xh", p2="XH/Y", ask="probability", of="h", given="male",
                                  result="1/4"))),
    (True, "calc", dict(q="Translate AUGUUUUAG?", a="Met-Leu", dp=["5.2.1b"],
                        calc=dict(kind="translate", mrna="AUGUUUUAG", result="Met-Leu"))),
    (True, "calc", dict(q="SA:V of a 3 cm cube?", a="3:1", dp=["5.2.1a"],
                        calc=dict(kind="sav", shape="cube", side=3, result="3:1"))),
    (True, "definition", dict(q="Reliability (syllabus glossary)?", glossary="reliability", dp=["5.2.1a"],
                              a="How close a measurement is to the true value.")),
    (True, "definition", dict(q="NESA key word: Assess", keyword="Assess", a="Make a judgement based on criteria.")),
    (True, "calc", dict(q="Daughter of a carrier mother and unaffected father: chance of haemophilia?", a="1/4",
                        dp=["5.2.1a"], calc=dict(kind="cross", p1="XH/Xh", p2="XH/Y", ask="probability", of="h",
                                                 given="female", result="1/4"))),
    (True, "calc", dict(q="Roan × roan phenotype ratio?", a="1:1", dp=["5.2.1a"],
                        calc=dict(kind="cross", p1="CR/CW", p2="CR/CW", mode="codominant", result={"CR/CW": 1, "CR/CR": 1}))),
    (True, "calc", dict(q="Age with 12.5% carbon-14 left?", a="11460 years", dp=["5.2.1a"],
                        calc=dict(kind="halflife", half_life=5730, remaining=0.125, result=11460))),
    (True, "calc", dict(q="Frequency of allele a with 40 AA, 40 Aa, 20 aa?", a="0.3", dp=["5.2.1a"],
                        calc=dict(kind="allele-frequency", hom_dom=40, het=40, hom_rec=20, allele="rec", result=0.3))),
    (True, "calc", dict(q="Cells after 1 hour, doubling every 20 min, from one cell?", a="6", dp=["5.2.1a"],
                        calc=dict(kind="growth", start=1, doubling_min=20, time_min=60, result=6))),
    (True, "calc", dict(q="If A = 20%, what % is C?", a="20%", dp=["5.2.1b"],
                        calc=dict(kind="chargaff", A=20, ask="C", result=20))),
    (True, "calc", dict(q="Quadrats 2, 4, 6 (1 m²) in 100 m²?", a="300", dp=["5.2.1a"],
                        calc=dict(kind="quadrat", counts=[2, 4, 6], quadrat_m2=1, area_m2=100, result=300))),
    (True, "calc", dict(q="Mass 2.0 g → 1.5 g: % change?", a="−20%", dp=["5.2.1a"],
                        calc=dict(kind="percent-change", initial=2.0, final=1.5, result=-20))),
    (True, "lint", dict(q="Triple asterisks?", a="***Bold italic***", dp=["5.2.1a"])),
    (True, "lint", dict(q="Card with an unknown field?", a="x", dp=["5.2.1a"], extra="oops")),
]


def make(fields: dict, n: int, deck: Deck) -> Card:
    raw = {"id": n, **fields}
    return Card(deck=deck, id=n, q=fields.get("q", ""), a=fields.get("a", ""), cloze=fields.get("cloze", ""),
                dp=fields.get("dp", []), tags=fields.get("tags", []), calc=fields.get("calc"),
                glossary=fields.get("glossary"), keyword=fields.get("keyword"), raw=raw)


def new_deck(fields: dict | None = None) -> Deck:
    if fields and fields.get("keyword"):
        return Deck(code="KW", path=Path("fixture.yaml"), skills="kw", title="Key words")
    return Deck(code="5.2", path=Path("fixture.yaml"), module=5, iq=2, title="Cell Replication",
                question="How important is it for genetic material to be replicated exactly?",
                module_title="Heredity", year=12)


def check(card: Card) -> Report:
    rep = Report()
    lint([card.deck], SYL, rep)
    definitions([card.deck], SYL, rep)
    calculations([card.deck], rep)
    spelling([card.deck], rep)
    return rep


def main() -> int:
    failures = 0
    for n, (should_fail, kind, fields) in enumerate(FIXTURES, 1):
        deck = new_deck(fields)
        card = make(fields, n, deck)
        deck.cards.append(card)
        rep = check(card)
        kinds = {k for _, k, _ in rep.errors}
        label = fields.get("q") or fields.get("cloze")
        if should_fail and kind not in kinds:
            failures += 1
            print(f"MISSED  ({kind}) {label}  → errors: {rep.errors}")
        elif not should_fail and rep.errors:
            failures += 1
            print(f"FALSE ALARM  {label}  → {rep.errors}")
    # duplicates and coverage work across cards
    deck = new_deck()
    deck.cards += [make(dict(q="What does DNA ligase do?", a="Joins fragments.", dp=["5.2.1b"]), 1, deck),
                   make(dict(q="What does DNA ligase do?", a="Seals nicks.", dp=["5.2.1b"]), 2, deck)]
    rep = Report()
    duplicates([deck], rep)
    if not any(k == "duplicate" for _, k, _ in rep.errors):
        failures += 1
        print("MISSED  (duplicate) identical questions")
    rep = Report()
    coverage([deck], SYL, rep)
    if not any(u == "5.2.2" and k == "coverage" for u, k, _ in rep.errors):
        failures += 1
        print("MISSED  (coverage) dot point 5.2.2 has no card")
    if any(u == "5.2.1b" for u, _, _ in rep.errors):
        failures += 1
        print("FALSE ALARM  (coverage) 5.2.1b is covered")
    if not any(u == "5.5.1a" for u, _, _ in rep.warnings) or any(u == "5.5.1a" for u, _, _ in rep.errors):
        failures += 1
        print("WRONG LEVEL  (coverage) an uncovered 'for example' point should be a warning, not an error")
    total = len(FIXTURES) + 4
    print(f"{total - failures}/{total} self-tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
