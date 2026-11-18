#!/usr/bin/env python3
"""Optional 4th check: run LanguageTool (French grammar & style) over every card.

    python fr/verbs-intermediate/tools/grammar_check.py --fetch   # first time: downloads LanguageTool via Maven
    python fr/verbs-intermediate/tools/grammar_check.py           # later runs

Needs Java 17+ and (for --fetch) Maven. LanguageTool runs locally; nothing is
sent to a web service. Results go to GRAMMAR.md. False positives can be
silenced in tools/grammar_ignore.yaml (card id + rule id + a reason).

This check is slower and noisier than verify.py, so it is advisory: it never
fails the build, it gives a human reviewer a short list of sentences to look at.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckdata import ROOT, load_decks  # noqa: E402

TOOLS = Path(__file__).resolve().parent
POM = TOOLS / "languagetool" / "pom.xml"
DEFAULT_LIB = Path(os.environ.get("LT_LIB", Path.home() / ".cache" / "anki-cards" / "languagetool"))
# Categories that are about house style rather than correctness, or that clash
# with deliberate choices in these cards (straight apostrophes, → arrows…).
IGNORED_CATEGORIES = {"TYPOGRAPHY", "STYLE", "REDUNDANCY", "REPETITIONS_STYLE", "PLAIN_FRENCH"}


def fetch(lib: Path) -> None:
    lib.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mvn", "-q", "-f", str(POM), "dependency:copy-dependencies",
                    f"-DoutputDirectory={lib}"], check=True)


def run_languagetool(lib: Path, lines: list[str]) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        path = f.name
    try:
        out = subprocess.run(
            ["java", "-cp", f"{lib}{os.sep}*", "org.languagetool.commandline.Main",
             "-l", "fr", "--json", path],
            check=True, capture_output=True, text=True, encoding="utf-8")
        return out.stdout
    finally:
        os.unlink(path)


def parse_lt_json(raw: str, lines: list[str]) -> list[tuple[int, dict]]:
    """Map LanguageTool matches back to input line numbers.

    Uses the character offset first; if that doesn't land inside a line's text,
    falls back to finding the match's sentence in the lines.
    """
    data = json.loads(raw[raw.index("{"):])
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1  # + newline
    found: list[tuple[int, dict]] = []
    for m in data.get("matches", []):
        idx = None
        off = m.get("offset")
        if isinstance(off, int):
            for i in range(len(starts) - 1, -1, -1):
                if starts[i] <= off:
                    if off - starts[i] < len(lines[i]):
                        idx = i
                    break
        if idx is None:
            sent = (m.get("sentence") or "").strip()
            idx = next((i for i, ln in enumerate(lines) if sent and sent in ln), None)
        if idx is not None:
            found.append((idx, m))
    return found


def load_ignores() -> set[tuple[str, str]]:
    import yaml
    f = TOOLS / "grammar_ignore.yaml"
    if not f.exists():
        return set()
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {(str(e["id"]), str(e["rule"])) for e in (data.get("ignore") or [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", type=Path, default=DEFAULT_LIB, help="folder of LanguageTool jars")
    ap.add_argument("--fetch", action="store_true", help="download LanguageTool with Maven first")
    ap.add_argument("--report", type=Path, default=ROOT / "GRAMMAR.md")
    args = ap.parse_args()

    if args.fetch or not any(args.lib.glob("language-fr-*.jar")):
        print(f"Fetching LanguageTool into {args.lib} …")
        fetch(args.lib)

    cards = [c for d in load_decks() for c in d.cards]
    lines = [c.plain.replace("\n", " ") for c in cards]
    raw = run_languagetool(args.lib, lines)
    ignores = load_ignores()

    rows = []
    for idx, m in parse_lt_json(raw, lines):
        c = cards[idx]
        rule = m.get("rule", {})
        cat = rule.get("category", {}).get("id", "")
        if cat in IGNORED_CATEGORIES or (c.uid, rule.get("id", "")) in ignores:
            continue
        ctx = m.get("context", {})
        text = ctx.get("text", "")
        flagged = text[ctx.get("offset", 0): ctx.get("offset", 0) + ctx.get("length", 0)]
        repl = ", ".join(r.get("value", "") for r in m.get("replacements", [])[:3])
        rows.append(f"- [ ] `{c.uid}` **{flagged}** — {m.get('message', '')} "
                    f"(rule `{rule.get('id', '')}`{'; try: ' + repl if repl else ''})  \n"
                    f"  «{c.plain}»")

    report = ["# Grammar report (LanguageTool)", "",
              "Generated by `tools/grammar_check.py` — advisory only. LanguageTool is good at agreement "
              "and spelling slips, weak on literary quotations and deliberate archaisms. For each item, "
              "either fix the card or add it to `tools/grammar_ignore.yaml` with a reason.", "",
              f"Sentences checked: {len(lines)} · Flags: {len(rows)}", ""] + (rows or ["No flags."])
    args.report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"{len(lines)} sentences checked, {len(rows)} flags → {args.report.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
