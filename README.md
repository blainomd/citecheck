# citecheck

**A citation check that compares titles, not just DOIs.** Paste a reference list or an
AI-written summary; every DOI is looked up at CrossRef, and the title CrossRef returns is
compared with the words in the reference. Only a DOI that resolves **and** matches its claimed
title passes.

Try it: **[surgeonvalue.com/docsf#check](https://surgeonvalue.com/docsf#check)** · Apache-2.0 ·
no dependencies · no account · nothing stored

## Why existence-checking is not enough

*JBJS Open Access* 2026 ([doi:10.2106/JBJS.OA.25.00225](https://doi.org/10.2106/JBJS.OA.25.00225))
asked a model about each of the 19 AAOS hip fracture guideline recommendations, then asked for
its evidence. It cited 2,556 publications:

| | |
|---|---|
| Fabricated outright | 7.9% |
| Of the cited papers found in PubMed: wrong authors / wrong title / wrong PMID | 91.7% / 91.5% / 91.0% |
| In the guideline's own reference list | 1.1% |
| Answers still rated accurate to the guideline | 76.3% |

A link-checker passes most of those citations. A real DOI attached to a claim the paper never
made is the common failure, not the rare one.

## Five verdicts, one pass

| Verdict | Meaning | Pass? |
|---|---|---|
| `VERIFIED` | Resolves, and the reference carries CrossRef's title | yes |
| `TITLE_MISMATCH` | Resolves **to a different paper** | no |
| `NO_CLAIMED_TITLE` | Resolves, but the text gives nothing to compare | no |
| `DOES_NOT_RESOLVE` | No record at CrossRef | no |
| `UNCHECKED` | CrossRef not reached | no |

None of them answers the third question: does the paper say what the summary says? That still
takes a person.

## Use it: one paste

Put this in any page that accepts HTML. Change the heading, brand and colour; that is the setup.

```html
<div data-citecheck data-title="Check a citation" data-brand="Your Lab" data-brand-url="https://your.site" data-accent="#0b5fff"></div>
<script src="https://surgeonvalue.com/citecheck.js" defer></script>
```

Or self-host: copy `citecheck.js` next to your page and point the `src` at it. To see it
working right now, open `examples/index.html` in a browser.

Options (as `data-*` attributes, or `CiteCheck.mount(el, {...})`):

| Option | Default | |
|---|---|---|
| `title` | "Check a citation" | heading |
| `brand`, `brandUrl` | none | your name, and an https link |
| `accent` | `#0f766e` | button and link colour |
| `threshold` | `0.6` | share of the title's content words that must appear in the reference |
| `credit` | `true` | `false` removes the small method line |

In code:

```js
const results = await CiteCheck.check("Ghanem D, et al. ChatGPT-4 Knows Its A B C D E but Cannot Cite Its Source. 2024. doi:10.2106/JBJS.OA.24.00099");
// [{ doi, claim, verdict: "VERIFIED", pass: true, coverage: 1, title, journal, year, firstAuthor }]
```

## API

```bash
curl -s https://surgeonvalue.com/api/cite-check -H "Content-Type: application/json" \
  -d '{"text":"Author. Title of the paper. Journal. Year. doi:10.xxxx/yyy"}'
```

Also `GET /api/cite-check?ref=...`. Up to 10 DOIs per call, stateless. Send references,
never patient details.

## Privacy

The widget runs in the reader's browser. The only thing that leaves the page is each bare DOI,
sent to `api.crossref.org`. No cookies, analytics or backend. Read `citecheck.js` and confirm.

## How matching works, and where it fails

Each DOI is paired with the text before it on the same line. The title CrossRef returns is
reduced to content words (lower-cased, accents and punctuation stripped, short and common words
dropped); the verdict is `VERIFIED` when at least 60% of them appear in the reference.

- A reference with a paraphrased or heavily abbreviated title can come back `TITLE_MISMATCH`.
  That errs toward a person opening the paper, which is the right direction.
- A reference that shares most title words with a different real paper could pass. Rare, but
  this checks identity, not content.
- CrossRef's public API allows one request at a time per address, so lookups run in sequence.
- A DOI taken from the wrong field of a PubMed record can belong to a linked comment. It
  resolves perfectly and is the wrong paper. Checkers need tests where they should fail.

## Tests

```bash
node --test test/citecheck.test.mjs                    # verdict rules, offline
CITECHECK_LIVE=1 node --test test/citecheck.test.mjs   # plus four live CrossRef verdicts
```

## `python/`: retrieval that abstains

A standard-library Python package for building and scoring a literature-retrieval system that
refuses to answer rather than answer from unverified sources: BM25 retrieval over PubMed
records, an abstention gate (`ANSWER` / `INSUFFICIENT_EVIDENCE` / `AMBIGUOUS`), the same
title-match verification, and an evaluation harness with an asymmetric loss matrix and
red-flag recall that is never averaged away. `python/REVERSAL_SET.md` specifies a
contamination-resistant task built from the specialty's own reversals.

```bash
cd python
python3 tests/test_all.py      # 14 unit tests (4 call live CrossRef)
python3 tests/test_e2e.py      # 22 end-to-end checks, offline fixture corpus
python3 build_index.py --retmax 2000
python3 server.py --index data/ortho.index
```

The fixture corpus is synthetic on purpose (see `python/tests/fixtures/README.md`). On a
python.org build of Python on macOS you may need `export SSL_CERT_FILE=/etc/ssl/cert.pem`.
Read `python/AGENT_INSTRUCTIONS.md` before extending it.

## Limits, stated plainly

The orthopaedic studies behind this are small and single-centre, and they tested specific
model versions. The strongest published case against the fabrication framing: a 2026
*Journal of Biomedical Informatics* systematic review found omissions dominant (60-74%) and
hallucination at 0.08-6% ([doi:10.1016/j.jbi.2026.105086](https://doi.org/10.1016/j.jbi.2026.105086)).
A citation check catches none of what a summary leaves out.

## More open building blocks

This is one piece. Other Apache-2.0 building blocks for healthcare software (FHIR helpers,
identity, PROMs) are listed at **[solvinghealth.com/#open](https://solvinghealth.com/#open)**.

Made for the DOCSF 2026 breakout "The Evolution of Search" (surgeonvalue.com/docsf).
Apache-2.0: copy it, rename it, adapt it for your specialty.
