"""End-to-end: built index -> retrieve -> gate -> verify -> HTTP API.

Run: python tests/test_e2e.py     (requires data/ortho.index; see build_index.py)
"""
import json, os, sys, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orthorag.index import BM25Index
from orthorag.ingest import Document
from orthorag.rag import OrthoRAG, grounded_prompt
from orthorag.abstain import Outcome
from orthorag.verify import extract_dois, verify_doi, Verdict

CHECKS = []
def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))

# Prefer a real harvested index when one exists; otherwise fall back to the synthetic
# fixture corpus so a fresh clone can run the suite offline with no harvest step.
if os.path.exists("data/ortho.index"):
    idx = BM25Index.load("data/ortho.index")
    corpus_kind = "harvested"
else:
    from orthorag.ingest import read_jsonl
    idx = BM25Index().add(read_jsonl("tests/fixtures/corpus.jsonl"))
    corpus_kind = "synthetic fixture"
check("index loaded non-empty", len(idx) > 0, f"{len(idx)} docs ({corpus_kind})")

rag = OrthoRAG(idx, generator=None, verify=False)

# 1. Retrieval returns something for an in-domain query
a = rag.answer("total knee arthroplasty outcomes", top_k=8)
check("in-domain query retrieves hits", len(a.hits) > 0, f"{len(a.hits)} hits")

# 2. Out-of-domain query must abstain, not improvise
b = rag.answer("quantum chromodynamics lattice gauge theory", top_k=8)
check("out-of-domain abstains", b.outcome != Outcome.ANSWER.value, b.outcome)
check("abstention explains itself", "Not answering" in (b.text or ""), (b.text or "")[:60])

# 3. High-stakes raises the bar vs the same query non-high-stakes
lo = rag.answer("rotator cuff repair", top_k=8, high_stakes=False)
hi = rag.answer("rotator cuff repair", top_k=8, high_stakes=True)
order = {"ANSWER": 0, "AMBIGUOUS": 1, "INSUFFICIENT_EVIDENCE": 2}
check("high_stakes never more permissive",
      order[hi.outcome] >= order[lo.outcome], f"{lo.outcome} -> {hi.outcome}")

# 4. Level V only must abstain under high stakes.
# The score floor is lowered to 0 here ON PURPOSE: with it in place this test passed
# because BM25 scores on a 2-doc corpus are tiny, i.e. it passed without ever reaching
# the evidence-level gate. Isolate the mechanism under test, then assert on the reason.
from orthorag.abstain import GateConfig
loose = GateConfig(min_top_score=0.0, min_mean_score=0.0, disagreement_margin=0.0)
synth = BM25Index().add([
    Document(doc_id="v1", title="Opinion on cartilage repair", abstract="cartilage repair opinion piece",
             publication_types=["Editorial"], doi=""),
    Document(doc_id="v2", title="Commentary on cartilage repair", abstract="cartilage repair commentary",
             publication_types=["Editorial"], doi=""),
])
r4 = OrthoRAG(synth, verify=False, config=loose).answer("cartilage repair", high_stakes=True)
check("level V refused for high stakes", r4.outcome == "INSUFFICIENT_EVIDENCE", r4.gate_reason)
check("...and refused BECAUSE of the level, not the score",
      "Level V" in r4.gate_reason, r4.gate_reason)

# 4b. Same corpus, same query, Level I instead -> must be allowed through the level gate
synth_i = BM25Index().add([
    Document(doc_id="i1", title="Trial of cartilage repair", abstract="cartilage repair randomized trial",
             publication_types=["Randomized Controlled Trial"], doi=""),
    Document(doc_id="i2", title="Cohort of cartilage repair", abstract="cartilage repair prospective cohort",
             publication_types=["Clinical Trial"], doi=""),
])
r4b = OrthoRAG(synth_i, verify=False, config=loose).answer("cartilage repair", high_stakes=True)
check("level I passes the level gate", r4b.outcome == "ANSWER", r4b.gate_reason)

# 5. A title-mismatched citation disqualifies the answer.
# Same correction as above: with the default score floor this passed on "support too
# weak" and never exercised the citation check. Loosen the floor, force Level I so the
# level gate cannot fire either, and assert the refusal names the citation problem.
mism = BM25Index().add([
    Document(doc_id="m1", title="Dual mobility cups in revision hip arthroplasty",
             abstract="dislocation revision total hip arthroplasty dual mobility",
             publication_types=["Randomized Controlled Trial"], doi="10.2106/JBJS.OA.24.00099"),
    Document(doc_id="m2", title="Dual mobility cups revisited",
             abstract="dislocation revision total hip arthroplasty dual mobility bearing",
             publication_types=["Meta-Analysis"], doi="10.2106/JBJS.OA.24.00099"),
])
r5 = OrthoRAG(mism, verify=True, config=loose).answer("dual mobility dislocation revision",
                                                      high_stakes=False)
