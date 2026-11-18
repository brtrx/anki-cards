"""Load deck sources (src/*.yaml) and render card fields.

Source format (one YAML file per sub-deck)::

    deck:
      number: 5
      slug: pc-vs-imparfait
      title: "Passé composé vs imparfait"
      mode: choice          # form | choice | recognise
      description: >
        Shown on the deck overview screen in Anki.
    cards:
      - id: 1                         # stable; never renumber (it seeds the note GUID)
        text: "Hier soir, nous {{sommes allés}} au cinéma."
        verb: aller
        tense: passe-compose
        person: 1p
        agree: mp                     # optional: ms fs mp fp inv, or f (= feminine, number from person)
        aux: avoir                    # optional: only for être-verbs used transitively (monter les valises)
        en: "Last night we went to the cinema."
        note: "Completed event at a specific time → passé composé."
        source: "…"                   # optional: attribution for quotations
        also: ["…"]                   # optional: other accepted answers
        cue: "…"                      # optional: overrides the generated cue
        tags: [quote]                 # optional extra tags
        check: false                  # optional: skip automatic conjugation check …
        check_reason: "…"             # … but then you must say why

The text marks the tested verb with {{…}}. Everything inside the braces is
what the learner must produce (verb plus any negation / clitic pronouns).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
BLANK_RE = re.compile(r"\{\{(.+?)\}\}")
MODES = {"form", "choice", "recognise"}


@dataclass
class Card:
    deck: "Deck"
    id: int
    text: str
    verb: str
    tense: str
    person: str | None
    en: str
    note: str = ""
    agree: str | None = None
    aux: str | None = None
    source: str = ""
    also: list[str] = field(default_factory=list)
    cue: str | None = None
    tags: list[str] = field(default_factory=list)
    check: bool = True
    check_reason: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.deck.number:02d}-{self.id:03d}"

    @property
    def answer(self) -> str:
        m = BLANK_RE.search(self.text)
        return m.group(1) if m else ""

    @property
    def plain(self) -> str:
        return typo(BLANK_RE.sub(lambda m: m.group(1), self.text))


@dataclass
class Deck:
    number: int
    slug: str
    title: str
    mode: str
    description: str
    path: Path
    cards: list[Card] = field(default_factory=list)

    @property
    def full_title(self) -> str:
        return f"{self.number:02d} · {self.title}"


def typo(s: str) -> str:
    """French typography: non-breaking spaces before ; : ! ? and inside « »."""
    s = re.sub(r" ([;!?])", " \\1", s)
    s = re.sub(r" :", " :", s)
    s = s.replace("« ", "« ").replace(" »", " »")
    return s


def md(s: str) -> str:
    """Tiny markdown: **bold**, *italic*; everything else HTML-escaped."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def load_decks(src: Path = SRC) -> list[Deck]:
    decks = []
    for path in sorted(src.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        d = data["deck"]
        deck = Deck(number=int(d["number"]), slug=d["slug"], title=d["title"],
                    mode=d.get("mode", "form"), description=d.get("description", "").strip(), path=path)
        for c in data.get("cards", []) or []:
            deck.cards.append(Card(
                deck=deck, id=int(c["id"]), text=c["text"], verb=c["verb"], tense=c["tense"],
                person=c.get("person"), en=c.get("en", ""), note=c.get("note", ""),
                agree=c.get("agree"), aux=c.get("aux"), source=c.get("source", ""), also=list(c.get("also", []) or []),
                cue=c.get("cue"), tags=list(c.get("tags", []) or []),
                check=c.get("check", True), check_reason=c.get("check_reason", ""), raw=c,
            ))
        decks.append(deck)
    return decks
