"""BM25 retrieval over the corpus. Pure stdlib + numpy, no service dependency.

BM25 is the deliberate default: it is strong on the precise terminology that dominates
orthopaedic queries (eponyms, implant names, classification systems), it is inspectable
when a retrieval looks wrong, and it needs no API key or GPU -- so an evaluation can be
reproduced by a reviewer. Dense retrieval is a drop-in upgrade via `HybridIndex`, and
should be justified by a measured gain on the eval set, not assumed.
"""
from __future__ import annotations
import math, re, pickle
from collections import Counter
from dataclasses import dataclass

TOKEN_RX = re.compile(r"[a-z0-9][a-z0-9\-']*")
STOP = set("""a an the and or of in for to with on by is are was were be been being as at from
that this these those we our it its which not no than then they their he she his her you your
i if may might can could should would will shall do does did done have has had having but
also such into over under between during about after before above below more most other some
any each both few many own same so too very s t""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RX.findall((text or "").lower()) if t not in STOP and len(t) > 1]


@dataclass
class Hit:
    doc_id: str
    score: float
    title: str
    journal: str
    year: int | None
    doi: str
    evidence_level: str
    snippet: str


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list = []
        self.by_id: dict = {}
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._len: list[int] = []
        self._avg = 0.0

    def add(self, documents) -> "BM25Index":
        for d in documents:
            toks = tokenize(d.text_for_index())
            if not toks:
                continue
            tf = Counter(toks)
            self.docs.append(d); self.by_id[d.doc_id] = d
            self._tf.append(tf); self._len.append(len(toks))
            for term in tf:
                self._df[term] += 1
        self._avg = (sum(self._len) / len(self._len)) if self._len else 0.0
        return self

    def __len__(self):
        return len(self.docs)

    def _idf(self, term: str) -> float:
        n, df = len(self.docs), self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 8) -> list[Hit]:
        q = tokenize(query)
        if not q or not self.docs:
            return []
        scored = []
        for i, tf in enumerate(self._tf):
            s, dl = 0.0, self._len[i]
            for term in q:
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avg or 1))
                s += self._idf(term) * f * (self.k1 + 1) / denom
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        out = []
        for s, i in scored[:top_k]:
            d = self.docs[i]
            out.append(Hit(doc_id=d.doc_id, score=round(s, 4), title=d.title,
                           journal=d.journal, year=d.year, doi=d.doi,
                           evidence_level=d.evidence_level,
                           snippet=self._snippet(d.text_for_index(), q)))
        return out

    @staticmethod
    def _snippet(text: str, q: list[str], width: int = 320) -> str:
        low = text.lower()
        pos = min((low.find(t) for t in q if low.find(t) >= 0), default=-1)
        if pos < 0:
            return text[:width]
        start = max(0, pos - width // 3)
        return ("..." if start else "") + text[start:start + width].strip() + "..."

    def save(self, path: str):
        with open(path, "wb") as fh:
            pickle.dump(self, fh)

    @staticmethod
    def load(path: str) -> "BM25Index":
        with open(path, "rb") as fh:
            return pickle.load(fh)


class HybridIndex(BM25Index):
    """Hook for dense retrieval. Left unimplemented on purpose: adding an embedding model
    is a measurable change, so implement it alongside an eval run that shows it helps."""

    def search(self, query: str, top_k: int = 8, alpha: float = 1.0) -> list[Hit]:
        return super().search(query, top_k)
