"""Independent calculators for worked-problem cards.

A card may declare the problem it poses and the result it claims:

    calc:
      kind: cross
      p1: "XH/Xh"
      p2: "XH/Y"
      ask: probability
      of: "h"            # phenotype key (or a label from `labels`)
      given: male
      result: "1/2"

verify.py recomputes the result from the inputs alone, fails the card if the
declared `result` differs, and fails it if the answer text doesn't contain
the result. So a typo in a ratio or a mistranscribed codon cannot slip through.

Kinds
  complement   strand          "5'-ATGC-3'"         → "3'-TACG-5'"
  transcribe   template        "3'-TACGGT-5'"       → "5'-AUGCCA-3'"   (mRNA)
  translate    mrna            "AUGGCUUAA"          → "Met-Ala"        (stops at a stop codon)
  cross        p1, p2, mode    genotypes like "A/a B/b", "XH/Xh", "XH/Y", "IA/i", "CR/CW"
               mode: complete (default) | incomplete | codominant | abo
               ask: phenotype-ratio | sexed-phenotype-ratio (keys like "h male") | genotype-ratio |
                    probability (+ of, optional given: male | female)
               labels: {phenotype key: name}  (optional; result may use the names)
  sav          shape cube (side) | cuboid (dims) | sphere (r)  → "3:1"
  magnification  two of image_mm, actual_um, magnification → the third
  field        fov_um, count  → size of one object in µm (fov_um / count)
  lincoln      marked, caught, recaptured → population estimate
  quadrat      counts (per quadrat), quadrat_m2, area_m2 → population estimate
  rate         cases, population, per → cases per `per` people
  halflife     half_life (years) and remaining (fraction left, e.g. 0.25) → age in years
  growth       start, doubling_min, time_min → number of cells (binary fission, no deaths)
  chargaff     percentage of one base (e.g. A: 30) and ask (another base) → its percentage
  allele-frequency  hom_dom, het, hom_rec (numbers of individuals), allele: dom | rec → frequency
  percent-change    initial, final → percentage change (negative for a decrease)
"""
from __future__ import annotations

import math
import re
from collections import Counter
from fractions import Fraction
from itertools import product

# --------------------------------------------------------------------------- nucleic acids

_PAIR_DNA = {"A": "T", "T": "A", "G": "C", "C": "G"}
_PAIR_RNA = {"A": "U", "T": "A", "U": "A", "G": "C", "C": "G"}

# NCBI translation table 1 (the standard code); base order T C A G.
_AA = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
_THREE = {"A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln", "E": "Glu", "G": "Gly",
          "H": "His", "I": "Ile", "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro", "S": "Ser",
          "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val", "*": "Stop"}
CODON_TABLE = {a + b + c: _THREE[_AA[16 * i + 4 * j + k]]
               for i, a in enumerate("UCAG") for j, b in enumerate("UCAG") for k, c in enumerate("UCAG")}


def _strand(s: str) -> tuple[str | None, str]:
    """Split "5'-ATGC-3'" into (orientation, bases)."""
    s = s.replace("’", "'").replace(" ", "")
    m = re.fullmatch(r"([35])'-?([ACGTU]+)-?([35])'", s)
    if m:
        if m.group(1) == m.group(3):
            raise ValueError(f"strand {s!r}: both ends are {m.group(1)}'")
        return m.group(1), m.group(2)
    if not re.fullmatch(r"[ACGTU]+", s):
        raise ValueError(f"not a nucleotide sequence: {s!r}")
    return None, s


def _label(end: str | None, bases: str) -> str:
    if end is None:
        return bases
    other = "3" if end == "5" else "5"
    return f"{end}'-{bases}-{other}'"


def complement(strand: str) -> str:
    end, b = _strand(strand)
    if "U" in b:
        raise ValueError("complement expects DNA")
    return _label(None if end is None else ("3" if end == "5" else "5"), "".join(_PAIR_DNA[x] for x in b))


def transcribe(template: str) -> str:
    end, b = _strand(template)
    if "U" in b:
        raise ValueError("template must be DNA")
    return _label(None if end is None else ("3" if end == "5" else "5"), "".join(_PAIR_RNA[x] for x in b))


def translate(mrna: str) -> str:
    end, b = _strand(mrna)
    if end == "3":
        raise ValueError("write the mRNA 5'→3' to translate it")
    if "T" in b:
        raise ValueError("mRNA contains T")
    out = []
    for i in range(0, len(b) - len(b) % 3, 3):
        aa = CODON_TABLE[b[i:i + 3]]
        if aa == "Stop":
            break
        out.append(aa)
    return "-".join(out)


