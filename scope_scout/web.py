"""Local reasoning-trace UI for Scope Scout — the demo console we screen-record.

Renders the SAME event stream the CLI already consumes (run_turn yields
thinking / tool_use / tool_result / final) but streams it to a browser over
Server-Sent Events, so the agent's reasoning appears in real time: the
conversation/agenda builds on the left while the live reasoning trace (every
tool call, with LIVE workspace reads badged distinctly) builds on the right.

Run:
    python -m scope_scout.web              # local-knowledge only (recording-safe)
    python -m scope_scout.web --live       # connect live neon-sock via Loomi MCP

Single-user demo server by design: one AgentSession lives at module scope and
/api/reset starts a fresh one between scenarios. The optional live MCP session
is opened once at startup and held for the process lifetime (it's serialized
and rate-paced internally), then closed on exit.
"""

from __future__ import annotations

import argparse
import atexit
import json
import sys
import threading

from flask import Flask, Response, render_template, request

from .agent import AgentSession, run_turn
from .loomi_mcp import LoomiMCP

app = Flask(__name__)

# --- process-wide demo state ----------------------------------------------
# One conversation at a time (single-user demo). A lock guards turn execution
# so overlapping POSTs can't interleave on the same session / MCP.
_session = AgentSession()
_session_lock = threading.Lock()
_mcp = None  # set at startup when --live; the live LoomiMCP session, else None


def _sse(event: dict) -> str:
    """Encode one trace event as an SSE frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.route("/")
def index():
    return render_template("index.html", live=_mcp is not None)


@app.route("/api/reset", methods=["POST"])
def reset():
    """Start a fresh conversation (used between demo scenarios)."""
    global _session
    with _session_lock:
        _session = AgentSession()
    return {"ok": True}


@app.route("/api/chat", methods=["POST"])
def chat():
    """Run one architect turn, streaming the reasoning trace as SSE."""
    user_input = (request.json or {}).get("input", "").strip()
    if not user_input:
        return {"error": "empty input"}, 400

    def stream():
        # Hold the lock for the whole turn so a second request can't run_turn
        # against the same session/MCP concurrently. SSE keeps the HTTP
        # connection open for the turn's duration, which is what we want.
        with _session_lock:
            try:
                for event in run_turn(_session, user_input, mcp=_mcp):
                    yield _sse(event)
            except Exception as e:  # surface to the UI instead of a dead stream
                yield _sse({"type": "error", "text": f"{type(e).__name__}: {e}"})

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering so frames flush live
            "Connection": "keep-alive",
        },
    )


def main() -> int:
    global _mcp
    parser = argparse.ArgumentParser(description="Scope Scout reasoning-trace web UI")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Connect the live neon-sock workspace via Loomi MCP "
        "(opens a browser on first auth; needs Node/npx).",
    )
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if args.live:
        print("Connecting to live neon-sock workspace via Loomi MCP...", flush=True)
        mcp = LoomiMCP()
        mcp.__enter__()
        _mcp = mcp
        atexit.register(lambda: mcp.__exit__(None, None, None))
        print("Live workspace connected.\n", flush=True)
    else:
        print("Running local-knowledge only (recording-safe). Use --live for the "
              "live workspace.\n", flush=True)

    print(f"Scope Scout console: http://127.0.0.1:{args.port}\n", flush=True)
    # threaded=True so the SSE stream for a turn doesn't block /api/reset or the
    # page load. use_reloader=False so we don't spawn a second process that would
    # try to open a second MCP session.
    app.run(port=args.port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
