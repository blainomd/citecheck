#!/usr/bin/env bash
# Run every suite in the repo. Exits non-zero on any failure.
# macOS python.org builds may need: export SSL_CERT_FILE=/etc/ssl/cert.pem
set -u; cd "$(dirname "$0")/.."
fail=0
echo "--- unit (python) ---";   python3 tests/test_all.py   || fail=1
echo "--- e2e (python) ---";    python3 tests/test_e2e.py   || fail=1
echo "--- widget (node) ---";   node --test ../test/citecheck.test.mjs     || fail=1
echo; [ $fail -eq 0 ] && echo "ALL SUITES PASSED" || echo "FAILURES PRESENT"
exit $fail
