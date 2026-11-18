"""Thin wrapper around verbecc (Verbiste-derived French conjugation data).

This module is the *independent reference* used to double-check every card:
the card author declares (verb, tense, person, agreement) and this module
computes what the form should be, without looking at the author's answer.

It is also used to generate the "verb at a glance" strip on the back of
each card, so that strip never contains hand-typed conjugations.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from functools import lru_cache

# verbecc writes ./verbecc.log on import; keep it out of the repo.
_cwd = os.getcwd()
os.chdir(tempfile.gettempdir())
try:
    from verbecc import CompleteConjugator
    from verbecc.core.defs.types.lang_code import LangCodeISO639_1
finally:
    os.chdir(_cwd)
logging.disable(logging.CRITICAL)

# key -> (label shown to learners, verbecc mood, verbecc tense)
# Tenses with mood None are periphrastic/composed and built here.
TENSES: dict[str, tuple[str, str | None, str | None]] = {
    "present": ("présent", "indicatif", "présent"),
    "imparfait": ("imparfait", "indicatif", "imparfait"),
    "passe-compose": ("passé composé", "indicatif", "passé-composé"),
    "plus-que-parfait": ("plus-que-parfait", "indicatif", "plus-que-parfait"),
    "passe-simple": ("passé simple", "indicatif", "passé-simple"),
    "passe-anterieur": ("passé antérieur", "indicatif", "passé-antérieur"),
    "futur": ("futur simple", "indicatif", "futur-simple"),
    "futur-anterieur": ("futur antérieur", "indicatif", "futur-antérieur"),
    "conditionnel": ("conditionnel présent", "conditionnel", "présent"),
    "conditionnel-passe": ("conditionnel passé", "conditionnel", "passé"),
    "subjonctif": ("subjonctif présent", "subjonctif", "présent"),
    "subjonctif-passe": ("subjonctif passé", "subjonctif", "passé"),
    "subjonctif-imparfait": ("subjonctif imparfait", "subjonctif", "imparfait"),
    "subjonctif-pqp": ("subjonctif plus-que-parfait", "subjonctif", "plus-que-parfait"),
    "imperatif": ("impératif", "imperatif", "imperatif-présent"),
    "participe-present": ("participe présent", "participe", "participe-présent"),
    "gerondif": ("gérondif", "participe", "participe-présent"),
    "participe-passe": ("participe passé", "participe", "participe-passé"),
    "infinitif": ("infinitif", None, None),
    "infinitif-passe": ("infinitif passé", None, None),
    "participe-passe-compose": ("participe passé composé", None, None),
    "futur-proche": ("futur proche", None, None),
    "passe-recent": ("passé récent", None, None),
}

# Literary tenses -> the everyday tense a reader should "translate" them to.
EVERYDAY_EQUIVALENT = {
    "passe-simple": "passe-compose",
    "passe-anterieur": "plus-que-parfait",
    "subjonctif-imparfait": "subjonctif",
    "subjonctif-pqp": "subjonctif-passe",
}

COMPOUND = {
    "passe-compose", "plus-que-parfait", "passe-anterieur", "futur-anterieur",
    "conditionnel-passe", "subjonctif-passe", "subjonctif-pqp",
    "infinitif-passe", "participe-passe-compose", "participe-passe",
}

PERSONS = {"1s": ("1", "s"), "2s": ("2", "s"), "3s": ("3", "s"),
           "1p": ("1", "p"), "2p": ("2", "p"), "3p": ("3", "p")}
NO_PERSON = {"participe-present", "gerondif", "participe-passe", "infinitif",
             "infinitif-passe", "participe-passe-compose"}

ETRE_FORMS = set("""être étant été suis es est sommes êtes sont étais était étions
étiez étaient serai seras sera serons serez seront serais serait serions seriez
seraient sois soit soyons soyez soient fus fut fûmes fûtes furent fusse fusses
fût fussions fussiez fussent""".split())

# Clitics / negation stripped before comparing the verb core. Subject pronouns
# are NOT stripped (blanks never contain them, and *tu* is also the participle
# of *taire*); strip_subject() removes them from verbecc's output instead.
STRIP = set("""ne n' pas plus jamais rien guère point personne aucun aucune nullement
me m' te t' se s' nous vous le la l' les lui leur y en moi toi t que qu' j' c'
déjà encore bien mal beaucoup trop toujours souvent vraiment enfin presque assez
vite longtemps tout""".split())  # adverbs often sit between auxiliary and participle

SUBJECT_RE = re.compile(r"^(que |qu')?(je |j'|tu |il |elle |on |nous |vous |ils |elles )")


@lru_cache(maxsize=None)
def _conjugator() -> CompleteConjugator:
    os.chdir(tempfile.gettempdir())
    try:
        return CompleteConjugator(LangCodeISO639_1.fr)
    finally:
        os.chdir(_cwd)


def split_reflexive(verb: str) -> tuple[bool, str]:
    """'se lever' -> (True, 'lever'); "s'en aller" -> (True, 'aller')."""
    v = verb.strip()
    for pre in ("se ", "s'"):
        if v.startswith(pre):
            base = v[len(pre):]
            if base.startswith("en "):
                base = base[3:]
            return True, base
    return False, v


def verb_known(verb: str) -> tuple[bool, str]:
    """Is the verb in the Verbiste dictionary (no ML guessing, exact accents)?"""
    _, base = split_reflexive(verb)
    try:
        v = _conjugator().find_verb_by_infinitive(base)
    except Exception as e:  # VerbNotFoundError
        return False, f"not found ({type(e).__name__})"
    if getattr(v, "predicted", False):
        return False, "only an ML guess - not in dictionary"
    if v.infinitive != base:
        return False, f"matched '{v.infinitive}' (accents differ)"
    return True, v.template


# Known gaps in verbecc's data, filled by hand from standard reference tables
# (Bescherelle). Any card whose check relies on these is listed for human review.
OVERRIDES: dict[tuple[str, str, str], str] = {
    ("falloir", "indicatif", "présent"): "il faut",
    ("falloir", "indicatif", "imparfait"): "il fallait",
    ("falloir", "indicatif", "futur-simple"): "il faudra",
    ("falloir", "indicatif", "passé-simple"): "il fallut",
    ("falloir", "conditionnel", "présent"): "il faudrait",
    ("falloir", "subjonctif", "présent"): "qu'il faille",
    ("falloir", "subjonctif", "imparfait"): "qu'il fallût",
}
AUX_TENSE = {  # (mood, compound tense) -> simple tense of the auxiliary
    ("indicatif", "passé-composé"): "présent",
    ("indicatif", "plus-que-parfait"): "imparfait",
    ("indicatif", "passé-antérieur"): "passé-simple",
    ("indicatif", "futur-antérieur"): "futur-simple",
    ("conditionnel", "passé"): "présent",
    ("subjonctif", "passé"): "présent",
    ("subjonctif", "plus-que-parfait"): "imparfait",
}


def verbecc_name(verb: str) -> str:
    """verbecc refuses 's'en aller' etc.; conjugate the bare verb (clitics are stripped anyway)."""
    return verb[5:] if verb.startswith("s'en ") else verb