check("title mismatch blocks answer", r5.outcome != "ANSWER", r5.gate_reason[:90])
check("...and blocked BECAUSE of the citation, not the score",
      "different paper" in r5.gate_reason, r5.gate_reason[:90])

# 6. Verification verdicts, live
c_ok = verify_doi("10.2106/JBJS.OA.24.00099", "ChatGPT-4 Knows Its A B C D E but Cannot Cite Its Source.")
c_bad = verify_doi("10.2106/JBJS.OA.24.00099", "Outcomes of Dual-Mobility Cups in Revision Total Hip Arthroplasty")
c_404 = verify_doi("10.2106/JBJS.25.00412", "anything")
check("verify VERIFIED", c_ok.verdict is Verdict.VERIFIED, str(c_ok.title_similarity))
check("verify TITLE_MISMATCH", c_bad.verdict is Verdict.TITLE_MISMATCH, str(c_bad.title_similarity))
check("verify UNRESOLVED", c_404.verdict is Verdict.UNRESOLVED, c_404.note[:40])

# 7. grounded_prompt tags every source and demands refusal option
p = grounded_prompt("q", a.hits[:3], None)
check("prompt tags sources", "[S1]" in p and "[S3]" in p)
check("prompt permits refusal", "INSUFFICIENT EVIDENCE" in p)

# 8. HTTP API -- exercised in-process.
# NOTE: binding a listening socket is not permitted in the build sandbox, so the handler
# is driven directly through BytesIO rather than over a real TCP connection. This covers
# routing, JSON parsing, status codes and payload shape; it does not cover socket setup.
import io, json as _json
import server as srv
from orthorag.rag import OrthoRAG as _RAG

srv.STATE["rag"] = _RAG(idx, verify=False)
srv.STATE["prefix"] = "/docsf"


class _FakeSocket:
    def getsockname(self): return ("127.0.0.1", 0)
    def getpeername(self): return ("127.0.0.1", 0)
    def makefile(self, *a, **k): return io.BytesIO()
    def sendall(self, *a, **k): pass
    def close(self): pass


def call(method, path, body=None):
    payload = b"" if body is None else _json.dumps(body).encode()
    req = f"{method} {path} HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
    if body is not None:
        req += f"Content-Length: {len(payload)}\r\n"
    raw = req.encode() + b"\r\n" + payload

    class H(srv.Handler):
        def __init__(self):
            self.rfile = io.BytesIO(raw)
            self.wfile = io.BytesIO()
            self.connection = _FakeSocket()
            self.client_address = ("127.0.0.1", 0)
            self.request = self.connection
            self.server = None
            self.handle_one_request()

        def log_message(self, *a, **k): pass

    h = H()
    out = h.wfile.getvalue()
    status = int(out.split(b" ")[1]) if out.startswith(b"HTTP/") else 0
    _, _, bodyb = out.partition(b"\r\n\r\n")
    try:
        parsed = _json.loads(bodyb) if bodyb else None
    except Exception:
        parsed = None
    return status, parsed


st, h = call("GET", "/docsf/api/health")
check("health 200 + doc count", st == 200 and h and h.get("documents") == len(idx), f"{st} {h}")

st, q = call("POST", "/docsf/api/query", {"q": "hip fracture fixation"})
check("api/query 200 with outcome+hits",
      st == 200 and q and "outcome" in q and isinstance(q.get("hits"), list),
      f"{st} {q.get('outcome') if q else None}")

st, v = call("POST", "/docsf/api/verify",
             {"text": "see 10.2106/JBJS.25.00412 and 10.2106/JBJS.OA.24.00099"})
check("api/verify finds both DOIs", st == 200 and v and v["summary"]["n"] == 2,
      f"{st} {v['summary'] if v else None}")
check("api/verify flags the fabricated DOI",
      bool(v) and any(c["verdict"] == "DOES_NOT_RESOLVE" for c in v["citations"]),
      str({c["verdict"] for c in v["citations"]}) if v else "")
check("api/verify does not pass the real DOI without a title",
      bool(v) and any(c["verdict"] == "NO_CLAIMED_TITLE" for c in v["citations"]),
      str({c["verdict"] for c in v["citations"]}) if v else "")

st, _ = call("POST", "/docsf/api/query", {})
check("empty query -> 400", st == 400, str(st))

st, _ = call("GET", "/docsf/api/nope")
check("unknown route -> 404", st == 404, str(st))


bad = [c for c in CHECKS if not c[1]]
for name, ok, detail in CHECKS:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
print(f"\n{len(CHECKS)-len(bad)}/{len(CHECKS)} e2e checks passed")
sys.exit(1 if bad else 0)
