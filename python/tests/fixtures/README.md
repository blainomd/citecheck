# Fixture corpus

60 **synthetic** orthopaedic records so `tests/test_e2e.py` runs offline on a fresh clone
with no harvest step.

Synthetic on purpose: shipping real abstracts would place third-party copyrighted text in a
repository whose central argument is that you must license the corpus you index.

The DOIs use the reserved-looking `10.9999/fixture.*` prefix and **do not resolve**. Tests
that need a resolving DOI use real ones against live Crossref and are marked as network
tests. A fixture DOI appearing as `VERIFIED` would mean the verifier is broken.
