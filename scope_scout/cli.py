"""Minimal CLI for smoke testing the agent loop.

Usage:
    python -m scope_scout.cli                 # uses the default smoke input
    python -m scope_scout.cli "your text"     # one-shot
    python -m scope_scout.cli --repl          # interactive multi-turn

Prints the reasoning trace as it happens (thinking text, tool calls, tool
results) so you can see the agent reasoning in real time without a UI.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import nullcontext

# Force UTF-8 on stdout so the agent's reasoning trace (which uses arrows,
# em-dashes, smart quotes from Bloomreach docs) prints on Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from .agent import AgentSession, run_turn
from .loomi_mcp import LoomiMCP


SMOKE_INPUT = (
    "We're scoping a Bloomreach Engagement implementation for a furniture "
    "retailer. The client wants: (1) abandoned cart recovery email, "
    "(2) welcome flow for newsletter signups, and (3) loyalty program for "
    "repeat customers. What does this implementation look like and what "
    "should I be asking the client before I scope?"
)


def _print_event(event: dict) -> None:
    """Format one trace event for terminal display."""
    t = event["type"]
    if t == "thinking":
        text = event["text"].strip()
        if text:
            print(f"\n[agent]\n{text}\n")
    elif t == "tool_use":
        print(f"  -> tool_use: {event['name']}({json.dumps(event['input'], ensure_ascii=False)})")
    elif t == "tool_result":
        result = event["result"]
        # Truncate huge results for terminal readability
        preview = result if len(result) < 400 else result[:400] + f"... ({len(result)} chars)"
        print(f"  <- tool_result: {event['name']} = {preview}")
    elif t == "final":
        print("\n[turn complete]\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scope Scout CLI")
    parser.add_argument("input", nargs="?", help="Architect input text (omit for default smoke input)")
    parser.add_argument("--repl", action="store_true", help="Interactive multi-turn mode")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Connect to the live neon-sock workspace via the Loomi MCP "
        "(opens a browser on first auth; needs Node/npx).",
    )
    args = parser.parse_args()

    session = AgentSession()

    # --live opens a persistent MCP session for the whole run; without it the
    # context manager yields None and the agent runs local-knowledge only.
    if args.live:
        print("Connecting to live neon-sock workspace via Loomi MCP...\n")
    cm = LoomiMCP() if args.live else nullcontext(None)

    with cm as mcp:
        if args.repl:
            print("Scope Scout REPL — Ctrl+C or empty line to exit.\n")
            while True:
                try:
                    text = input("architect> ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    return 0
                if not text:
                    return 0
                for event in run_turn(session, text, mcp=mcp):
                    _print_event(event)
        else:
            text = args.input or SMOKE_INPUT
            print(f"architect> {text}\n")
            for event in run_turn(session, text, mcp=mcp):
                _print_event(event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
