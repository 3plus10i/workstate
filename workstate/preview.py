"""Loopback-only development preview; never started by the desktop application."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


def run_preview(service, entry, port):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path not in ("/", "/index.html"):
                self.respond(404, b"Not found", "text/plain")
                return
            self.respond(200, entry.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            if host not in {f"127.0.0.1:{port}", f"localhost:{port}"} or (origin and origin != f"http://{host}") or self.path != "/api" or self.headers.get("Content-Type") != "application/json":
                self.respond(403, b"Forbidden", "text/plain")
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length < 1_000_000:
                    raise ValueError("Invalid request length")
                request = json.loads(self.rfile.read(length))
                result = service.dispatch(request["method"], request.get("payload"))
                self.respond(200, json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            except (ValueError, KeyError):
                self.respond(400, b"Invalid request", "text/plain")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"WorkState development preview: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
