# Instructions for an AI coding agent working on this repo

You are extending a verified-retrieval system for orthopaedic literature, the companion to
`surgeonvalue.com/docsf`. Read this before writing code.

## The one rule that governs every change

**A claim that cannot be traced to a retrieved span, from a citation independently
verified to exist AND to be the paper it claims to be, is not returned. The system
abstains instead.**

Every feature request gets tested against that rule. If a change would let an unverified
claim reach a user, the change is wrong even if it improves a metric.

## Why the design looks like this

A 2026 JBJS Open Access study (doi:10.2106/JBJS.OA.25.00225) prompted a model on the 19
AAOS hip-fracture CPG recommendations and asked for its evidence. Of 2,556 cited
publications: 7.9% fabricated, **1.1% overlapping the guideline's own reference list**,
and of those that do exist in PubMed, 91.7% had wrong authors, 91.5% wrong titles, 91.0%
wrong PMIDs. Meanwhile 76.3% of its answers were rated accurate to the guideline and 88.2%
were rated excellent for clarity.

So: fluent, accurate-sounding, resting on almost none of the specialty's evidence base.
Resolution-checking alone would have passed most of those citations. That is why
`verify.py` has four verdicts and only one of them is a pass.

## Do not

- **Do not add a cloud LLM call to the retrieval path by default.** `generator=None` is a
  complete product: it returns verified evidence plus the gate decision. A generator is
  opt-in and must use `grounded_prompt`, which requires a `[S#]` tag on every claim.
- **Do not index publisher full text without a TDM agreement.** `LicensedCorpusSource`
  raises if you omit `publisher`/`agreement_ref`. Do not remove that guard. Do not point
  it at scraped PDFs.
- **Do not average away a red-flag miss.** `aggregate()` reports `red_flag_failure`
  separately from the headline score for a reason: a system that catches 19 of 20
  contraindications and misses an active infection has not scored 95%.
- **Do not collapse existence and support into one citation score.** A system at 92%
  existence and 9% support is the JBJS result above; one blended number hides it.
- **Do not weaken the abstention gate to raise answer rate.** Over-commitment is the
  documented failure of every system tested (21.3%-55.3%); answer rate is not the goal.
- **Do not send user-pasted text anywhere except the DOIs needed for Crossref.** This is a
  PHI-adjacent audience. The privacy property is load-bearing.

## Where to start

```bash
python tests/test_all.py                              # 15 tests, 4 hit live Crossref
python -m orthorag.ingest --counts                    # corpus size, live
python build_index.py --retmax 2000                   # build data/ortho.index
python server.py --index data/ortho.index --prefix /docsf
```

## Highest-value work, in order

1. **Reference standard for the eval set.** The hard, unglamorous, blocking problem.
   Concordance with one attending is agreement, not ground truth. Needs blinded
   multi-surgeon adjudication with published inter-rater agreement. Until this exists,
   label every score "agreement with expert panel", never "accuracy".
2. **The reversal set** (see `REVERSAL_SET.md`). Freeze the corpus at year X, ask for a
   recommendation, score whether the system correctly identifies that the then-available
   evidence was too weak to support what the field then believed. This is the
   contamination-resistant task and the one nobody else has.
3. **Entailment scoring for `support`.** Does the retrieved span actually support the
   claim? Needs human adjudication on a sample, with an LLM judge calibrated against it.
4. **PMC Open Access full-text ingestion.** 179,712 orthopaedic records have full text in
   PMC. Currently only titles/abstracts are indexed.
5. **An omission task.** The strongest counterargument to this whole design: a 2026 J
   Biomed Inform study (doi:10.1016/j.jbi.2026.105086) found omissions dominant at 60-74%
   with hallucination rates of only 0.08-6%. A benchmark built only on citation integrity
   misses that entirely. There is currently no task family for it. Build one.

## Style

Terse, inspectable, stdlib-first. Someone auditing this should be able to read all of it.
Every module docstring states why the module exists and cites the evidence. Keep that.