def used_override(verb: str, mood: str, tense: str) -> bool:
    _, base = split_reflexive(verb)
    return (base, mood, tense) in OVERRIDES and _raw_rows(verbecc_name(verb), mood, tense) == []


@lru_cache(maxsize=None)
def _raw_rows(verb: str, mood: str, tense: str) -> list[dict]:
    r = _conjugator().conjugate_mood_tense(verb, mood, tense, conjugate_pronouns=True)
    d = json.loads(str(r))
    d = d if isinstance(d, list) else d.get("conjugations", [])
    # verbecc marks missing forms with '-'
    return [x for x in d if any(f.strip() not in ("-", "que -") for f in x.get("c", []))]


@lru_cache(maxsize=None)
def rows(verb: str, mood: str, tense: str) -> list[dict]:
    refl, base = split_reflexive(verb)
    name = verbecc_name(verb)
    out = _raw_rows(name, mood, tense)
    if not out and (base, mood, tense) in OVERRIDES:
        out = [{"c": [OVERRIDES[(base, mood, tense)]], "p": "3", "n": "s", "g": "m", "pr": "il"}]
    if verb.startswith("s'en ") and (mood, tense) in AUX_TENSE:
        # pronominal, so the auxiliary is être whatever the bare verb takes
        pp = participles(base)
        out = [{**r, "c": [f"{a} {pp.get((r.get('g') or 'm', r.get('n') or 's'), pp[('m', 's')])[0]}"
                           for a in r["c"]]}
               for r in _raw_rows("être", mood, AUX_TENSE[(mood, tense)])]
    return out


def strip_subject(form: str) -> str:
    return SUBJECT_RE.sub("", form, count=1)


def tokens(s: str) -> list[str]:
    """Lower-case tokens, splitting on spaces and hyphens, keeping elision marks."""
    s = s.lower().replace("’", "'")
    out: list[str] = []
    for chunk in re.split(r"[\s\-]+", s):
        chunk = chunk.strip(".,;:!?«»\"()")
        while "'" in chunk:
            head, chunk = chunk.split("'", 1)
            out.append(head + "'")
        if chunk:
            out.append(chunk)
    return out


