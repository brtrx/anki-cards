#!/usr/bin/env python3
"""Self-test for grammar_check.py, without Java or LanguageTool.

    python fr/verbs-intermediate/tools/test_grammar_check.py

A stub HTTP server answers /v2/check in LanguageTool's JSON format, so the
client side (requests, offset → word mapping, category filtering, ignore list,
report) is exercised on every CI run. A second test checks that a server which
cannot start produces a clear error rather than hanging.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grammar_check  # noqa: E402


def match(text: str, anchor: str, word: str, rule: str, category: str) -> dict:
    """A LanguageTool-style match on `word` inside `anchor`, offsets in UTF-16 units."""
    py_off = text.index(anchor) + anchor.index(word)
    off = grammar_check.u16len(text[:py_off])
    return {"message": f"stub {rule}", "offset": off, "length": grammar_check.u16len(word),
            "replacements": [{"value": word.upper()}],
            "rule": {"id": rule, "category": {"id": category}}}


class Stub(BaseHTTPRequestHandler):
    calls = 0
    sizes: list[int] = []

    def do_POST(self):  # noqa: N802
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        assert self.path == "/v2/check" and form["language"] == ["fr"], (self.path, form)
        text = form["text"][0]
        Stub.calls += 1
        Stub.sizes.append(len(text))
        matches = []
        if "nées à Marseille" in text:
            matches.append(match(text, "nous sommes nées à Marseille", "nées", "STUB_AGREEMENT", "GRAMMAR"))
        if "Qui dort dîne" in text:
            matches.append(match(text, "Qui dort dîne", "dîne", "STUB_STYLE", "STYLE"))       # filtered by category
        if "Ça suffit" in text:
            matches.append(match(text, "Ça suffit", "suffit", "STUB_IGNORED", "GRAMMAR"))    # filtered by ignore file
        if "Rira bien" in text:  # a match on the last word of a card: must map to that card
            matches.append(match(text, "rira le dernier.", "dernier", "STUB_LAST_WORD", "GRAMMAR"))
        body = json.dumps({"matches": matches}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_client_against_stub() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "ignore.yaml").write_text("ignore:\n  - id: 02-039\n    rule: STUB_IGNORED\n    reason: test\n")
        report = tmp / "GRAMMAR.md"
        rc = grammar_check.main(["--url", f"http://127.0.0.1:{srv.server_port}",
                                 "--ignore", str(tmp / "ignore.yaml"), "--report", str(report)])
        out = report.read_text()
        assert rc == 0
        assert "Flags: 2" in out, out[:500]
        assert "`04-019` **nées**" in out, out
        assert "`07-020` **dernier**" in out, out
        assert "STUB_STYLE" not in out and "STUB_IGNORED" not in out
        n = int(out.split("Sentences checked: ")[1].split(" ")[0])
        assert n > 400 and Stub.calls <= n // 20, (n, Stub.calls)
        assert max(Stub.sizes) <= grammar_check.BATCH_CHARS + 600, max(Stub.sizes)
        print(f"ok   client vs stub server: {n} cards in {Stub.calls} batched requests, 2 flags kept, 2 filtered")
    finally:
        srv.shutdown()
        shutil.rmtree(tmp)


def test_helpers() -> None:
    s = "a😀 nées"                       # 😀 is 2 UTF-16 units but 1 Python char
    assert grammar_check.u16len(s) == 8
    assert grammar_check.u16_slice(s, 4, 4) == "nées"
    groups = grammar_check.batches(["x" * 3000] * 5, len)
    assert [len(g) for g in groups] == [1, 1, 1, 1, 1], groups
    groups = grammar_check.batches(["x" * 100] * 120, len)
    assert sum(map(len, groups)) == 120 and len(groups) == 3, [len(g) for g in groups]
    print("ok   UTF-16 offsets and batching")


def test_server_start_failure_is_reported() -> None:
    if not shutil.which("java"):
        print("skip server-start failure test (no java)")
        return
    empty = Path(tempfile.mkdtemp())
    try:
        with grammar_check.LocalServer(empty, startup_timeout=60):
            raise AssertionError("server should not have started without jars")
    except RuntimeError as e:
        assert "exited with code" in str(e), e
        print("ok   missing jars → clear error after retrying without config, no hang")
    finally:
        shutil.rmtree(empty)


if __name__ == "__main__":
    test_helpers()
    test_client_against_stub()
    test_server_start_failure_is_reported()
    print("grammar_check self-test passed")
