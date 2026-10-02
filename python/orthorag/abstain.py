"""The abstention gate. The scored behaviour, not an afterthought.

WHY
---
CliniCARE-Bench (Scale AI, August 2026 -- industry benchmark, not peer reviewed) put the
option to defer inside the scoring standard rather than bolting it on as a confidence
threshold. Across sixteen systems, EVERY system under-abstained: over-commitment ran
21.3%-55.3% while over-abstention ran only 7.3%-16.5%. It held on a rebalanced set, so it
is a property of the models, not the label mix.

The reference implementation for doing better is gated deferral. Nature Medicine,
15 September 2026 (doi:10.1038/s41591-026-04609-x): behavioural consistency discriminated
correctness at AUC 0.860, and at a 0.90 threshold the system retained 49.4% of cases at
98.9% accuracy while routing the rest to a clinician.

So this module returns one of three outcomes, and the third is a first-class answer:
  ANSWER            -- retrieval support is sufficient
  INSUFFICIENT_EVIDENCE -- the record/corpus does not contain enough to answer
  AMBIGUOUS         -- evidence is present and still supports more than one defensible read

Splitting the last two matters: they are different failures and need different fixes.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    ANSWER = "ANSWER"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class GateConfig:
    min_hits: int = 2                 # need corroboration, not a single hit
    min_top_score: float = 3.0        # BM25 score floor for the best hit
    min_mean_score: float = 1.5
    require_level: tuple = ("I", "II", "III")  # levels that may support an ANSWER
    high_stakes_require_level: tuple = ("I", "II")
    disagreement_margin: float = 0.15  # top hits scoring within this -> possible conflict


@dataclass
class GateResult:
    outcome: Outcome
    reason: str
    top_score: float = 0.0
    n_hits: int = 0
    best_level: str = "unknown"

    @property
    def answerable(self) -> bool:
        return self.outcome is Outcome.ANSWER


LEVEL_ORDER = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "unknown": 9}


def gate(hits, *, high_stakes: bool = False, config: GateConfig | None = None) -> GateResult:
    """Decide whether retrieval supports answering at all.

    `high_stakes=True` is for anything that changes what happens to a patient. It raises
    the evidence-level floor rather than the score floor, because the risk is acting on a
    confident retrieval from a case series.
    """
    cfg = config or GateConfig()
    if not hits:
        return GateResult(Outcome.INSUFFICIENT_EVIDENCE, "no documents retrieved")

    scores = [h.score for h in hits]
    top, mean = max(scores), sum(scores) / len(scores)
    levels = sorted((h.evidence_level for h in hits), key=lambda L: LEVEL_ORDER.get(L, 9))
    best = levels[0] if levels else "unknown"

    if len(hits) < cfg.min_hits:
        return GateResult(Outcome.INSUFFICIENT_EVIDENCE,
                          f"only {len(hits)} supporting document(s); need {cfg.min_hits}",
                          top, len(hits), best)
    if top < cfg.min_top_score or mean < cfg.min_mean_score:
        return GateResult(Outcome.INSUFFICIENT_EVIDENCE,
                          f"retrieval support too weak (top={top:.2f}, mean={mean:.2f})",
                          top, len(hits), best)

    needed = cfg.high_stakes_require_level if high_stakes else cfg.require_level
    if best not in needed:
        return GateResult(
            Outcome.INSUFFICIENT_EVIDENCE,
            f"best available evidence is Level {best}; "
            f"{'a patient-facing' if high_stakes else 'this'} answer requires "
            f"Level {' or '.join(needed)}",
            top, len(hits), best)

    if len(scores) >= 2 and (scores[0] - scores[1]) / (scores[0] or 1) < cfg.disagreement_margin:
        return GateResult(Outcome.AMBIGUOUS,
                          "top sources score near-equally; check whether they agree before relying on this",
                          top, len(hits), best)

    return GateResult(Outcome.ANSWER, "retrieval support sufficient", top, len(hits), best)