def core(s: str) -> tuple[str, ...]:
    """Verb core of a string: drop negation and clitic pronouns."""
    out = []
    for t in tokens(s):
        if t in STRIP:
            continue
        if t == "d'":
            t = "de"
        out.append(t)
    return tuple(out)


def _pick(rs: list[dict], p: str | None, n: str | None, g: str | None) -> list[dict]:
    cand = [r for r in rs if (p is None or r.get("p") == p) and (n is None or r.get("n") == n)]
    if g:
        gm = [r for r in cand if r.get("g") == g]
        if gm:
            return gm
    return cand


def participles(verb: str) -> dict[tuple[str, str], list[str]]:
    _, base = split_reflexive(verb)
    out: dict[tuple[str, str], list[str]] = {}
    for r in rows(base, "participe", "participe-passé"):
        out[(r.get("g") or "m", r.get("n") or "s")] = r["c"]
    return out


def auxiliary(verb: str) -> str:
    """'être' or 'avoir', according to verbecc's own passé composé."""
    refl, base = split_reflexive(verb)
    if refl:
        return "être"
    rs = rows(base, "indicatif", "passé-composé")
    first = core(strip_subject(rs[0]["c"][0]))[0]
    return "être" if first in ETRE_FORMS else "avoir"


def parse_agree(agree: str | None, person: str | None) -> tuple[str, str] | None:
    """'fp' -> ('f','p'); 'f' -> ('f', number of person); None -> None; 'inv' -> ('m','s')."""
    if agree is None:
        return None
    if agree == "inv":
        return ("m", "s")
    g = agree[0]
    if len(agree) == 2:
        return (g, agree[1])
    number = PERSONS[person][1] if person in PERSONS else "s"
    return (g, number)


def expected(verb: str, tense: str, person: str | None, agree: str | None,
             euphonic: bool | None = None, aux: str | None = None) -> tuple[list[tuple[str, ...]], list[str]]:
    """Return (acceptable verb cores, info messages).

    euphonic: for 2s imperatives, True if followed by -y/-en (vas-y, manges-en),
    False if not (va, mange), None to accept both.
    aux: declared auxiliary for verbs that switch (monter/sortir/passer… + direct
    object take avoir); None = verbecc's default.
    """
    info: list[str] = []
    label, mood, vtense = TENSES[tense]
    refl, base = split_reflexive(verb)
    p, n = PERSONS.get(person, (None, None))
    ag = parse_agree(agree, person)

    def pp_forms(default_gn: tuple[str, str]) -> list[str]:
        gn = ag or default_gn
        return participles(verb).get(gn) or participles(verb)[("m", "s")]

    default_aux = auxiliary(verb) if tense in COMPOUND else None
    aux = aux or default_aux
    if tense in COMPOUND and aux != default_aux:
        info.append(f"auxiliary {aux} declared (verbecc default: {default_aux}) - transitive use? check by hand")
    subj_gn = ("m", n or "s")

    if tense in COMPOUND and ag is not None:
        if aux == "avoir" and ag != ("m", "s"):
            info.append("agreement with a preceding direct object (avoir) - check by hand")
        if aux == "être" and n and ag[1] != n and agree != "inv":
            info.append(f"être-verb agreement '{agree}' differs from subject number - polite vous / on? check by hand")
        if agree == "inv" and aux == "être":
            info.append("pronominal participle left invariable (indirect object / COD after) - check by hand")

    if tense == "infinitif":
        return [core(base)], info
    if tense in ("infinitif-passe", "participe-passe-compose"):
        aux_word = {("être", "infinitif-passe"): "être", ("avoir", "infinitif-passe"): "avoir",
                    ("être", "participe-passe-compose"): "étant", ("avoir", "participe-passe-compose"): "ayant"}[(aux, tense)]
        default = ("m", "s")
        return [(aux_word, pp) for pp in pp_forms(default)], info
    if tense == "participe-passe":
        return [(pp,) for pp in pp_forms(("m", "s"))], info
    if tense == "futur-proche":
        return [core(strip_subject(f)) + core(base) for r in _pick(rows("aller", "indicatif", "présent"), p, n, None)[:1] for f in r["c"]], info
    if tense == "passe-recent":
        return [core(strip_subject(f)) + ("de",) + core(base) for r in _pick(rows("venir", "indicatif", "présent"), p, n, None)[:1] for f in r["c"]], info

    if tense in COMPOUND and aux != default_aux and (mood, vtense) in AUX_TENSE:
        default = subj_gn if aux == "être" else ("m", "s")
        outs = [core(strip_subject(f)) + (pp,)
                for r in _pick(rows(aux, mood, AUX_TENSE[(mood, vtense)]), p, n, None)[:1]
                for f in r["c"] for pp in pp_forms(default)]
        return outs, info

    rs = rows(verb, mood, vtense)
    if used_override(verb, mood, vtense):
        info.append(f"verbecc has no {label} of {base}; checked against the hand-filled override table")
    if tense in NO_PERSON:
        picked = rs
    else:
        g = ag[0] if ag else None
        picked = _pick(rs, p, n, g)
    if not picked:
        return [], [f"verbecc has no {label} form for person {person}"]

    outs: list[tuple[str, ...]] = []
    for r in picked:
        for f in r["c"]:
            c = core(strip_subject(f))
            if tense in COMPOUND and c:
                default = subj_gn if aux == "être" else ("m", "s")
                for pp in pp_forms(default):
                    outs.append(c[:-1] + (pp,))
            else:
                # va -> vas-y / manges-en : euphonic -s on 2s imperatives in -e/-a
                if tense == "imperatif" and person == "2s" and c and c[-1][-1] in "ea":
                    if euphonic in (False, None):
                        outs.append(c)
                    if euphonic in (True, None):
                        outs.append(c[:-1] + (c[-1] + "s",))
                else:
                    outs.append(c)
    # de-duplicate, keep order
    seen, uniq = set(), []
    for o in outs:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return uniq, info