# --------------------------------------------------------------------------- crosses

def _parse_genotype(g: str) -> list[tuple[str, str]]:
    loci = []
    for locus in g.split():
        parts = locus.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"genotype {g!r}: write each locus as allele/allele, e.g. A/a or XH/Y")
        loci.append((parts[0], parts[1]))
    return loci


def _is_male(geno: list[tuple[str, str]]) -> bool:
    return any("Y" in pair for pair in geno)


def _allele_letter(a: str) -> str | None:
    """'XH' → 'H', 'Y' → None, 'A' → 'A'."""
    if a == "Y":
        return None
    return a[1:] if a.startswith("X") and len(a) > 1 else a


def _locus_phenotype(pair: tuple[str, str], mode: str) -> str:
    if mode == "abo":
        s = set(pair)
        if s == {"IA", "IB"}:
            return "AB"
        if "IA" in s:
            return "A"
        if "IB" in s:
            return "B"
        if s == {"i"}:
            return "O"
        raise ValueError(f"ABO alleles must be IA, IB or i, got {pair}")
    letters = [x for x in (_allele_letter(a) for a in pair) if x is not None]
    if mode in ("incomplete", "codominant"):
        return "/".join(sorted(letters))
    if mode != "complete":
        raise ValueError(f"unknown mode {mode!r}")
    dom = [x for x in letters if x[0].isupper()]
    return dom[0] if dom else letters[0]


def _gametes(geno: list[tuple[str, str]]) -> Counter:
    g = Counter()
    for combo in product(*geno):           # one allele from each locus (independent assortment)
        g[combo] += 1
    return g


def _canon(geno: tuple[tuple[str, str], ...]) -> str:
    def key(a: str) -> tuple:
        return (a == "Y", _allele_letter(a) is not None and not _allele_letter(a)[0].isupper(), a)
    return " ".join("/".join(sorted(pair, key=key)) for pair in geno)


def cross_offspring(p1: str, p2: str) -> dict[str, Fraction]:
    g1, g2 = _gametes(_parse_genotype(p1)), _gametes(_parse_genotype(p2))
    n1, n2 = sum(g1.values()), sum(g2.values())
    out: Counter = Counter()
    for (a, ca), (b, cb) in product(g1.items(), g2.items()):
        child = tuple(tuple((x, y)) for x, y in zip(a, b))
        out[_canon(child)] += Fraction(ca * cb, n1 * n2)
    return dict(out)


def phenotype_of(genotype: str, mode: str) -> str:
    return " ".join(_locus_phenotype(p, mode) for p in _parse_genotype(genotype))


