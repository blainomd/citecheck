"""Corpus ingestion. Two sources, one interface.

LICENSING -- READ THIS FIRST
----------------------------
`PubMedSource` and `PMCOpenAccessSource` use public NCBI E-utilities and the PMC Open
Access subset. Those are free to query and redistribute within the terms NCBI states.

`LicensedCorpusSource` is a stub. Full text of JBJS, CORR, AJSM and similar is
copyrighted and paywalled; indexing it requires a text-and-data-mining agreement with
the publisher (Wolters Kluwer for JBJS). Do not point this at scraped PDFs. If JBJS or
OREF are partners in an evaluation, they are the parties who can supply a licensed dump
-- drop it in as JSONL matching `Document` and everything downstream works unchanged.

As of 2 October 2026 the legally ingestible orthopaedic corpus is substantial:
  570,815  PubMed records matching an orthopaedic term set
  179,712  of those with full text in PMC
   15,987  randomised controlled trials
   14,169  systematic reviews / meta-analyses
(counts from E-utilities esearch; reproduce with `python -m orthorag.ingest --counts`)
"""
from __future__ import annotations
import json, time, urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

ORTHO_TERMS = ('(orthopedics[mh] OR orthopaedics[tiab] OR orthopedics[tiab] OR '
               'arthroplasty[tiab] OR fracture*[tiab] OR "rotator cuff"[tiab] OR '
               'meniscus[tiab] OR "spinal fusion"[tiab] OR arthroscopy[tiab] OR '
               '"joint replacement"[tiab])')

LEVEL_FROM_PTYPE = {
    "Randomized Controlled Trial": "I",
    "Meta-Analysis": "I",
    "Systematic Review": "I",
    "Clinical Trial": "II",
    "Comparative Study": "III",
    "Case Reports": "IV",
    "Review": "V",
    "Editorial": "V",
    "Comment": "V",
}


@dataclass
class Document:
    doc_id: str
    title: str
    abstract: str = ""
    journal: str = ""
    year: int | None = None
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    publication_types: list[str] = field(default_factory=list)
    mesh: list[str] = field(default_factory=list)
    full_text: str = ""
    source: str = "pubmed"

    @property
    def evidence_level(self) -> str:
        """Coarse Level-of-Evidence proxy from PubMed publication types.

        This is a PROXY, not JBJS's assigned Level. JBJS prints an explicit Level on
        clinical articles; if a licensed corpus supplies it, prefer that field and treat
        this only as a fallback. Report which one was used.
        """
        for pt in self.publication_types:
            if pt in LEVEL_FROM_PTYPE:
                return LEVEL_FROM_PTYPE[pt]
        return "unknown"

    def text_for_index(self) -> str:
        return " ".join(filter(None, [self.title, self.abstract, self.full_text]))

    def to_dict(self):
        d = asdict(self); d["evidence_level"] = self.evidence_level; return d


def _get(url: str, timeout: float = 60.0, ua: str = "orthorag-ingest/0.1") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return fh.read()


def _eutils(path: str, **params) -> bytes:
    params.setdefault("retmode", "json" if path.startswith("esearch") else "xml")
    return _get(EUTILS + path + "?" + urllib.parse.urlencode(params))


def esearch_count(term: str) -> int:
    r = json.loads(_eutils("esearch.fcgi", db="pubmed", term=term, retmax=0))
    return int(r["esearchresult"]["count"])


def esearch(term: str, retmax: int = 200, sort: str = "relevance") -> list[str]:
    r = json.loads(_eutils("esearch.fcgi", db="pubmed", term=term, retmax=retmax, sort=sort))
    return r["esearchresult"]["idlist"]


def _article_doi(art: ET.Element) -> str:
    """Prefer ELocationID. See the false-negative warning in verify.py -- ArticleIdList
    can carry DOIs belonging to linked comments, which resolve but are the wrong paper."""
    for e in art.findall(".//ELocationID"):
        if e.get("EIdType") == "doi" and e.text:
            return e.text.strip()
    for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi" and aid.text:
            return aid.text.strip()
    return ""


def _itertext(node) -> str:
    return "".join(node.itertext()) if node is not None else ""


def efetch(pmids: list[str], batch: int = 150, pause: float = 0.34) -> list[Document]:
    docs: list[Document] = []
    for i in range(0, len(pmids), batch):
        chunk = pmids[i:i + batch]
        xml = _eutils("efetch.fcgi", db="pubmed", id=",".join(chunk), retmode="xml")
        for art in ET.fromstring(xml).findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID") or ""
            year = art.findtext(".//JournalIssue/PubDate/Year")
            pmcid = ""
            for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if aid.get("IdType") == "pmc" and aid.text:
                    pmcid = aid.text.strip()
            docs.append(Document(
                doc_id=f"pmid:{pmid}", pmid=pmid, pmcid=pmcid,
                title=_itertext(art.find(".//ArticleTitle")),
                abstract=" ".join(_itertext(x) for x in art.findall(".//Abstract/AbstractText")),
                journal=art.findtext(".//Journal/ISOAbbreviation") or "",
                year=int(year) if (year or "").isdigit() else None,
                doi=_article_doi(art),
                publication_types=[p.text for p in art.findall(".//PublicationType") if p.text],
                mesh=[m.text for m in art.findall(".//MeshHeading/DescriptorName") if m.text],
            ))
        if i + batch < len(pmids):
            time.sleep(pause)
    return docs


def harvest(term: str = ORTHO_TERMS, retmax: int = 500, **kw) -> list[Document]:
    return efetch(esearch(term, retmax=retmax), **kw)


def write_jsonl(docs: list[Document], path: str) -> int:
    with open(path, "w") as fh:
        for d in docs:
            fh.write(json.dumps(d.to_dict()) + "\n")
    return len(docs)


def read_jsonl(path: str) -> list[Document]:
    out = []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            rec.pop("evidence_level", None)
            out.append(Document(**rec))
    return out


class LicensedCorpusSource:
    """Drop-in for a publisher-supplied dump. Expects JSONL matching Document fields.

    Required by the licence, and by honesty: record the agreement under which the corpus
    was supplied, and keep `source` set to the publisher so provenance survives into
    every answer the system returns.
    """

    def __init__(self, jsonl_path: str, publisher: str, agreement_ref: str):
        if not publisher or not agreement_ref:
            raise ValueError(
                "A licensed corpus requires both `publisher` and `agreement_ref`. "
                "If you do not have a text-and-data-mining agreement, you cannot index "
                "this content -- use PubMed abstracts and the PMC Open Access subset."
            )
        self.jsonl_path, self.publisher, self.agreement_ref = jsonl_path, publisher, agreement_ref

    def load(self) -> list[Document]:
        docs = read_jsonl(self.jsonl_path)
        for d in docs:
            d.source = self.publisher
        return docs


if __name__ == "__main__":
    import sys
    if "--counts" in sys.argv:
        for label, q in [
            ("ortho records", ORTHO_TERMS),
            ("in PMC", f"{ORTHO_TERMS} AND pubmed pmc[sb]"),
            ("RCTs", f"{ORTHO_TERMS} AND randomized controlled trial[pt]"),
            ("SR/meta", f"{ORTHO_TERMS} AND (systematic review[pt] OR meta-analysis[pt])"),
        ]:
            print(f"{label:16s} {esearch_count(q):>9,}")
            time.sleep(0.34)
