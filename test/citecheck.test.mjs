// node --test test/citecheck.test.mjs  (offline: verdict rules)
// CITECHECK_LIVE=1 node --test test/citecheck.test.mjs  (adds four live CrossRef verdicts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const src = readFileSync(new URL("../citecheck.js", import.meta.url), "utf8");
const sandbox = { window: {}, fetch, setTimeout, Promise };
vm.runInNewContext(src, sandbox);
const C = sandbox.window.CiteCheck;

// Titles exactly as CrossRef returned them on 2026-10-02.
const GHANEM = "ChatGPT-4 Knows Its A B C D E but Cannot Cite Its Source";
const SLOAN = "Projected Volume of Primary Total Joint Arthroplasty in the U.S., 2014 to 2030";

test("VERIFIED when the reference carries the real title", () => {
  assert.equal(C.verdict("ok", GHANEM, "Ghanem D, et al. ChatGPT-4 Knows Its A B C D E but Cannot Cite Its Source. JBJS OA 2024", 0.6).verdict, "VERIFIED");
});
test("TITLE_MISMATCH when a real DOI is attached to a different paper (the case a link-checker passes)", () => {
  assert.equal(C.verdict("ok", SLOAN, "Author A, et al. Dual-mobility cups eliminate dislocation after revision hip arthroplasty. J Bone Joint Surg Am. 2018", 0.6).verdict, "TITLE_MISMATCH");
});
test("a bare DOI is NO_CLAIMED_TITLE, never a pass", () => {
  assert.equal(C.verdict("ok", SLOAN, "", 0.6).verdict, "NO_CLAIMED_TITLE");
});
test("not found and network failure are never passes", () => {
  assert.equal(C.verdict("missing", null, "some title words here", 0.6).verdict, "DOES_NOT_RESOLVE");
  assert.equal(C.verdict("error", null, "some title words here", 0.6).verdict, "UNCHECKED");
});
test("one shared generic word does not make a match", () => {
  assert.ok(C.coverage(SLOAN, "Arthroplasty outcomes in rural hospitals across three decades") < 0.6);
});
test("extracts each DOI with the words before it on its line, deduped", () => {
  const c = C.extract("Title one words here doi:10.1234/aaa. Title two other words (doi: 10.1234/bbb)\nsee https://doi.org/10.1234/aaa");
  assert.equal(JSON.stringify(c.map((x) => x.doi)), JSON.stringify(["10.1234/aaa", "10.1234/bbb"]));
  assert.match(c[1].claim, /Title two/);
  assert.doesNotMatch(c[1].claim, /Title one/);
});
test("pasted text is escaped before it reaches the page", () => {
  assert.match(src, /esc\(r\.claim\)/);
  assert.match(src, /esc\(r\.title\)/);
});

test("live CrossRef: four references, four verdicts", { skip: !process.env.CITECHECK_LIVE }, async () => {
  const r = await C.check(
    [
      "Ghanem D, et al. ChatGPT-4 Knows Its A B C D E but Cannot Cite Its Source. JBJS Open Access. 2024. doi:10.2106/JBJS.OA.24.00099",
      "Author A, et al. Dual-mobility cups eliminate dislocation after revision hip arthroplasty. 2018. doi:10.2106/JBJS.17.01617",
      "Author B, et al. Robotic arthroplasty outcomes at five years. 2025. doi:10.2106/JBJS.25.00412",
      "See doi:10.1097/CORR.0000000000003234",
    ].join("\n"),
  );
  assert.equal(JSON.stringify(r.map((x) => x.verdict)), JSON.stringify(["VERIFIED", "TITLE_MISMATCH", "DOES_NOT_RESOLVE", "NO_CLAIMED_TITLE"]));
});