def full_form(verb: str, tense: str, person: str | None, gender: str = "m") -> str:
    """Human-readable form with subject pronoun, e.g. 'elles ont vécu' (for recognition cards).

    gender picks il/elle (and être-verb agreement); avoir verbs never agree here.
    """
    label, mood, vtense = TENSES[tense]
    p, n = PERSONS.get(person, (None, None))
    rs = _pick(rows(verb, mood, vtense), p, n, gender)
    return rs[0]["c"][0] if rs else ""


EN_CLITIC = {"1s": "m'en ", "2s": "t'en ", "3s": "s'en ", "1p": "nous en ", "2p": "vous en ", "3p": "s'en "}


def _form(verb: str, mood: str, tense: str, p: str, n: str, maxv: int = 1) -> str:
    """First form(s) with subject pronoun; re-inserts the clitic for s'en verbs."""
    rs = _pick(rows(verb, mood, tense), p, n, "m")
    if not rs:
        return ""
    forms = rs[0]["c"][:maxv]
    if verb.startswith("s'en "):  # j'irai -> je m'en irai
        out = []
        for f in forms:
            m = SUBJECT_RE.match(f)
            subj = (m.group(0) if m else "").replace("j'", "je ")
            out.append(subj + EN_CLITIC[p + n] + f[len(m.group(0)) if m else 0:])
        forms = out
    return " / ".join(forms)


@lru_cache(maxsize=None)
def glance(verb: str) -> str:
    """HTML strip of principal parts ('temps primitifs') for the back of a card."""
    refl, base = split_reflexive(verb)
    impersonal = base in {"falloir", "pleuvoir", "neiger"}
    pp = participles(verb)[("m", "s")][0]
    pres_rows = rows(verbecc_name(base), "participe", "participe-présent")
    ppres = pres_rows[0]["c"][0] if pres_rows else "—"
    aux = auxiliary(verb)
    head = (f"<b>{verb}</b> · <i>part. prés.</i> {ppres} · <i>part. passé</i> {pp} · <i>aux.</i> {aux}")
    if impersonal:
        line2 = "présent: " + _form(verb, "indicatif", "présent", "3", "s")
        line3 = ("futur: " + _form(verb, "indicatif", "futur-simple", "3", "s")
                 + " · subj.: " + _form(verb, "subjonctif", "présent", "3", "s")
                 + " · p. simple: " + _form(verb, "indicatif", "passé-simple", "3", "s"))
    else:
        line2 = "présent: " + " · ".join(_form(verb, "indicatif", "présent", p, n, maxv=2)
                                         for p, n in (("1", "s"), ("1", "p"), ("3", "p")))
        line3 = ("futur: " + _form(verb, "indicatif", "futur-simple", "1", "s")
                 + " · subj.: " + _form(verb, "subjonctif", "présent", "1", "s")
                 + ", " + _form(verb, "subjonctif", "présent", "1", "p")
                 + " · p. simple: " + _form(verb, "indicatif", "passé-simple", "3", "s"))
    return "<br>".join([head, line2, line3])


def all_forms(verb: str) -> set[str]:
    """Every word verbecc produces for the verb (used to extend the spell-checker)."""
    _, base = split_reflexive(verb)
    words: set[str] = set()
    d = json.loads(str(_conjugator().conjugate(base, conjugate_pronouns=False)))
    for tenses in d["moods"].values():
        for rs in tenses.values():
            for r in rs:
                for f in r["c"]:
                    words.update(t.strip("'") for t in tokens(f))
    return words
