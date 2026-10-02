/*!
 * citecheck.js — a citation check you can put on your own page, under your own name.
 * From surgeonvalue.com/docsf · no dependencies · no build step · no account.
 *
 * WHAT IT DOES
 *   Finds every DOI in the text a reader pastes, looks each one up at CrossRef, and
 *   compares the title CrossRef returns with the words in the reference. Only a DOI
 *   that resolves AND matches its claimed title passes. A real DOI attached to a
 *   different paper comes back "Different paper": the case a link-checker marks green.
 *
 * WHY
 *   JBJS Open Access 2026 (doi:10.2106/JBJS.OA.25.00225): of 2,556 publications a model
 *   cited for the AAOS hip fracture guideline, 7.9% were fabricated, and of the cited
 *   papers found in PubMed about nine in ten carried the wrong author, title or PMID.
 *
 * PRIVACY
 *   Nothing the reader pastes leaves their browser except the bare DOI strings, sent to
 *   api.crossref.org. No cookies, no analytics, no backend. Read this file and confirm.
 *
 * ONE PASTE
 *   <div data-citecheck data-title="Check a citation" data-accent="#0b5fff" data-brand="Your Lab"></div>
 *   <script src="https://surgeonvalue.com/citecheck.js" defer></script>
 *
 * OR BY HAND
 *   CiteCheck.mount('#el', { title, accent, brand, brandUrl, threshold: 0.6, credit: true })
 *   CiteCheck.check('Author. Title of the paper. Journal. 2024. doi:10.xxxx/yyy') -> Promise<[results]>
 *
 *   credit: false removes the small "method from surgeonvalue.com/docsf" line. You may.
 */
