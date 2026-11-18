#!/usr/bin/env python3
"""Self-test: prove the checker catches typical learner/author mistakes.

    python fr/verbs-intermediate/tools/test_verify.py

Each fixture is a deliberately right or wrong card. A checker that passes
everything would be worthless, so this guards against silent regressions.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckdata import Card, Deck  # noqa: E402
from verify import Report, conjugation, lint  # noqa: E402

# (should_fail, kind expected, text, verb, tense, person, agree[, aux])
FIXTURES = [
    # --- must be accepted ---
    (False, None, "Hier, nous {{sommes allés}} au cinéma.", "aller", "passe-compose", "1p", None),
    (False, None, "Elle {{s'est levée}} tôt.", "se lever", "passe-compose", "3s", "f"),
    (False, None, "Je {{paye}} par carte.", "payer", "present", "1s", None),
    (False, None, "Je {{paie}} par carte.", "payer", "present", "1s", None),
    (False, None, "Je {{ne l'ai pas vue}}.", "voir", "passe-compose", "1s", "fs"),
    (False, None, "{{Vas-y}} !", "aller", "imperatif", "2s", None),
    (False, None, "{{Va}} chercher le pain.", "aller", "imperatif", "2s", None),
    (False, None, "{{Manges-en}} un peu.", "manger", "imperatif", "2s", None),
    (False, None, "{{Lève-toi}} !", "se lever", "imperatif", "2s", None),
    (False, None, "Il faut que tu {{viennes}}.", "venir", "subjonctif", "2s", None),
    (False, None, "Quand tu {{auras fini}}, appelle-moi.", "finir", "futur-anterieur", "2s", None),
    (False, None, "{{En faisant}} attention, tu réussiras.", "faire", "gerondif", None, None),
    (False, None, "Après {{s'être levées}}, elles sont parties.", "se lever", "infinitif-passe", None, "fp"),
    (False, None, "Il {{faut}} partir.", "falloir", "present", "3s", None),
    (False, None, "Elles se {{sont parlé}}.", "se parler", "passe-compose", "3p", "inv"),
    (False, None, "Tout le monde {{s'est tu}}.", "se taire", "passe-compose", "3s", None),
    (False, None, "Tu {{as sorti}} la poubelle ?", "sortir", "passe-compose", "2s", None, "avoir"),
    (False, None, "Elle {{est sortie}} hier soir.", "sortir", "passe-compose", "3s", "f"),
    # --- must be rejected ---
    (True, "conjugation", "Hier, nous {{sommes allé}} au cinéma.", "aller", "passe-compose", "1p", None),
    (True, "conjugation", "Hier, nous {{avons allés}} au cinéma.", "aller", "passe-compose", "1p", None),
    (True, "conjugation", "Elle {{s'est levé}} tôt.", "se lever", "passe-compose", "3s", "f"),
    (True, "conjugation", "Il faut que tu {{viens}}.", "venir", "subjonctif", "2s", None),
    (True, "conjugation", "Ils {{prenent}} le bus.", "prendre", "present", "3p", None),
    (True, "conjugation", "Je {{jeterai}} un œil.", "jeter", "futur", "1s", None),
    (True, "conjugation", "Si j'{{aurais}} su…", "avoir", "imparfait", "1s", None),
    (True, "conjugation", "Vous {{disez}} quoi ?", "dire", "present", "2p", None),
    (True, "conjugation", "{{Va-y}} !", "aller", "imperatif", "2s", None),
    (True, "conjugation", "{{Vas}} chercher le pain.", "aller", "imperatif", "2s", None),
    (True, "conjugation", "{{Mange-en}} un peu.", "manger", "imperatif", "2s", None),
    (True, "conjugation", "Il {{a mouru}} en 1821.", "mourir", "passe-compose", "3s", None),
    (True, "conjugation", "Je {{ne l'ai pas vu}}.", "voir", "passe-compose", "1s", "fs"),
    (True, "conjugation", "Tout le monde {{s'est tue}}.", "se taire", "passe-compose", "3s", None),
    (True, "conjugation", "Tu {{as sorti}} la poubelle ?", "sortir", "passe-compose", "2s", None),
    (True, "conjugation", "Tu {{es sorti}} la poubelle ?", "sortir", "passe-compose", "2s", None, "avoir"),
    (True, "conjugation", "Il {{faudra}} partir.", "falloir", "present", "3s", None),
    (True, "lint", "Je {{vais}} et je {{viens}}.", "aller", "present", "1s", None),
    (True, "lint", "Je {{chantrai}}.", "chantrer", "futur", "1s", None),
    (True, "reflexive", "Tu {{se lèves}} tôt.", "se lever", "present", "2s", None),
]


def main() -> int:
    deck = Deck(number=99, slug="test", title="test", mode="form", description="", path=Path("test.yaml"))
    failures = 0
    for i, (should_fail, kind, text, verb, tense, person, agree, *rest) in enumerate(FIXTURES, 1):
        deck.cards = [Card(deck=deck, id=i, text=text, verb=verb, tense=tense, person=person,
                           agree=agree, aux=rest[0] if rest else None, en="Test.", note="Test.")]
        rep = Report()
        lint([deck], rep)
        conjugation([deck], rep)
        kinds = {k for _, k, _ in rep.errors}
        ok = (bool(kinds) == should_fail) and (kind is None or kind in kinds)
        status = "ok  " if ok else "FAIL"
        want = f"reject ({kind})" if should_fail else "accept"
        print(f"{status} {want:22} {text}" + ("" if ok else f"   → errors: {rep.errors}"))
        failures += not ok
    print(f"\n{len(FIXTURES) - failures}/{len(FIXTURES)} fixtures behaved as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
