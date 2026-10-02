"""Tests that include cases where the checker MUST fail.

Run: python -m pytest tests/ -v     (or: python tests/test_all.py)
Network tests hit api.crossref.org and NCBI; they are marked and skippable.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orthorag.verify import (extract_dois, verify_doi, title_similarity, Verdict,
                             normalise_title)
from orthorag.index import BM25Index, tokenize
from orthorag.ingest import Document
from orthorag.abstain import gate, Outcome, GateConfig
from orthorag.evaluate import Item, score_item, aggregate, LOSS_MATRIX

NETWORK = os.environ.get("ORTHORAG_NETWORK_TESTS", "1") == "1"

REAL_DOI = "10.2106/JBJS.OA.24.00099"
REAL_TITLE = "ChatGPT-4 Knows Its A B C D E but Cannot Cite Its Source."
FAKE_DOI = "10.2106/JBJS.25.00412"       # confirmed 404 on 2026-10-02
WRONG_TITLE = "Outcomes of Dual-Mobility Cups in Revision Total Hip Arthroplasty"


def test_extract_dois_strips_punctuation():
    assert extract_dois("see 10.1000/abc.") == ["10.1000/abc"]
    assert extract_dois("(10.1000/xyz)") == ["10.1000/xyz"]
    assert extract_dois("none here") == []
    assert len(extract_dois("10.2106/abc and 10.2106/abc")) == 1   # dedupe
    assert extract_dois("10.1/a") == []                      # 10.<4-9 digits> required


def test_title_normalisation_and_similarity():
    assert normalise_title("The  Knee: A Study!") == "the knee a study"
    assert title_similarity("same title", "Same Title") == 1.0
    assert title_similarity("abc", "") == 0.0


def test_bm25_ranks_relevant_doc_first():
    docs = [
        Document(doc_id="1", title="Dual mobility cups in revision hip arthroplasty",
                 abstract="dislocation after revision total hip arthroplasty",
                 publication_types=["Randomized Controlled Trial"]),
        Document(doc_id="2", title="Distal radius fracture fixation",
                 abstract="volar plating of the wrist", publication_types=["Case Reports"]),
    ]
    idx = BM25Index().add(docs)
    assert len(idx) == 2
    hits = idx.search("dislocation revision hip arthroplasty", top_k=2)
    assert hits and hits[0].doc_id == "1"
    assert hits[0].evidence_level == "I"


def test_evidence_level_proxy():
    assert Document(doc_id="x", title="t", publication_types=["Case Reports"]).evidence_level == "IV"
    assert Document(doc_id="x", title="t", publication_types=["Editorial"]).evidence_level == "V"
    assert Document(doc_id="x", title="t", publication_types=[]).evidence_level == "unknown"


def test_gate_abstains_on_no_hits():
    assert gate([]).outcome is Outcome.INSUFFICIENT_EVIDENCE


def test_gate_abstains_on_level_v_for_high_stakes():
    class H:
        def __init__(s, sc, lv): s.score, s.evidence_level = sc, lv
    hits = [H(99.0, "V"), H(50.0, "V")]
    g = gate(hits, high_stakes=True)
    assert g.outcome is Outcome.INSUFFICIENT_EVIDENCE
    assert "Level V" in g.reason


def test_gate_answers_on_strong_level_i():
    class H:
        def __init__(s, sc, lv): s.score, s.evidence_level = sc, lv
    g = gate([H(99.0, "I"), H(20.0, "II")], high_stakes=True)
    assert g.outcome is Outcome.ANSWER


def test_loss_matrix_pays_equally_for_yes_and_no():
    """The core design claim of the harness, asserted as a test."""
    assert LOSS_MATRIX[("operate", "operate")] == LOSS_MATRIX[("no_operate", "no_operate")]
    # operating when you should not is worse than the reverse
    assert LOSS_MATRIX[("no_operate", "operate")] < LOSS_MATRIX[("operate", "no_operate")]
    # over-abstention is penalised, but far less than over-commitment
    assert LOSS_MATRIX[("operate", "insufficient")] > LOSS_MATRIX[("insufficient", "operate")]


def test_red_flag_miss_is_not_averaged_away():
    it = Item(item_id="i1", question="q", reference_label="no_operate",
              red_flags=["active infection"])
    r = score_item(it, "no_operate", mentioned_text="patient is well")
    assert r.red_flags_missed == ["active infection"]
    agg = aggregate([r])
    assert agg["red_flag_failure"] is True
    assert agg["net_judgment_benefit"] == 1.0   # headline looks perfect...
    assert agg["red_flags_missed_total"] == 1   # ...which is why this is reported beside it


def test_over_commitment_rate_computed():
    items = [Item(item_id=f"i{i}", question="q", reference_label="insufficient") for i in range(4)]
    rs = [score_item(items[0], "operate"), score_item(items[1], "operate"),
          score_item(items[2], "insufficient"), score_item(items[3], "insufficient")]
    assert aggregate(rs)["over_commitment_rate"] == 0.5


# ---- network tests: the four verdicts, against live Crossref ----

def test_real_doi_with_correct_title_verifies():
    if not NETWORK: return
    c = verify_doi(REAL_DOI, REAL_TITLE)
    assert c.verdict is Verdict.VERIFIED, c.to_dict()
    assert c.title_similarity >= 0.85


def test_real_doi_with_wrong_title_is_mismatch():
    """THE IMPORTANT ONE. A resolution-only checker passes this; it must not."""
    if not NETWORK: return
    c = verify_doi(REAL_DOI, WRONG_TITLE)
    assert c.verdict is Verdict.TITLE_MISMATCH, c.to_dict()


def test_fabricated_doi_does_not_resolve():
    if not NETWORK: return
    assert verify_doi(FAKE_DOI, "anything").verdict is Verdict.UNRESOLVED


def test_missing_claimed_title_is_not_a_pass():
    if not NETWORK: return
    c = verify_doi(REAL_DOI, None)
    assert c.verdict is Verdict.NO_CLAIMED_TITLE
    assert not c.passed()


if __name__ == "__main__":
    import traceback
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for name, fn in fns:
        try:
            fn(); print(f"PASS {name}")
        except Exception:
            bad += 1; print(f"FAIL {name}"); traceback.print_exc()
    print(f"\n{len(fns)-bad}/{len(fns)} passed")
    sys.exit(1 if bad else 0)
