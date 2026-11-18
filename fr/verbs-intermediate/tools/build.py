#!/usr/bin/env python3
"""Build Anki packages (.apkg) from src/*.yaml.

    python fr/verbs-intermediate/tools/build.py

Writes:
    dist/French_Verbs_B1-B2.apkg       all sub-decks in one package
    dist/decks/NN-slug.apkg            one package per sub-deck

Note GUIDs are derived from (deck number, card id), so re-importing an
updated package updates existing notes instead of duplicating them, and
the per-deck packages and the combined package can be mixed freely.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import genanki

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conj  # noqa: E402
from deckdata import BLANK_RE, ROOT, Card, Deck, load_decks, md, typo  # noqa: E402

PARENT = "French::Verbs (B1–B2)"
MODEL_ID = 1735040111
GUID_NS = "fr-verbs-intermediate"
FIELDS = ["ID", "Front", "Cue", "Back", "Answer", "Solution", "Plain", "English", "Note",
          "Also", "Source", "Glance", "Verb", "Tense", "DeckTitle"]
DIST = ROOT / "dist"


def model() -> genanki.Model:
    nt = ROOT / "note_type"
    return genanki.Model(
        MODEL_ID,
        "French verb in context (fr-verbs-intermediate)",
        fields=[{"name": f} for f in FIELDS],
        templates=[{
            "name": "Verb in context",
            "qfmt": (nt / "front.html").read_text(encoding="utf-8"),
            "afmt": (nt / "back.html").read_text(encoding="utf-8"),
        }],
        css=(nt / "style.css").read_text(encoding="utf-8"),
        sort_field_index=FIELDS.index("Front"),
    )


def deck_id(name: str) -> int:
    return (1 << 30) + int(hashlib.sha1(name.encode()).hexdigest()[:7], 16)


def gender_hint(card: Card) -> str:
    """Tell the learner the gender when the sentence alone can't (je/tu/nous/vous + être)."""
    if card.agree in (None, "inv") or card.person not in ("1s", "2s", "1p", "2p"):
        return ""
    if card.tense not in conj.COMPOUND or (card.aux or conj.auxiliary(card.verb)) != "être":
        return ""
    g, n = conj.parse_agree(card.agree, card.person)
    if card.person == "2p" and n == "s":
        return ("fém." if g == "f" else "masc.") + " sing. (vous de politesse)"
    if g == "f":
        return "fém. pl." if n == "p" else "fém."
    return ""


def cue_for(card: Card) -> str:
    if card.cue:
        return card.cue
    label = conj.TENSES[card.tense][0]
    mode = card.deck.mode
    if mode == "recognise":
        eq = conj.EVERYDAY_EQUIVALENT.get(card.tense)
        return f"infinitif ? → {conj.TENSES[eq][0]} ?" if eq else "infinitif ? temps ?"
    parts = [card.verb] if mode == "choice" else [card.verb, label]
    gh = gender_hint(card)
    if gh:
        parts.append(gh)
    return " · ".join(parts)


def solution_for(card: Card) -> str:
    if card.deck.mode != "recognise":
        return ""
    eq = conj.EVERYDAY_EQUIVALENT.get(card.tense, card.tense)
    gender = "m"
    if card.agree:
        gender = conj.parse_agree(card.agree, card.person)[0]
    elif re.search(r"\b[Ee]lles?\s*$", card.text.split("{{")[0]):
        gender = "f"
    return f"{card.verb} → {conj.full_form(card.verb, eq, card.person, gender)}"


def fields_for(card: Card) -> list[str]:
    text = typo(card.text)
    if card.deck.mode == "recognise":
        front = BLANK_RE.sub(lambda m: f'<span class="target">{m.group(1)}</span>', text)
    else:
        front = BLANK_RE.sub('<span class="blank">&nbsp;</span>', text)
    back = BLANK_RE.sub(lambda m: f'<span class="ans">{m.group(1)}</span>', text)
    return [
        card.uid,
        front,
        cue_for(card),
        back,
        typo(card.answer),
        solution_for(card),
        card.plain,
        card.en,
        md(card.note),
        " · ".join(typo(a) for a in card.also),
        md(card.source),
        conj.glance(card.verb),
        card.verb,
        conj.TENSES[card.tense][0],
        card.deck.full_title,
    ]


def tags_for(card: Card) -> list[str]:
    t = [f"fr::verbs::{card.deck.number:02d}-{card.deck.slug}",
         f"fr::tense::{card.tense}",
         f"fr::verb::{card.verb.replace(' ', '_').replace(chr(39), '_')}",
         f"fr::mode::{card.deck.mode}"]
    t += [f"fr::{x}" for x in card.tags]
    if card.source and "quote" not in card.tags:
        t.append("fr::quote")
    return t


def build(decks: list[Deck]) -> None:
    m = model()
    DIST.mkdir(exist_ok=True)
    (DIST / "decks").mkdir(exist_ok=True)
    parent = genanki.Deck(deck_id(PARENT), PARENT, description=(
        "Intermediate (B1–B2) French verbs in context. Study the numbered sub-decks in order; "
        "reviews from all unlocked sub-decks are mixed automatically."))
    all_decks = [parent]
    due = 0
    for d in decks:
        name = f"{PARENT}::{d.full_title}"
        gd = genanki.Deck(deck_id(name), name, description=md(d.description).replace("\n", "<br>"))
        for c in d.cards:
            due += 1
            gd.add_note(genanki.Note(model=m, fields=fields_for(c), tags=tags_for(c),
                                     guid=genanki.guid_for(GUID_NS, d.number, c.id), due=due))
        genanki.Package(gd).write_to_file(DIST / "decks" / f"{d.number:02d}-{d.slug}.apkg")
        all_decks.append(gd)
    genanki.Package(all_decks).write_to_file(DIST / "French_Verbs_B1-B2.apkg")
    n = sum(len(d.cards) for d in decks)
    print(f"Built {n} notes in {len(decks)} sub-decks → {DIST.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    build(load_decks())
