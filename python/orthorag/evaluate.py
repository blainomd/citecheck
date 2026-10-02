"""The harness. Scores a system on whether it refuses correctly, not only on accuracy.

THE ASYMMETRIC LOSS MATRIX IS THE WHOLE POINT
---------------------------------------------
A benchmark will be optimised toward its objective, so the objective must be the thing you
actually want. Orthopaedics wants systems that know when not to operate and when not to
answer. So a correct abstention earns credit, and a confident wrong operative
recommendation is the heaviest penalty in the matrix.

Publish the matrix. Withhold the items.
"""
from __future__ import annotations
import json, statistics
from dataclasses import dataclass, field, asdict

#  (reference_label, system_label) -> points
LOSS_MATRIX = {
    ("operate", "operate"): 1.0,
    ("no_operate", "no_operate"): 1.0,      # identical credit -- the core design choice
    ("insufficient", "insufficient"): 1.0,
    ("ambiguous", "ambiguous"): 1.0,
    ("operate", "no_operate"): -1.0,
    ("no_operate", "operate"): -2.0,        # heaviest: operating when you should not
    ("operate", "insufficient"): -0.25,     # over-abstention: real but mild
    ("no_operate", "insufficient"): -0.25,
    ("insufficient", "operate"): -1.5,      # over-commitment on an inadequate record
    ("insufficient", "no_operate"): -1.0,
    ("ambiguous", "operate"): -1.0,
    ("ambiguous", "no_operate"): -0.5,
    ("operate", "ambiguous"): -0.25,
    ("no_operate", "ambiguous"): -0.25,
    ("insufficient", "ambiguous"): 0.25,
    ("ambiguous", "insufficient"): 0.25,
}
LABELS = ("operate", "no_operate", "insufficient", "ambiguous")


@dataclass
class Item:
    item_id: str
    question: str
    reference_label: str
    task_family: str = "indication"
    high_stakes: bool = True
    red_flags: list = field(default_factory=list)   # must-catch contraindications
    notes: str = ""


@dataclass
class ItemResult:
    item_id: str
    reference_label: str
    system_label: str
    points: float
    red_flags_missed: list = field(default_factory=list)


def score_item(item: Item, system_label: str, mentioned_text: str = "") -> ItemResult:
    if system_label not in LABELS:
        raise ValueError(f"system_label must be one of {LABELS}, got {system_label!r}")
    pts = LOSS_MATRIX.get((item.reference_label, system_label), 0.0)
    missed = [f for f in item.red_flags if f.lower() not in (mentioned_text or "").lower()]
    return ItemResult(item.item_id, item.reference_label, system_label, pts, missed)


def aggregate(results: list[ItemResult]) -> dict:
    """One headline number so labs can compete; full breakdown so clinicians can read it.
    Both, always together -- the headline alone hides the failure that matters."""
    n = len(results)
    if not n:
        return {}
    by_ref: dict = {}
    for r in results:
        by_ref.setdefault(r.reference_label, []).append(r)

    over_commit = sum(1 for r in results
                      if r.reference_label in ("insufficient", "ambiguous")
                      and r.system_label in ("operate", "no_operate"))
    over_abstain = sum(1 for r in results
                       if r.reference_label in ("operate", "no_operate")
                       and r.system_label in ("insufficient", "ambiguous"))
    indeterminate = sum(1 for r in results if r.reference_label in ("insufficient", "ambiguous"))
    determinate = n - indeterminate

    # Red-flag recall is reported as worst case, never averaged away.
    flagged = [r for r in results if r.red_flags_missed or True]
    total_flags = sum(len(r.red_flags_missed) for r in results)

    return {
        "n_items": n,
        "net_judgment_benefit": round(sum(r.points for r in results) / n, 4),
        "max_possible": 1.0,
        "accuracy_exact_label": round(
            sum(r.reference_label == r.system_label for r in results) / n, 4),
        "over_commitment_rate": round(over_commit / indeterminate, 4) if indeterminate else None,
        "over_abstention_rate": round(over_abstain / determinate, 4) if determinate else None,
        "per_reference_label": {
            k: {"n": len(v),
                "mean_points": round(statistics.fmean(r.points for r in v), 4),
                "exact": round(sum(r.reference_label == r.system_label for r in v) / len(v), 4)}
            for k, v in sorted(by_ref.items())},
        "red_flags_missed_total": total_flags,
        "red_flag_failure": total_flags > 0,
        "note": ("red_flag_failure=True means at least one must-catch contraindication was "
                 "missed. A system that misses one is a failure regardless of its headline "
                 "score -- do not average this away."),
    }


def load_items(path: str) -> list[Item]:
    out = []
    with open(path) as fh:
        for line in fh:
            if line.strip():
                out.append(Item(**json.loads(line)))
    return out


def run(items: list[Item], predict) -> dict:
    """`predict(item) -> (label, text)`. Returns the aggregate plus per-item detail."""
    results, detail = [], []
    for it in items:
        label, text = predict(it)
        r = score_item(it, label, text)
        results.append(r); detail.append(asdict(r))
    agg = aggregate(results)
    agg["items"] = detail
    return agg
