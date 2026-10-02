"""Stdlib HTTP server for the retrieval API. No framework dependency. Mount it under any prefix.

    python server.py --index data/ortho.index --port 8000 --prefix /docsf

Routes
  GET  {prefix}/            static UI
  POST {prefix}/api/query   {"q": str, "high_stakes": bool} -> Answer JSON
  POST {prefix}/api/verify  {"text": str} -> citation verdicts
  GET  {prefix}/api/health  index size + build info

Production: put this behind nginx or run via gunicorn with a WSGI shim. The handler is
deliberately small so an audit can read all of it.
"""
from __future__ import annotations
import argparse, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from orthorag.index import BM25Index
from orthorag.rag import OrthoRAG
from orthorag.verify import extract_dois, verify_doi, summarise

STATE: dict = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "orthorag"

    def _send(self, code: int, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _route(self) -> str:
        p = urlparse(self.path).path
        prefix = STATE["prefix"]
        return p[len(prefix):] or "/" if p.startswith(prefix) else p

    def do_GET(self):
        r = self._route()
        if r in ("/", "/index.html"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html")
            with open(path, "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if r == "/api/health":
            return self._send(200, {"ok": True, "documents": len(STATE["rag"].index),
                                    "verify_enabled": STATE["rag"].verify})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        r = self._route()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "invalid JSON"})

        if r == "/api/query":
            q = (body.get("q") or "").strip()
            if not q:
                return self._send(400, {"error": "q is required"})
            ans = STATE["rag"].answer(q, high_stakes=bool(body.get("high_stakes")))
            return self._send(200, ans.to_dict())

        if r == "/api/verify":
            text = body.get("text") or ""
            cits = [verify_doi(d) for d in extract_dois(text)]
            return self._send(200, {"summary": summarise(cits),
                                    "citations": [c.to_dict() for c in cits]})

        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="data/ortho.index")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--prefix", default="/docsf")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()

    idx = BM25Index.load(a.index) if os.path.exists(a.index) else BM25Index()
    STATE["rag"] = OrthoRAG(idx, generator=None, verify=not a.no_verify)
    STATE["prefix"] = a.prefix.rstrip("/")
    print(f"serving {len(idx)} docs on http://0.0.0.0:{a.port}{STATE['prefix']}/", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
