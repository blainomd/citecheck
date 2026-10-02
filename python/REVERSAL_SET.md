# The reversal set

The contamination-resistant task family, and the one nobody else has. Not yet built — this
is the specification.

## The idea

Fifty years of orthopaedic literature is the specialty's record of where it changed its
mind. Vertebroplasty for osteoporotic compression fracture. Arthroscopic partial
meniscectomy for degenerative tears. Metal-on-metal bearings. Routine rhBMP-2 in spine
fusion. Thermal capsulorrhaphy.

Each is a dated natural experiment: a period when the published evidence supported
enthusiasm, then better evidence reversed it. The answer was knowable in principle from the
weakness of the early evidence, and the field got it wrong anyway.

## The task

Freeze the corpus at year X. Supply only literature published before X. Ask for a
recommendation.

## What is scored — and this is the whole design

**Not** "did you predict the future." Any current model has read the outcome; asking it to
predict 2015 from 2005 tests memorisation and nothing else.

**Scored instead:** reasoning only from the pre-reversal evidence, does the system correctly
identify that the evidence base was too weak to support what the field then believed?

A system that said *"the 2005 evidence for vertebroplasty is uncontrolled case series and
does not support this level of confidence"* would have been right, and right **for the
available reason**. That is the behaviour worth paying for.

## Why this is the right shape for a harness

- **Leak-proof.** The correct output is a calibration statement about evidence sufficiency,
  not a fact to recall. Publish the whole answer key and the task stays hard.
- **It makes abstention the winning move**, matching the documented failure of every system
  tested (over-commitment 21.3%–55.3%, CliniCARE-Bench August 2026).
- **Orthopaedics is uniquely positioned to own it.** JBJS pioneered explicit Level of
  Evidence labelling, so the specialty has a graded fifty-year record of its own confidence.
  Few fields do.
- **It is a journal asset, not a vendor asset.** The reversal record and the LOE labels sit
  with JBJS. That makes the governance ask a publishing ask.

## Item schema

```jsonc
{
  "item_id": "rev_vertebroplasty_2005",
  "topic": "vertebroplasty for osteoporotic vertebral compression fracture",
  "freeze_year": 2005,
  "question": "A 74-year-old with an acute painful osteoporotic L2 compression fracture...",
  "contemporary_belief": "widely adopted, strongly advocated",
  "later_reference": "sham-controlled trials found no benefit over placebo",
  "reference_label": "insufficient",      // correct answer AT the freeze year
  "reversal_year": 2009,
  "evidence_at_freeze": ["uncontrolled case series", "registry data"],
  "red_flags": [],
  "adjudication": { "panel_size": 0, "agreement": null }   // MUST be filled before use
}
```

## Build steps

1. **Candidate identification.** Systematic search for orthopaedic reversals with a dated
   landmark trial. Seed from published "medical reversal" literature rather than memory —
   several commonly cited examples are misremembered, and the whole exercise fails if the
   reversal set itself is unverified.
2. **Verify every anchor.** Each candidate needs the pre-reversal and post-reversal papers
   confirmed by DOI through Crossref with a title match. Use `orthorag.verify`. Discard any
   candidate whose anchors cannot be verified; do not fill gaps from recollection.
3. **Freeze the corpus.** Index restricted to `year <= freeze_year`. The index must be built
   from a filtered corpus, not filtered at query time — leakage through BM25 statistics is
   subtle and real.
4. **Blinded adjudication.** Multiple surgeons, blinded to the outcome, label what the
   correct answer *was* at the freeze year. Publish inter-rater agreement. **Without this
   the set is an opinion, not a benchmark.**
5. **Hold it back.** Public development set for method transparency; private evaluation set
   scored by submission, refreshed on a published cadence.

## Known hazards

- **Hindsight contamination in the labelling**, not just the model. Adjudicators who know the
  outcome cannot label the freeze year cleanly. Blinding is doing real work here.
- **Survivorship.** Reversals are visible; practices that were correctly adopted and never
  reversed are invisible, and a set made only of reversals teaches a system to refuse
  everything. **Include controls: topics where the contemporary enthusiasm turned out to be
  justified.** Without them the harness rewards indiscriminate abstention — the exact
  Goodhart failure this design is otherwise built to avoid.
- **"Insufficient" is not always the right answer at the freeze year.** Sometimes the
  evidence genuinely did support the practice and new information later changed the
  calculus. Those items belong in the set labelled accordingly.

---

## Seed set — anchors verified 2 October 2026

`data/reversal_seed.jsonl` contains four candidate items. Every reversal anchor below
returned HTTP 200 from Crossref **and** a title similarity of 1.0 against the title claimed
for it. None has been adjudicated, so **none is usable as a benchmark item yet** — the
`status` field says so explicitly and the `adjudication.panel_size` is 0.

| Item | Freeze | Reversal | Anchor DOI(s) |
|---|---|---|---|
| Vertebroplasty for osteoporotic VCF | 2008 | 2009 | 10.1056/NEJMoa0900563 · 10.1056/NEJMoa0900429 |
| APM for degenerative meniscal tear | 2012 | 2013 | 10.1056/NEJMoa1305189 |
| Arthroscopic debridement for knee OA | 2001 | 2002 | 10.1056/NEJMoa013259 · 10.1056/NEJMoa0708333 |
| Subacromial decompression for shoulder pain | 2016 | 2018 | 10.1016/S0140-6736(17)32457-1 · 10.1136/bmj.k2860 |

Re-verify before use — Crossref metadata changes, and the point of this project is not to
take anyone's word for a citation, including mine:

```bash
python - <<'PY'
from orthorag.verify import verify_doi
import json
for line in open("data/reversal_seed.jsonl"):
    it = json.loads(line)
    for a in it["reversal_anchors"]:
        c = verify_doi(a["doi"])
        print(it["item_id"], a["doi"], c.verdict.value, c.actual_title)
PY
```

**Still required before any of these is a benchmark item:** blinded multi-surgeon
adjudication of what the correct answer *was* at the freeze year, with published inter-rater
agreement, plus control items where the contemporary enthusiasm turned out to be justified.
Without the controls the harness rewards indiscriminate abstention.
