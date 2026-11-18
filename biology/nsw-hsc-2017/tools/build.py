#!/usr/bin/env python3
"""Build Anki packages (.apkg) from src/*.yaml.

    python biology/nsw-hsc-2017/tools/build.py

Writes:
    dist/Biology_NSW_HSC_2017_syllabus.apkg     every deck in one package
    dist/decks/module-N-<slug>.apkg             one package per module (with its inquiry-question decks)
    dist/decks/skills-<slug>.apkg               the two skills decks

Note GUIDs are derived from (deck code, card id), so re-importing an updated
package updates existing notes instead of duplicating them, and the module
packages and the combined package can be mixed freely.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import genanki

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckdata import ROOT, Card, Deck, Syllabus, dp_label, load_decks, load_syllabus, md  # noqa: E402

PARENT = "Biology (NSW HSC · 2017 syllabus)"
QA_MODEL_ID = 1781205301
CLOZE_MODEL_ID = 1781205302
GUID_NS = "bio-nsw-hsc-2017"
QA_FIELDS = ["ID", "Question", "Hint", "Answer", "Explanation", "Tip", "Source", "Syllabus", "Ref", "Location"]
CLOZE_FIELDS = ["Text", "ID", "Hint", "Explanation", "Tip", "Source", "Syllabus", "Ref", "Location"]
DIST = ROOT / "dist"
NT = ROOT / "note_type"


def models() -> tuple[genanki.Model, genanki.Model]:
    css = (NT / "style.css").read_text(encoding="utf-8")
    qa = genanki.Model(
        QA_MODEL_ID, "Biology Q&A (nsw-hsc-2017)",
        fields=[{"name": f} for f in QA_FIELDS],
        templates=[{"name": "Question → answer",
                    "qfmt": (NT / "qa_front.html").read_text(encoding="utf-8"),
                    "afmt": (NT / "qa_back.html").read_text(encoding="utf-8")}],
        css=css, sort_field_index=QA_FIELDS.index("Question"))
    cloze = genanki.Model(
        CLOZE_MODEL_ID, "Biology cloze (nsw-hsc-2017)",
        fields=[{"name": f} for f in CLOZE_FIELDS],
        templates=[{"name": "Cloze",
                    "qfmt": (NT / "cloze_front.html").read_text(encoding="utf-8"),
                    "afmt": (NT / "cloze_back.html").read_text(encoding="utf-8")}],
        css=css, model_type=genanki.Model.CLOZE, sort_field_index=0)
    return qa, cloze


def deck_id(name: str) -> int:
    return (1 << 30) + int(hashlib.sha1(name.encode()).hexdigest()[:7], 16)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def cited(c: Card) -> list[str]:
    return c.dp or (["KW." + c.keyword] if c.keyword else [])


def syllabus_html(c: Card, syl: Syllabus) -> tuple[str, str]:
    refs, texts = [], []
    for pid in cited(c):
        p = syl.points[pid]
        if p.module == "KW":
            refs.append("Key words")
            texts.append("NESA Glossary of key words")
            continue
        label = dp_label(pid)
        refs.append(label)
        texts.append(f'<span class="ref">{label}</span> {md(p.text)}')
    return "<br>".join(texts), " · ".join(refs)


def fields_for(c: Card, syl: Syllabus) -> list[str]:
    syll, ref = syllabus_html(c, syl)
    common = {"ID": c.uid, "Hint": md(c.hint), "Explanation": md(c.x), "Tip": md(c.tip),
              "Source": md(c.source), "Syllabus": syll, "Ref": ref, "Location": c.deck.location}
    if c.is_cloze:
        common["Text"] = md(c.cloze)
        return [common[f] for f in CLOZE_FIELDS]
    common["Question"] = md(c.q)
    common["Answer"] = md(c.a)
    return [common[f] for f in QA_FIELDS]


def tags_for(c: Card) -> list[str]:
    d = c.deck
    if d.skills:
        t = [f"bio::skills::{d.skills}"]
    else:
        t = [f"bio::m{d.module}::iq{d.code}", f"bio::year{d.year}"]
    t += [f"bio::dp::{pid.replace(' ', '_')}" for pid in cited(c) if not pid.startswith("KW.")]
    t += [f"bio::{x}" for x in c.tags]
    if c.calc:
        t.append("bio::calc")
    if c.is_cloze:
        t.append("bio::cloze")
    return t


def description(d: Deck) -> str:
    if d.skills == "kw":
        return ("The key words NESA uses in HSC questions, with NESA's own definitions, plus what each "
                "demands in a Biology answer.")
    if d.skills == "ws":
        return ("Working Scientifically: the seven skill areas of the syllabus (questioning, planning, "
                "conducting, processing, analysing, problem solving, communicating).")
    return f"<b>Inquiry question:</b> {d.question}<br>Year {d.year} · Module {d.module}: {d.module_title}"


def build(decks: list[Deck], syl: Syllabus) -> None:
    qa, cloze = models()
    DIST.mkdir(exist_ok=True)
    (DIST / "decks").mkdir(exist_ok=True)
    parent = genanki.Deck(deck_id(PARENT), PARENT, description=(
        "NSW HSC Biology, <b>Biology Stage 6 Syllabus (2017)</b>: Year 11 (Modules 1–4) and Year 12 "
        "(Modules 5–8), one sub-deck per inquiry question, plus key words and Working Scientifically. "
        "The 2017 syllabus is examined up to and including the 2027 HSC."))
    all_decks = [parent]
    groups: dict[str, list[genanki.Deck]] = {}
    module_parents: dict[int, genanki.Deck] = {}
    due = 0
    for d in decks:
        if d.module and d.module not in module_parents:
            m_name = f"{PARENT}::{d.anki_path[0]}"
            mp = genanki.Deck(deck_id(m_name), m_name, description=(
                f"Year {d.year} · Module {d.module}: {d.module_title} (Biology Stage 6 Syllabus 2017)"))
            module_parents[d.module] = mp
            all_decks.append(mp)
            groups[f"module-{d.module}-{slug(d.module_title)}"] = [mp]
        name = "::".join([PARENT, *d.anki_path])
        gd = genanki.Deck(deck_id(name), name, description=description(d))
        for c in d.cards:
            due += 1
            gd.add_note(genanki.Note(model=cloze if c.is_cloze else qa, fields=fields_for(c, syl),
                                     tags=tags_for(c), guid=genanki.guid_for(GUID_NS, d.code, c.id), due=due))
        all_decks.append(gd)
        key = f"module-{d.module}-{slug(d.module_title)}" if d.module else f"skills-{slug(d.anki_path[0].split('·')[1])}"
        groups.setdefault(key, []).append(gd)
    for key, gds in groups.items():
        genanki.Package(gds).write_to_file(DIST / "decks" / f"{key}.apkg")
    genanki.Package(all_decks).write_to_file(DIST / "Biology_NSW_HSC_2017_syllabus.apkg")
    n = sum(len(d.cards) for d in decks)
    print(f"Built {n} notes in {len(decks)} decks → {DIST.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    syl = load_syllabus()
    build(load_decks(syl), syl)
