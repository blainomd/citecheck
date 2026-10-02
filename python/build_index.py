"""Build the retrieval index from live PubMed. Fetch and index are separate steps so the
fetch can be cached and the index rebuilt offline.

    python build_index.py --retmax 2000
    python build_index.py --from-jsonl data/corpus.jsonl
"""
from __future__ import annotations
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from orthorag.ingest import harvest, read_jsonl, write_jsonl, ORTHO_TERMS
from orthorag.index import BM25Index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retmax", type=int, default=500)
    ap.add_argument("--term", default=ORTHO_TERMS)
    ap.add_argument("--jsonl", default="data/corpus.jsonl")
    ap.add_argument("--index", default="data/ortho.index")
    ap.add_argument("--from-jsonl", action="store_true")
    a = ap.parse_args()
    os.makedirs("data", exist_ok=True)

    if a.from_jsonl:
        docs = read_jsonl(a.jsonl)
        print(f"loaded {len(docs)} docs from {a.jsonl}")
    else:
        t0 = time.time()
        docs = harvest(a.term, retmax=a.retmax)
        print(f"harvested {len(docs)} docs in {time.time()-t0:.1f}s")
        write_jsonl(docs, a.jsonl)

    idx = BM25Index().add(docs)
    idx.save(a.index)
    lv = {}
    for d in docs:
        lv[d.evidence_level] = lv.get(d.evidence_level, 0) + 1
    with_doi = sum(1 for d in docs if d.doi)
    print(f"indexed {len(idx)} docs -> {a.index}")
    print(f"with DOI: {with_doi}/{len(docs)}")
    print("evidence-level proxy:", dict(sorted(lv.items())))


if __name__ == "__main__":
    main()
