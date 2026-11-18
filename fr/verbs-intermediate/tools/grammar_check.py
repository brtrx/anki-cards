#!/usr/bin/env python3
"""Optional 4th check: run LanguageTool (French grammar & style) over every card.

    python fr/verbs-intermediate/tools/grammar_check.py --fetch   # first time: downloads LanguageTool via Maven
    python fr/verbs-intermediate/tools/grammar_check.py           # later runs
    python fr/verbs-intermediate/tools/grammar_check.py --url http://localhost:8081   # use a server you already run

Needs Java 17+ and (for --fetch) Maven. LanguageTool runs as a local HTTP
server on 127.0.0.1 that this script starts and stops; each card is sent to it
as a separate request, so every result maps cleanly to one card. Nothing is
sent to a web service. Results go to GRAMMAR.md; false positives can be
silenced in tools/grammar_ignore.yaml (card id + rule id + a reason).

Flags are advisory and never make the script fail. It exits non-zero only if
LanguageTool itself could not be fetched, started or queried.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckdata import ROOT, load_decks  # noqa: E402

TOOLS = Path(__file__).resolve().parent
POM = TOOLS / "languagetool" / "pom.xml"
DEFAULT_LIB = Path(os.environ.get("LT_LIB", Path.home() / ".cache" / "anki-cards" / "languagetool"))
SERVER_CLASS = "org.languagetool.server.HTTPServer"
# Categories about house style rather than correctness, or that clash with
# deliberate choices in these cards (straight apostrophes, → arrows…).
IGNORED_CATEGORIES = {"TYPOGRAPHY", "STYLE", "REDUNDANCY", "REPETITIONS_STYLE", "PLAIN_FRENCH"}


def fetch(lib: Path) -> None:
    lib.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mvn", "-q", "-f", str(POM), "dependency:copy-dependencies",
                    f"-DoutputDirectory={lib}"], check=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(base_url: str, text: str, timeout: float = 60) -> dict:
    """POST one text to LanguageTool's /v2/check and return the JSON response."""
    data = urllib.parse.urlencode({"language": "fr", "text": text}).encode()
    req = urllib.request.Request(f"{base_url.rstrip('/')}/v2/check", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class LocalServer:
    """Start LanguageTool's HTTP server on 127.0.0.1 and stop it afterwards."""

    def __init__(self, lib: Path, startup_timeout: float = 240):
        self.lib, self.startup_timeout = lib, startup_timeout
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False)
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "LocalServer":
        cmd = ["java", "-Xmx2g", "-cp", f"{self.lib}{os.sep}*", SERVER_CLASS, "--port", str(self.port)]
        self.proc = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + self.startup_timeout
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError(f"LanguageTool server exited with code {self.proc.returncode}:\n{self.log_tail()}")
            try:
                check(self.url, "Bonjour.", timeout=30)  # also warms up the French rules
                return self
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                if time.monotonic() > deadline:
                    raise RuntimeError(f"LanguageTool server not ready after {self.startup_timeout}s:\n{self.log_tail()}")
                time.sleep(1)

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()
        os.unlink(self.log.name)

    def log_tail(self, n: int = 40) -> str:
        self.log.flush()
        return "\n".join(Path(self.log.name).read_text(errors="replace").splitlines()[-n:])


def load_ignores(path: Path) -> set[tuple[str, str]]:
    import yaml
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {(str(e["id"]), str(e["rule"])) for e in (data.get("ignore") or [])}


def run_checks(base_url: str, ignores: set[tuple[str, str]]) -> tuple[int, list[str], Counter]:
    cards = [c for d in load_decks() for c in d.cards]
    rows, rules = [], Counter()
    for c in cards:
        result = check(base_url, c.plain)
        for m in result.get("matches", []):
            rule = m.get("rule", {})
            rid, cat = rule.get("id", ""), rule.get("category", {}).get("id", "")
            if cat in IGNORED_CATEGORIES or (c.uid, rid) in ignores:
                continue
            off, length = m.get("offset", 0), m.get("length", 0)
            flagged = c.plain[off:off + length]
            repl = ", ".join(r.get("value", "") for r in m.get("replacements", [])[:3])
            rules[rid] += 1
            rows.append(f"- [ ] `{c.uid}` **{flagged}** — {m.get('message', '')} "
                        f"(rule `{rid}`{'; suggestion: ' + repl if repl else ''})  \n"
                        f"  «{c.plain}»")
    return len(cards), rows, rules


def write_report(path: Path, n: int, rows: list[str], rules: Counter) -> None:
    lines = ["# Grammar report (LanguageTool)", "",
             "Generated by `tools/grammar_check.py` — advisory only. LanguageTool is good at agreement "
             "and spelling slips, weak on literary quotations and deliberate archaisms. For each item, "
             "either fix the card or add it to `tools/grammar_ignore.yaml` with a reason.", "",
             f"Sentences checked: {n} · Flags: {len(rows)}", ""]
    if rules:
        lines += ["| Rule | Flags |", "|---|---:|"] + [f"| `{r}` | {k} |" for r, k in rules.most_common()] + [""]
    lines += rows or ["No flags."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", type=Path, default=DEFAULT_LIB, help="folder of LanguageTool jars")
    ap.add_argument("--fetch", action="store_true", help="download LanguageTool with Maven first")
    ap.add_argument("--url", help="use an already-running LanguageTool server instead of starting one")
    ap.add_argument("--ignore", type=Path, default=TOOLS / "grammar_ignore.yaml")
    ap.add_argument("--report", type=Path, default=ROOT / "GRAMMAR.md")
    args = ap.parse_args(argv)

    ignores = load_ignores(args.ignore)
    if args.url:
        n, rows, rules = run_checks(args.url, ignores)
    else:
        if args.fetch or not any(args.lib.glob("language-fr-*.jar")):
            print(f"Fetching LanguageTool into {args.lib} …", flush=True)
            fetch(args.lib)
        print("Starting LanguageTool server …", flush=True)
        with LocalServer(args.lib) as server:
            n, rows, rules = run_checks(server.url, ignores)
    write_report(args.report, n, rows, rules)
    print(f"{n} sentences checked, {len(rows)} flags → {args.report.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