def _ratio(d: dict[str, Fraction]) -> dict[str, int]:
    den = math.lcm(*(f.denominator for f in d.values()))
    ints = {k: int(v * den) for k, v in d.items()}
    g = math.gcd(*ints.values())
    return {k: v // g for k, v in ints.items()}


def cross(spec: dict) -> object:
    mode = spec.get("mode", "complete")
    labels = spec.get("labels") or {}
    offspring = cross_offspring(spec["p1"], spec["p2"])
    ask = spec.get("ask", "phenotype-ratio")
    if ask == "genotype-ratio":
        return _ratio(offspring)
    pheno: dict[str, Fraction] = Counter()
    sexed: dict[tuple[str, str], Fraction] = Counter()
    for g, f in offspring.items():
        p = phenotype_of(g, mode)
        p = labels.get(p, p)
        pheno[p] += f
        sexed[(p, "male" if _is_male(_parse_genotype(g)) else "female")] += f
    if ask == "phenotype-ratio":
        return _ratio(pheno)
    if ask == "sexed-phenotype-ratio":
        return _ratio({f"{p} {s}": v for (p, s), v in sexed.items()})
    if ask == "probability":
        target, given = spec["of"], spec.get("given")
        if given in ("male", "female"):
            num = sexed.get((target, given), Fraction(0))
            den = sum(v for (p, s), v in sexed.items() if s == given)
        elif given:
            raise ValueError("given must be male or female")
        else:
            num, den = pheno.get(target, Fraction(0)), Fraction(1)
        if target not in pheno:
            raise ValueError(f"phenotype {target!r} never occurs; phenotypes are {sorted(pheno)}")
        return num / den
    raise ValueError(f"unknown ask {ask!r}")


# --------------------------------------------------------------------------- numbers

def _num(x: float) -> str:
    x = round(x, 2)
    return str(int(x)) if x == int(x) else f"{x:g}"


def sav(spec: dict) -> str:
    shape = spec["shape"]
    if shape == "cube":
        s = spec["side"]
        sa, v = 6 * s * s, s ** 3
    elif shape == "cuboid":
        a, b, c = spec["dims"]
        sa, v = 2 * (a * b + b * c + a * c), a * b * c
    elif shape == "sphere":
        r = spec["r"]
        sa, v = 4 * math.pi * r * r, 4 / 3 * math.pi * r ** 3
    else:
        raise ValueError(f"unknown shape {shape!r}")
    return f"{_num(sa / v)}:1"


def magnification(spec: dict) -> str:
    have = {k for k in ("image_mm", "actual_um", "magnification") if k in spec}
    if have == {"image_mm", "actual_um"}:
        return _num(spec["image_mm"] * 1000 / spec["actual_um"])
    if have == {"image_mm", "magnification"}:
        return _num(spec["image_mm"] * 1000 / spec["magnification"])
    if have == {"actual_um", "magnification"}:
        return _num(spec["actual_um"] * spec["magnification"] / 1000)
    raise ValueError("give exactly two of image_mm, actual_um, magnification")


def calculate(spec: dict) -> object:
    kind = spec["kind"]
    if kind == "complement":
        return complement(spec["strand"])
    if kind == "transcribe":
        return transcribe(spec["template"])
    if kind == "translate":
        return translate(spec["mrna"])
    if kind == "cross":
        return cross(spec)
    if kind == "sav":
        return sav(spec)
    if kind == "magnification":
        return magnification(spec)
    if kind == "field":
        return _num(spec["fov_um"] / spec["count"])
    if kind == "lincoln":
        return _num(spec["marked"] * spec["caught"] / spec["recaptured"])
    if kind == "quadrat":
        counts = spec["counts"]
        return _num(sum(counts) / len(counts) / spec["quadrat_m2"] * spec["area_m2"])
    if kind == "growth":
        return _num(spec["start"] * 2 ** (spec["time_min"] / spec["doubling_min"]))
    if kind == "chargaff":
        given = [b for b in "ATGC" if b in spec]
        if len(given) != 1:
            raise ValueError("give the percentage of exactly one base")
        b, pct = given[0], spec[given[0]]
        same = {"A": "T", "T": "A", "G": "C", "C": "G"}
        ask = spec["ask"]
        return _num(pct if ask in (b, same[b]) else (100 - 2 * pct) / 2)
    if kind == "allele-frequency":
        n = spec["hom_dom"] + spec["het"] + spec["hom_rec"]
        rec = (spec["het"] + 2 * spec["hom_rec"]) / (2 * n)
        return _num(rec if spec["allele"] == "rec" else 1 - rec)
    if kind == "percent-change":
        return _num((spec["final"] - spec["initial"]) / spec["initial"] * 100)
    if kind == "halflife":
        return _num(spec["half_life"] * math.log2(1 / spec["remaining"]))
    if kind == "rate":
        return _num(spec["cases"] / spec["population"] * spec["per"])
    raise ValueError(f"unknown calc kind {kind!r}")


# --------------------------------------------------------------------------- comparing with the card

def normalise_result(r: object) -> object:
    """Bring a declared result (from YAML) into the form `calculate` returns."""
    if isinstance(r, dict):
        return {str(k): int(v) for k, v in r.items()}
    if isinstance(r, (int, float)):
        return _num(r)
    s = str(r).strip()
    if re.fullmatch(r"\d+/\d+", s):
        return Fraction(s)
    return s


def answer_forms(result: object) -> list[str]:
    """Strings, any one of which must appear in the answer text."""
    if isinstance(result, dict):
        return [":".join(str(v) for v in result.values())]
    if isinstance(result, Fraction):
        forms = [f"{result.numerator}/{result.denominator}"]
        pct = result * 100
        forms.append(f"{_num(float(pct))}%")
        if result in (0, 1):
            forms.append(str(int(result)))
        return forms
    return [str(result)]


def answer_contains(answer: str, result: object) -> bool:
    a = answer.replace("’", "'").replace("\u2009", "").replace("\u202f", "").replace("−", "-")
    a = re.sub(r"(?<=\d)[, \u00a0](?=\d{3}\b)", "", a)  # 12,000 / 12 000 → 12000
    a = re.sub(r"\s*:\s*", ":", a)                      # 3 : 1 → 3:1
    a = re.sub(r"\s*%", "%", a)
    a = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "/", a)
    return any(f in a for f in answer_forms(result))
