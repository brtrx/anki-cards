"""Load the syllabus map and the deck sources, and render card text.

Source format: one YAML file per deck in src/.

    deck:
      module: 5            # syllabus module, with…
      iq: 1                # …the inquiry question number (title and question come from syllabus.yaml)
      # or, for the two skills decks:
      skills: kw           # kw = NESA key words, ws = Working Scientifically
    cards:
      - id: 1                          # stable; never renumber (it seeds the note GUID)
        q: "Question?"                 # a question card has q + a …
        a: "Short answer."
        cloze: "… {{c1::term}} …"      # … or a cloze card has cloze instead (no a)
        x: "Explanation (optional)."
        tip: "Exam tip (optional)."
        hint: "Shown on demand on the front (optional)."
        source: "Attribution for data or quotations (optional)."
        dp: [5.1.1a, 5.1.2]            # syllabus dot points covered; the first must belong to this deck
        tags: [aus]                    # optional extra tags (see README)
        calc: {kind: cross, …}         # optional worked problem, recomputed by verify.py (see biocalc.py)
        glossary: reliability          # optional: a must be the syllabus glossary definition, word for word
        keyword: Assess                # optional (kw deck): a must be NESA's definition, word for word
        review: "why this needs a human check (optional)"

Text fields use a little markdown: **bold**, *italic*, X^H^ superscript, line breaks, "- " bullet
lists, "1. " numbered lists and "| a | b |" tables. Write chemistry with Unicode
sub/superscripts (CO₂, C₆H₁₂O₆, Na⁺).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CLOZE_RE = re.compile(r"\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}")
SKILLS = {
    "kw": ("KW", "Skills · Key words (NESA glossary)"),
    "ws": ("WS", "Skills · Working Scientifically"),
}


# --------------------------------------------------------------------------- syllabus

@dataclass
class DotPoint:
    id: str              # e.g. "5.1.1" or "5.1.1a" or "WS.2.2" or "KW.Assess"
    text: str            # full text for display (parent text + sub-point for sub-points)
    kind: str            # req | eg
    module: str          # "5", "WS", "KW"
    iq: str              # "5.1", "WS", "KW"
    leaf: bool = True    # citable by a card, and counted for coverage
    children: list[str] = field(default_factory=list)


@dataclass
class Syllabus:
    modules: list[dict]
    ws: list[dict]
    glossary: dict[str, str]
    keywords: dict[str, list[str]]
    points: dict[str, DotPoint] = field(default_factory=dict)

    def iq(self, module: int, iq: int) -> tuple[dict, dict]:
        m = next(m for m in self.modules if m["number"] == module)
        return m, next(q for q in m["iqs"] if q["number"] == iq)

    def leaves(self) -> list[DotPoint]:
        return [p for p in self.points.values() if p.leaf]


def load_syllabus(root: Path = ROOT) -> Syllabus:
    s = yaml.safe_load((root / "syllabus.yaml").read_text(encoding="utf-8"))
    k = yaml.safe_load((root / "keywords.yaml").read_text(encoding="utf-8"))
    syl = Syllabus(s["modules"], s["working_scientifically"], s["glossary"], k["keywords"])
    for m in s["modules"]:
        for q in m["iqs"]:
            iq = f"{m['number']}.{q['number']}"
            for dp in q["dot_points"]:
                subs = dp.get("subs") or []
                # A dot point whose sub-points are all "for example" is itself the requirement,
                # so cards may cite it directly; otherwise cards must cite a sub-point.
                only_eg = bool(subs) and all(sp["kind"] == "eg" for sp in subs)
                syl.points[dp["id"]] = DotPoint(dp["id"], dp["text"], "req", str(m["number"]), iq,
                                                leaf=not subs or only_eg,
                                                children=[dp["id"] + sp["id"] for sp in subs])
                for sp in subs:
                    pid = dp["id"] + sp["id"]
                    syl.points[pid] = DotPoint(pid, f"{dp['text']} {sp['text']}", sp["kind"], str(m["number"]), iq)
    for area in s["working_scientifically"]:
        for dp in area["dot_points"]:
            syl.points[dp["id"]] = DotPoint(dp["id"], dp["text"], "req", "WS", "WS")
    for word in k["keywords"]:
        pid = "KW." + word
        syl.points[pid] = DotPoint(pid, f"NESA glossary of key words: {word}", "req", "KW", "KW")
    return syl


# --------------------------------------------------------------------------- decks and cards

@dataclass
class Card:
    deck: "Deck"
    id: int
    q: str = ""
    a: str = ""
    cloze: str = ""
    x: str = ""
    tip: str = ""
    hint: str = ""
    source: str = ""
    dp: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    calc: dict | None = None
    glossary: str | None = None
    keyword: str | None = None
    review: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.deck.code}-{self.id:03d}"

    @property
    def is_cloze(self) -> bool:
        return bool(self.cloze)

    def texts(self) -> dict[str, str]:
        """The learner-visible text fields, by name."""
        return {k: v for k, v in (("q", self.q), ("a", self.a), ("cloze", self.cloze), ("x", self.x),
                                  ("tip", self.tip), ("hint", self.hint)) if v}


@dataclass
class Deck:
    code: str            # "5.1", "KW", "WS"
    path: Path
    module: int | None = None
    iq: int | None = None
    skills: str | None = None
    title: str = ""      # "Reproduction"
    question: str = ""   # the inquiry question
    module_title: str = ""
    year: int | None = None
    cards: list[Card] = field(default_factory=list)

    @property
    def anki_path(self) -> list[str]:
        """Deck path below the parent deck."""
        if self.skills:
            return [SKILLS[self.skills][1]]
        return [f"Module {self.module} · {self.module_title}", f"{self.code} · {self.title}"]

    @property
    def location(self) -> str:
        """Breadcrumb shown on each card."""
        if self.skills:
            return SKILLS[self.skills][1]
        return f"Module {self.module} · {self.module_title} › {self.code} {self.title}"

    @property
    def sort_key(self) -> tuple:
        if self.skills:
            return (99, 0 if self.skills == "kw" else 1)
        return (self.module, self.iq)


def load_decks(syl: Syllabus | None = None, src: Path = SRC) -> list[Deck]:
    syl = syl or load_syllabus()
    decks = []
    for path in sorted(src.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        d = data["deck"]
        if "skills" in d:
            code, title = SKILLS[d["skills"]]
            deck = Deck(code=code, path=path, skills=d["skills"], title=title)
        else:
            m, q = syl.iq(int(d["module"]), int(d["iq"]))
            deck = Deck(code=f"{m['number']}.{q['number']}", path=path, module=m["number"], iq=q["number"],
                        title=q["heading"], question=q["question"], module_title=m["title"], year=m["year"])
        for c in data.get("cards") or []:
            deck.cards.append(Card(
                deck=deck, id=int(c["id"]), q=c.get("q", ""), a=str(c.get("a", "")), cloze=c.get("cloze", ""),
                x=c.get("x", ""), tip=c.get("tip", ""), hint=c.get("hint", ""), source=c.get("source", ""),
                dp=[str(p) for p in (c.get("dp") or [])], tags=list(c.get("tags") or []), calc=c.get("calc"),
                glossary=c.get("glossary"), keyword=c.get("keyword"), review=c.get("review", ""), raw=c))
        decks.append(deck)
    decks.sort(key=lambda d: d.sort_key)
    return decks


# --------------------------------------------------------------------------- rendering

def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\^([^\^\s]+)\^", r"<sup>\1</sup>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    return s


def _list_type(line: str) -> str | None:
    if re.match(r"^\s*- ", line):
        return "ul"
    if re.match(r"^\s*\d+\. ", line):
        return "ol"
    return None


def md(s: str) -> str:
    """Tiny markdown → HTML: **bold**, *italic*, lists, tables, line breaks."""
    if not s:
        return ""
    blocks: list[tuple[str, str]] = []          # (kind, html); kind = text | block | blank
    lines = s.strip("\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head, body = rows[0], rows[1:]
            t = "<table><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr>"
            t += "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
            blocks.append(("block", t + "</table>"))
            continue
        tag = _list_type(line)
        if tag:
            items = []
            while i < len(lines) and _list_type(lines[i]) == tag:
                items.append(re.sub(r"^\s*(- |\d+\. )", "", lines[i]))
                i += 1
            blocks.append(("block", f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>"))
            continue
        blocks.append(("blank", "") if not line.strip() else ("text", _inline(line)))
        i += 1
    out = ""
    for j, (kind, h) in enumerate(blocks):
        prev = blocks[j - 1][0] if j else None
        if kind == "text" and prev == "text":
            out += "<br>"
        elif kind == "text" and prev == "blank" and j > 1 and blocks[j - 2][0] == "text":
            out += '<div class="gap"></div>'
        out += h
    return out


def plain(s: str) -> str:
    """Text with cloze and markdown markup removed (for checks)."""
    s = CLOZE_RE.sub(lambda m: m.group(2), s)
    s = re.sub(r"\*\*|(?<![\w*])\*|\*(?![\w*])", "", s)
    s = re.sub(r"\^([^\^\s]+)\^", r"\1", s)
    s = re.sub(r"^\s*(- |\d+\. )", "", s, flags=re.M)
    return s.replace("|", " ")


def dp_label(pid: str) -> str:
    m = re.fullmatch(r"(\d+\.\d+\.\d+)([a-z])", pid)
    return f"{m.group(1)}({m.group(2)})" if m else pid
