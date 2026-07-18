"""Local deterministic adversarial REST target for integration tests."""
from __future__ import annotations
import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

class AdversarialHandler(BaseHTTPRequestHandler):
    scenario = "ok"
    def do_GET(self):
        if self.scenario == "slow": time.sleep(2)
        if self.scenario == "unauthorized": self.send_response(401); self.end_headers(); return
        if self.scenario == "server_error": self.send_response(500); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b"not-json" if self.scenario == "malformed" else json.dumps({"ok": True}).encode())
    def log_message(self, *_): pass

class AdversarialApi:
    def __init__(self, scenario: str = "ok"):
        if scenario not in {"ok", "slow", "unauthorized", "server_error", "malformed"}: raise ValueError("unknown scenario")
        self.scenario = scenario; self.server = None; self.thread = None
    def start(self) -> str:
        handler = type("ScenarioHandler", (AdversarialHandler,), {"scenario": self.scenario})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler); self.thread = Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}/"
    def stop(self) -> None:
        if self.server: self.server.shutdown(); self.server.server_close(); self.server = None
