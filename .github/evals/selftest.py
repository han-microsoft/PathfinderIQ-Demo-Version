#!/usr/bin/env python3
"""selftest — prove the evals runner + reference flow. Run: `python3 selftest.py`.

Spins a fake Azure-style CRUD service (stdlib http.server) on localhost and drives
the reference flow through the REAL runner. Proves: the pass path works end-to-end,
cleanup runs, AND a forced negative path is actually caught (a flow that cannot
fail is broken — P7). No real deploy, no network egress.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "flows"))

import flow as F  # noqa: E402
import example_health  # type: ignore  # noqa: E402


class _FakeService(BaseHTTPRequestHandler):
    """Minimal in-memory CRUD with a health endpoint + bearer auth gate."""

    store: dict = {}

    def log_message(self, *a):  # silence
        pass

    def _send(self, code: int, body: dict | None = None):
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode())

    def _authed(self) -> bool:
        return self.headers.get("authorization") == "Bearer synthetic-dev-token"

    def _read_body(self) -> dict:
        n = int(self.headers.get("content-length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "build": "selftest-001"})
        if self.path.startswith("/items/"):
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            item_id = self.path.rsplit("/", 1)[-1]
            item = self.store.get(item_id)
            return self._send(200, item) if item else self._send(404, {"error": "nf"})
        self._send(404, {"error": "nf"})

    def do_POST(self):
        if self.path == "/items":
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            body = self._read_body()
            item_id = f"itm-{len(self.store) + 1}"
            self.store[item_id] = {"id": item_id, "name": body.get("name", "")}
            return self._send(201, {"id": item_id})
        self._send(404, {"error": "nf"})

    def do_DELETE(self):
        if self.path.startswith("/items/") and self._authed():
            self.store.pop(self.path.rsplit("/", 1)[-1], None)
            return self._send(204)
        self._send(404, {"error": "nf"})


def _serve() -> tuple[HTTPServer, str]:
    srv = HTTPServer(("127.0.0.1", 0), _FakeService)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _selfproof() -> None:
    srv, target = _serve()
    try:
        flow = example_health.FLOWS[0]

        # 1. happy path: every step passes, cleanup runs, nothing retained.
        ctx = F.EvalContext(live_target=target, nonce="EVAL_selftest_1")
        res = F.run_flow(flow, ctx)
        assert res.ok, [s.digest for s in res.steps if not s.ok]
        assert [s.name for s in res.steps] == \
            ["health", "unauth_rejected", "authed_write", "read_back"]
        assert res.cleanup_ok
        assert _FakeService.store == {}, "cleanup did not delete the nonce item"
        print("  happy-path: PASS")

        # 2. gating: a step failure stops the chain at that step.
        broken = F.Flow(
            name="broken", description="forced fail", tags=(),
            steps=[
                F.Step("ok", lambda c: "fine"),
                F.Step("boom", lambda c: c.expect(False, "intended failure")),
                F.Step("never", lambda c: "unreached"),
            ])
        r2 = F.run_flow(broken, F.EvalContext(live_target=target, nonce="EVAL_selftest_2"))
        assert not r2.ok
        assert [s.name for s in r2.steps] == ["ok", "boom"], "gate did not stop chain"
        assert r2.steps[-1].digest == "intended failure"
        print("  negative-path (gating): PASS")

        # 3. selective run by tag works via the real discovery+select path.
        import eval as runner  # noqa: E402
        reg = runner.discover()
        assert "authed_crud_journey" in reg
        tagged = runner._select(reg, ["run", "--tag", "auth"])
        assert [f.name for f in tagged] == ["authed_crud_journey"]
        print("  discovery + tag-select: PASS")

        print("evals selftest: PASS")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    _selfproof()
