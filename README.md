# anki-cards

Anki decks, organised by subject. Each deck is kept as plain-text source
(YAML) with its own build and verification tools, so changes are reviewable
in Git and every release is checked before it's built.

| Subject | Deck | Level | Cards | Download |
|---|---|---|---:|---|
| 🇫🇷 French (`fr/`) | [French Verbs in Context](fr/verbs-intermediate/) — tenses, moods & verb forms in real sentences | B1–B2 | 488 | [`.apkg`](fr/verbs-intermediate/dist/French_Verbs_B1-B2.apkg) |
| 🧬 Biology (`biology/`) | [NSW HSC Biology](biology/nsw-hsc-2017/) — every dot point of the Biology Stage 6 Syllabus (2017), by module and inquiry question | Years 11–12 (HSC to 2027) | 886 | [`.apkg`](biology/nsw-hsc-2017/dist/Biology_NSW_HSC_2017_syllabus.apkg) |

## Layout

```
<subject>/                    one folder per subject (ISO 639-1 code for languages: fr, es, de…; plain names otherwise: biology)
  README.md                   index of that subject's decks
  <deck-name>/
    README.md                 what's in it, how to study it, pedagogy, how it's checked
    src/*.yaml                the cards — the only files you edit by hand
    note_type/                card templates and CSS
    tools/                    build.py, verify.py, test_verify.py, …
    dist/*.apkg               built packages, ready to import into Anki
    VERIFICATION.md           latest automated check report + human-review checklist
```

## Using a deck

Download the `.apkg` from the deck's `dist/` folder and open it with Anki
(desktop, AnkiDroid or AnkiMobile). Each deck's README has recommended
settings and study advice.

## Building and checking

```bash
pip install -r requirements.txt
python fr/verbs-intermediate/tools/test_verify.py   # self-test of the checker
python fr/verbs-intermediate/tools/verify.py        # check every card
python fr/verbs-intermediate/tools/build.py         # rebuild the .apkg files

python biology/nsw-hsc-2017/tools/test_verify.py    # same three steps for the biology deck
python biology/nsw-hsc-2017/tools/verify.py
python biology/nsw-hsc-2017/tools/build.py
```

GitHub Actions runs the same checks on every push and pull request
([`.github/workflows/verify.yml`](.github/workflows/verify.yml)).

## Adding a subject or deck

Create `<subject>/<deck-name>/` with its own `README.md`, sources, tools and
`dist/`, add it to the table above and to the subject's README, and add its
checks to the CI workflow. Keep decks small and focused: several sub-decks
of 20–50 cards beat one deck of 500.