(function (root) {
  'use strict';

  var DOI_RX = /10\.\d{4,9}\/[^\s"'<>,;]+/g;
  var STOP = {};
  ('the and for with from into over under that this than then its their are was were has have had ' +
   'not but all any can our out who how why what when does did using use based versus among between ' +
   'after before about via per of in on at to by an a or as is be et al doi org https http www ' +
   'journal surg bone joint vol pages').split(' ').forEach(function (w) { STOP[w] = 1; });

  var LABEL = {
    VERIFIED: 'Verified', TITLE_MISMATCH: 'Different paper', NO_CLAIMED_TITLE: 'Nothing to compare',
    DOES_NOT_RESOLVE: 'Not found', UNCHECKED: 'Not checked'
  };
  var NOTE = {
    VERIFIED: 'Exists, and it is the paper the reference names. Whether it says what the text says is still yours to read.',
    TITLE_MISMATCH: 'The DOI is real but belongs to a different paper. A link-checker marks this green.',
    NO_CLAIMED_TITLE: 'Resolves, but the text names no title to compare. Not a pass: ask for the full reference.',
    DOES_NOT_RESOLVE: 'No record at CrossRef. Strike the claim or find its real source.',
    UNCHECKED: 'CrossRef could not be reached. Nothing was checked; never read this as a pass.'
  };

  function normalize(s) {
    return String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/&amp;/g, '&')
      .replace(/<[^>]+>/g, ' ').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }
  function words(s) {
    return normalize(s).split(' ').filter(function (w) { return w.length >= 3 && !STOP[w]; });
  }
  function coverage(title, claim) {
    var t = {}, n = 0, hit = 0, c = {};
    words(title).forEach(function (w) { if (!t[w]) { t[w] = 1; n++; } });
    if (!n) return 0;
    words(claim).forEach(function (w) { c[w] = 1; });
    Object.keys(t).forEach(function (w) { if (c[w]) hit++; });
    return hit / n;
  }
  function extract(text, max) {
    max = max || 25;
    var out = [], seen = {};
    String(text || '').split(/\r?\n/).forEach(function (line) {
      var from = 0, m;
      DOI_RX.lastIndex = 0;
      while ((m = DOI_RX.exec(line)) !== null && out.length < max) {
        var doi = m[0].replace(/[).\]}>]+$/, '');
        var claim = line.slice(from, m.index).replace(/\(?\s*(?:doi\s*:?|https?:\/\/(?:dx\.)?doi\.org\/)\s*$/i, '').trim();
        from = m.index + m[0].length;
        if (seen[doi.toLowerCase()]) continue;
        seen[doi.toLowerCase()] = 1;
        out.push({ doi: doi, claim: claim });
      }
    });
    return out;
  }
  function verdict(status, title, claim, threshold) {
    if (status === 'missing') return { verdict: 'DOES_NOT_RESOLVE', coverage: 0 };
    if (status === 'error') return { verdict: 'UNCHECKED', coverage: 0 };
    if (words(claim).length < 3 || !title) return { verdict: 'NO_CLAIMED_TITLE', coverage: 0 };
    var c = coverage(title, claim);
    return { verdict: c >= threshold ? 'VERIFIED' : 'TITLE_MISMATCH', coverage: Math.round(c * 100) / 100 };
  }
  // CrossRef's public API allows one request at a time per address: lookups run in
  // sequence (see check) and back off when told to slow down.
  function lookup(doi, tries) {
    tries = tries == null ? 3 : tries;
    return fetch('https://api.crossref.org/works/' + doi.split('/').map(encodeURIComponent).join('/'))
      .then(function (r) {
        if (r.status === 404) return { status: 'missing' };
        if (r.ok) return r.json().then(function (j) { return { status: 'ok', m: j.message || {} }; });
        throw new Error(String(r.status));
      })
      .catch(function () {
        if (tries > 0) return new Promise(function (res) { setTimeout(res, 700 * (4 - tries)); }).then(function () { return lookup(doi, tries - 1); });
        return { status: 'error' };
      });
  }
  function check(text, opts) {
    var threshold = (opts && opts.threshold) || 0.6;
    var cites = extract(text), results = [];
    return cites.reduce(function (p, c) {
      return p.then(function () { return lookup(c.doi); }).then(function (r) {
        var m = r.m || {};
        var title = m.title && m.title[0];
        var v = verdict(r.status, title, c.claim, threshold);
        var a = m.author && m.author[0];
        return {
          doi: c.doi, claim: c.claim, verdict: v.verdict, label: LABEL[v.verdict], pass: v.verdict === 'VERIFIED',
          coverage: v.coverage, title: title || null,
          journal: (m['container-title'] && m['container-title'][0]) || null,
          year: (m.issued && m.issued['date-parts'] && m.issued['date-parts'][0][0]) || null,
          firstAuthor: a ? [a.family, a.given].filter(Boolean).join(', ') : null
        };
      }).then(function (res) { results.push(res); });
    }, Promise.resolve()).then(function () { return results; });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeColor(c, d) { return /^#[0-9a-f]{3,8}$/i.test(c || '') ? c : d; }
  function safeUrl(u) { return /^https:\/\/[^\s"'<>]+$/i.test(u || '') ? u : null; }

  var CSS =
    '.cck{--cck-accent:#0f766e;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#111;max-width:60rem;border:1px solid #d4d4d8;border-radius:8px;padding:1rem;background:#fff}' +
    '.cck h3{margin:0 0 .25rem;font-size:1.125rem}.cck-brand{font-size:.8125rem;color:#52525b;margin:0 0 .75rem}' +
    '.cck textarea{width:100%;min-height:8rem;font:16px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;padding:.6rem;border:1px solid #a1a1aa;border-radius:6px;box-sizing:border-box}' +
    '.cck-note{font-size:.8125rem;color:#52525b;margin:.4rem 0 .7rem}' +
    '.cck-btn{min-height:44px;font-size:.9375rem;font-weight:600;padding:.5rem 1.1rem;border:0;background:var(--cck-accent);color:#fff;border-radius:6px;cursor:pointer}' +
    '.cck-btn[disabled]{opacity:.55;cursor:default}' +
    '.cck-sum{margin:.9rem 0 .4rem;font-weight:600;font-size:.9375rem}' +
    '.cck-row{border-left:4px solid #a1a1aa;padding:.55rem .75rem;margin:.5rem 0;background:#fafafa;border-radius:0 6px 6px 0}' +
    '.cck-ok{border-left-color:#15803d}.cck-bad{border-left-color:#b45309}.cck-dim{border-left-color:#71717a}' +
    '.cck-v{font-weight:700;font-size:.75rem;letter-spacing:.06em;text-transform:uppercase}' +
    '.cck-doi{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}' +
    '.cck-k{display:block;font-size:.6875rem;letter-spacing:.06em;text-transform:uppercase;color:#71717a;margin-top:.35rem}' +
    '.cck-s{text-decoration:line-through;text-decoration-color:#b45309;text-decoration-thickness:2px}' +
    '.cck-row a{color:var(--cck-accent)}' +
    '.cck-credit{margin-top:.9rem;padding-top:.5rem;border-top:1px solid #e4e4e7;font-size:.75rem;color:#71717a}.cck-credit a{color:inherit}';

  function mount(target, opts) {
    opts = opts || {};
    var host = typeof target === 'string' ? document.querySelector(target) : target;
    if (!host) throw new Error('CiteCheck.mount: target not found');
    if (!document.getElementById('cck-css')) {
      var st = document.createElement('style'); st.id = 'cck-css'; st.textContent = CSS; document.head.appendChild(st);
    }
    var threshold = Number(opts.threshold) > 0 && Number(opts.threshold) <= 1 ? Number(opts.threshold) : 0.6;
    var brandUrl = safeUrl(opts.brandUrl);
    var brand = opts.brand ? (brandUrl ? '<a href="' + esc(brandUrl) + '" rel="noopener">' + esc(opts.brand) + '</a>' : esc(opts.brand)) : '';
    host.innerHTML =
      '<div class="cck" style="--cck-accent:' + safeColor(opts.accent, '#0f766e') + '">' +
      '<h3>' + esc(opts.title || 'Check a citation') + '</h3>' +
      (brand ? '<p class="cck-brand">' + brand + '</p>' : '') +
      '<textarea aria-label="Paste references or AI-written text" placeholder="Author, et al. Title of the paper. Journal. Year. doi:10.xxxx/...  (one reference per line)"></textarea>' +
      '<p class="cck-note">Runs in your browser. Only the DOIs are sent, to api.crossref.org. Nothing is stored. No patient details.</p>' +
      '<button type="button" class="cck-btn">Check the citations</button>' +
      '<div role="status" aria-live="polite"></div>' +
      (opts.credit === false ? '' : '<p class="cck-credit">Method: <a href="https://surgeonvalue.com/docsf" rel="noopener">surgeonvalue.com/docsf</a>. A DOI that resolves is not a verified citation.</p>') +
      '</div>';
    var ta = host.querySelector('textarea'), btn = host.querySelector('.cck-btn'), out = host.querySelector('[role=status]');
    btn.addEventListener('click', function () {
      var text = ta.value;
      if (!extract(text).length) { out.innerHTML = '<p class="cck-sum">No DOI found. Ask for a DOI behind every claim.</p>'; return; }
      btn.disabled = true; btn.textContent = 'Checking…'; out.innerHTML = '';
      check(text, { threshold: threshold }).then(function (rs) {
        btn.disabled = false; btn.textContent = 'Check the citations';
        var pass = rs.filter(function (r) { return r.pass; }).length;
        var html = '<p class="cck-sum">' + rs.length + ' citation' + (rs.length === 1 ? '' : 's') + ' · ' + pass + (pass === 1 ? ' pass' : ' passes') + '</p>';
        rs.forEach(function (r) {
          var tone = r.pass ? 'cck-ok' : (r.verdict === 'UNCHECKED' || r.verdict === 'NO_CLAIMED_TITLE') ? 'cck-dim' : 'cck-bad';
          html += '<div class="cck-row ' + tone + '"><div class="cck-v">' + esc(r.label) + '</div><div class="cck-doi">' + esc(r.doi) + '</div>' +
            (r.claim ? '<span class="cck-k">The text claims</span><span class="' + (r.verdict === 'TITLE_MISMATCH' ? 'cck-s' : '') + '">' + esc(r.claim) + '</span>' : '') +
            (r.title ? '<span class="cck-k">CrossRef says</span>“' + esc(r.title) + '” ' + esc([r.firstAuthor, r.journal, r.year].filter(Boolean).join(' · ')) : '') +
            '<div class="cck-note">' + esc(NOTE[r.verdict]) + (r.title ? ' <a href="https://doi.org/' + encodeURI(r.doi) + '" target="_blank" rel="noopener">Open the paper</a>' : '') + '</div></div>';
        });
        out.innerHTML = html;
      });
    });
    return { check: check };
  }

  function auto() {
    var els = document.querySelectorAll('[data-citecheck]');
    for (var i = 0; i < els.length; i++) {
      var d = els[i].dataset;
      if (els[i].getAttribute('data-citecheck-mounted')) continue;
      els[i].setAttribute('data-citecheck-mounted', '1');
      mount(els[i], { title: d.title, accent: d.accent, brand: d.brand, brandUrl: d.brandUrl, threshold: d.threshold, credit: d.credit !== 'false' });
    }
  }

  root.CiteCheck = { mount: mount, check: check, extract: extract, verdict: verdict, coverage: coverage, version: '1.0.0' };
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auto); else auto();
  }
})(typeof window !== 'undefined' ? window : this);
