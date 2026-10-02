"""Orchestration: retrieve -> gate -> ground -> verify. No ungrounded claim escapes.

The generation step is pluggable and OPTIONAL. With no generator supplied the system
returns retrieved, verified evidence and the gate decision -- which is a complete and
honest product. The generator only ever reformats material that is already on screen.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .abstain import gate, GateResult, Outcome, GateConfig
from .verify import verify_doi, Citation, Verdict


@dataclass
class Answer:
    query: str
    outcome: str
    gate_reason: str
    hits: list = field(default_factory=list)
    citations: list = field(default_factory=list)
    text: str | None = None
    high_stakes: bool = False

    def to_dict(self):
        return {"query": self.query, "outcome": self.outcome, "gate_reason": self.gate_reason,
                "high_stakes": self.high_stakes, "text": self.text,
                "hits": [h.__dict__ for h in self.hits],
                "citations": [c.to_dict() for c in self.citations]}


class OrthoRAG:
    def __init__(self, index, generator=None, *, config: GateConfig | None = None,
                 verify: bool = True):
        self.index, self.generator, self.config, self.verify = index, generator, config, verify

    def answer(self, query: str, *, top_k: int = 8, high_stakes: bool = False) -> Answer:
        hits = self.index.search(query, top_k=top_k)
        g: GateResult = gate(hits, high_stakes=high_stakes, config=self.config)

        cits: list[Citation] = []
        if self.verify:
            for h in hits:
                if h.doi:
                    cits.append(verify_doi(h.doi, h.title))

        ans = Answer(query=query, outcome=g.outcome.value, gate_reason=g.reason,
                     hits=hits, citations=cits, high_stakes=high_stakes)

        if not g.answerable:
            ans.text = self._refusal(g, hits)
            return ans

        # A citation that resolves to a different paper disqualifies its source.
        bad = [c for c in cits if c.verdict is Verdict.TITLE_MISMATCH]
        if bad:
            ans.outcome = Outcome.INSUFFICIENT_EVIDENCE.value
            ans.gate_reason = (f"{len(bad)} retrieved citation(s) resolve to a different paper "
                               "than claimed; refusing to answer on unverified sources")
            ans.text = self._refusal(g, hits)
            return ans

        if self.generator is None:
            ans.text = None   # evidence-only mode
            return ans

        ans.text = self.generator(query=query, hits=hits, gate=g)
        return ans

    @staticmethod
    def _refusal(g: GateResult, hits) -> str:
        lines = [f"Not answering. {g.reason}."]
        if hits:
            lines.append("")
            lines.append("Closest retrieved material, for you to judge:")
            for h in hits[:5]:
                lines.append(f"  - [{h.evidence_level}] {h.title} ({h.journal} {h.year or '?'})"
                             + (f" doi:{h.doi}" if h.doi else " (no DOI)"))
        lines.append("")
        lines.append("A weak answer here would cost more than no answer.")
        return "\n".join(lines)


def grounded_prompt(query: str, hits, gate) -> str:
    """Prompt template for whatever model is wired in. Every claim must cite a [S#] tag,
    and the model is instructed that refusing is a valid, scored outcome."""
    src = "\n\n".join(
        f"[S{i+1}] {h.title} ({h.journal} {h.year or '?'}; Level {h.evidence_level}"
        + (f"; doi:{h.doi}" if h.doi else "") + f")\n{h.snippet}"
        for i, h in enumerate(hits))
    return f"""Answer the clinical question using ONLY the numbered sources below.

RULES
- Every factual claim must end with its source tag, e.g. [S2]. No tag means delete the claim.
- If the sources do not support an answer, say exactly: INSUFFICIENT EVIDENCE, and say what
  is missing. Refusing is a correct answer and is scored as one.
- Do not supply a citation that is not in the list. Do not infer a DOI.
- State the evidence level you are relying on, and do not describe a Level IV or V source
  with the confidence of a Level I source.
- Name the strongest source that argues against your own conclusion, if one is present.

QUESTION: {query}

SOURCES
{src}
"""
