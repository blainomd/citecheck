"""Citation verification. Two independent checks, never collapsed into one score.

WHY THIS MODULE EXISTS
----------------------
A 2026 JBJS Open Access study (doi:10.2106/JBJS.OA.25.00225) prompted ChatGPT-4o mini on
the 19 AAOS hip-fracture CPG recommendations and asked for supporting evidence. Of 2,556
cited publications, only 7.9% were fabricated outright -- but of the cited publications
that DO exist in PubMed, 91.7% were given with incorrect authors, 91.5% incorrect titles
and 91.0% incorrect PMIDs. Only 1.1% overlapped the guideline's own reference list.

So "the DOI resolves" is NOT verification. The common failure is a real identifier
attached to a claim its paper never made.

A FALSE-NEGATIVE WARNING, learned while building this
-----------------------------------------------------
Extracting an article's DOI from PubMed's <ArticleIdList> can return the DOI of a linked
comment or reference rather than the article itself. Those DOIs resolve perfectly, so a
resolution-only checker marks them VERIFIED while the citation is silently wrong. Prefer
<ELocationID EIdType="doi">, then re-verify against Crossref with a title comparison.
Checkers need their own tests, including cases where the checker must fail.
"""
from __future__ import annotations
import re, json, difflib, urllib.parse, urllib.request, urllib.error
from dataclasses import dataclass, asdict
from enum import Enum

DOI_RX = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
CROSSREF = "https://api.crossref.org/works/"
TITLE_MATCH_THRESHOLD = 0.85


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"                      # resolves, and title matches the claim
    TITLE_MISMATCH = "RESOLVES_TITLE_MISMATCH" # resolves, but to a different paper
    NO_CLAIMED_TITLE = "NO_CLAIMED_TITLE"      # resolves; nothing to compare against
    UNRESOLVED = "DOES_NOT_RESOLVE"            # fabricated or malformed
    UNCHECKED = "UNCHECKED"                    # network unavailable -- never a pass


@dataclass
class Citation:
    doi: str
    claimed_title: str | None = None
    actual_title: str | None = None
    container: str | None = None
    year: int | None = None
    title_similarity: float | None = None
    verdict: Verdict = Verdict.UNCHECKED
    note: str = ""

    def passed(self) -> bool:
        return self.verdict is Verdict.VERIFIED

    def to_dict(self):
        d = asdict(self); d["verdict"] = self.verdict.value; return d


def extract_dois(text: str) -> list[str]:
    """Extract DOIs, stripping trailing punctuation that regex greedily absorbs."""
    out, seen = [], set()
    for m in DOI_RX.finditer(text or ""):
        doi = m.group().rstrip(".,;)]>'\"")
        while doi.count("(") < doi.count(")"):
            doi = doi[:-1]
        if doi.lower() not in seen:
            seen.add(doi.lower()); out.append(doi)
    return out


def normalise_title(t: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (t or "").lower())).strip()


def title_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalise_title(a), normalise_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _fetch_crossref(doi: str, timeout: float, user_agent: str) -> tuple[int | None, dict | None]:
    req = urllib.request.Request(CROSSREF + urllib.parse.quote(doi),
                                 headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, json.load(fh).get("message")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def verify_doi(doi: str, claimed_title: str | None = None, *, timeout: float = 20.0,
               user_agent: str = "orthorag-verifier/0.1") -> Citation:
    c = Citation(doi=doi, claimed_title=claimed_title)
    status, msg = _fetch_crossref(doi, timeout, user_agent)

    if status is None:
        c.verdict, c.note = Verdict.UNCHECKED, "network unavailable - not a pass"
        return c
    if status != 200 or not msg:
        c.verdict = Verdict.UNRESOLVED
        c.note = f"Crossref returned {status}; identifier is fabricated or malformed"
        return c

    c.actual_title = (msg.get("title") or [None])[0]
    c.container = (msg.get("container-title") or [None])[0]
    parts = (msg.get("issued") or {}).get("date-parts") or [[None]]
    c.year = parts[0][0] if parts and parts[0] else None

    if not claimed_title:
        c.verdict = Verdict.NO_CLAIMED_TITLE
        c.note = "resolves, but no claimed title was supplied to compare - not a pass"
        return c

    c.title_similarity = round(title_similarity(claimed_title, c.actual_title), 3)
    if c.title_similarity >= TITLE_MATCH_THRESHOLD:
        c.verdict, c.note = Verdict.VERIFIED, "resolves and title matches"
    else:
        c.verdict = Verdict.TITLE_MISMATCH
        c.note = ("resolves, but to a DIFFERENT paper than claimed - this is the most "
                  "common real-world failure mode")
    return c


def verify_all(dois_and_titles, **kw) -> list[Citation]:
    return [verify_doi(d, t, **kw) for d, t in dois_and_titles]


def summarise(cits: list[Citation]) -> dict:
    counts: dict[str, int] = {}
    for c in cits:
        counts[c.verdict.value] = counts.get(c.verdict.value, 0) + 1
    n = len(cits)
    return {"n": n, "by_verdict": counts,
            "verified_fraction": round(sum(c.passed() for c in cits) / n, 3) if n else 0.0}
