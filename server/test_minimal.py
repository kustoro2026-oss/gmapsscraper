"""Minimal test — no database, no imports. If this works, the issue is in app.py."""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8080))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "path": self.path}).encode())
    
    def log_message(self, format, *args):
        print(f"  [REQ] {args[0]}")

print(f"Minimal server on 0.0.0.0:{PORT}")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
