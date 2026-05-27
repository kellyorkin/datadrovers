"""Synchronous wrapper around the live Bloomreach Loomi MCP.

Why this exists: the agent loop (agent.py) is synchronous and fires tool calls in
batches. The MCP, by contrast, is async, reached over a spawned `mcp-remote`
subprocess, and rate-limited to 1 request/second/user (and the alpha endpoint
drops streams intermittently). This class absorbs all of that and exposes one
simple, blocking method — `call(tool, args) -> str` — that returns the tool's
result as a JSON string, the same shape tools.py already hands back to Claude.

How it works:
  - On enter, it spawns ONE persistent `npx mcp-remote <URL>` session inside a
    dedicated background thread running its own asyncio loop, and keeps it open
    for the whole agent run (so we pay the OAuth/bridge startup cost once).
  - `call()` is thread-safe and SERIALIZED: a lock + pacing guarantees we never
    exceed ~1 req/sec no matter how many tool calls the agent fans out. It
    retries on rate-limit (429) and on SSE stream drops, with a per-call read
    timeout so a dead stream can never hang the agent.
  - On any unrecoverable failure it returns a JSON {"error": ...} string rather
    than raising, so the agent degrades gracefully (and the caller can swap in a
    stub). The token is already cached in ~/.mcp-auth, so no browser on re-runs.

Usage:
    with LoomiMCP() as mcp:
        print(mcp.read("get_event_schema"))   # project_id injected automatically
        # NB: do NOT print/log whoami — its response body embeds the live
        # access token. Use read()/call() for data tools instead.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOOMI_MCP_URL = "https://loomi-mcp-alpha.bloomreach.com/mcp"  # no trailing slash
NPX = "npx.cmd" if os.name == "nt" else "npx"

# neon-sock — captured via probe #3 so the agent never spends rate-limited calls
# re-navigating org -> workspace -> project.
NEON_SOCK_PROJECT_ID = "b5bbb76c-5469-11f1-aaeb-9ee3018bf36e"

# Introspection tools that take a single `project_id` argument. `read()` injects it.
PROJECT_TOOLS = {
    "get_project_overview",
    "get_event_schema",
    "get_customer_property_schema",
    "get_customer_schema",
    "get_mapping",
}


def _text_of(result) -> str:
    return "".join(getattr(b, "text", str(b)) for b in result.content)


class LoomiMCP:
    def __init__(
        self,
        *,
        project_id: str = NEON_SOCK_PROJECT_ID,
        pace_seconds: float = 1.2,
        read_timeout: float = 30.0,
        retries: int = 2,
        startup_timeout: float = 120.0,
    ) -> None:
        self.project_id = project_id
        self.pace_seconds = pace_seconds
        self.read_timeout = read_timeout
        self.retries = retries
        self.startup_timeout = startup_timeout

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: ClientSession | None = None
        self._stop_event: asyncio.Event | None = None
        self._ready = threading.Event()
        self._startup_error: Exception | None = None

        self._call_lock = threading.Lock()  # serialize + pace all calls
        self._last_call_ts = 0.0

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "LoomiMCP":
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=self.startup_timeout):
            raise RuntimeError(
                "Loomi MCP bridge did not become ready in time. If this is the "
                "first connection on a fresh machine it may be waiting on a "
                "browser login."
            )
        if self._startup_error is not None:
            raise self._startup_error
        return self

    def __exit__(self, *exc) -> None:
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=15)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        """Open the bridge + session once and hold it until __exit__ signals stop."""
        server = StdioServerParameters(command=NPX, args=["-y", "mcp-remote", LOOMI_MCP_URL])
        try:
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._stop_event = asyncio.Event()
                    self._ready.set()
                    await self._stop_event.wait()
        except Exception as e:  # surface startup failures to __enter__
            self._startup_error = e
            self._ready.set()

    # -- calling -----------------------------------------------------------

    async def _invoke(self, name: str, args: dict):
        return await self._session.call_tool(
            name, arguments=args, read_timeout_seconds=timedelta(seconds=self.read_timeout)
        )

    def call(self, name: str, args: dict | None = None) -> str:
        """Blocking, serialized, paced, retried tool call. Returns a JSON string.

        On unrecoverable failure returns json.dumps({"error": ...}) so the agent
        keeps going instead of crashing.
        """
        args = args or {}
        with self._call_lock:
            for attempt in range(self.retries + 1):
                # Pace: never fire faster than the server's 1 req/sec limit.
                delta = time.monotonic() - self._last_call_ts
                if delta < self.pace_seconds:
                    time.sleep(self.pace_seconds - delta)

                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._invoke(name, args), self._loop
                    )
                    result = future.result(timeout=self.read_timeout + 10)
                    body = _text_of(result)
                except Exception as e:  # SSE drop / timeout / loop error
                    self._last_call_ts = time.monotonic()
                    if attempt < self.retries:
                        time.sleep(1.5)
                        continue
                    return json.dumps({"error": f"{name}: {type(e).__name__}: {e}"})

                self._last_call_ts = time.monotonic()
                is_err = getattr(result, "isError", False)
                if is_err and "Too many requests" in body and attempt < self.retries:
                    time.sleep(1.5)
                    continue
                if is_err:
                    return json.dumps({"error": f"{name}: {body}"})
                return body
        return json.dumps({"error": f"{name}: exhausted retries"})

    def read(self, tool: str, **extra) -> str:
        """Convenience for project-scoped introspection tools — injects project_id."""
        args = dict(extra)
        if tool in PROJECT_TOOLS:
            args.setdefault("project_id", self.project_id)
        return self.call(tool, args)


# --- self-test ------------------------------------------------------------

if __name__ == "__main__":
    print("Opening persistent Loomi MCP session (cached token, no browser)...")
    with LoomiMCP() as mcp:
        for tool in ("get_project_overview", "get_mapping"):
            body = mcp.read(tool)
            ok = "error" not in body[:30].lower()
            print(f"\n## {tool} -> {'OK' if ok else 'ERROR'} ({len(body)} chars)")
            print(body[:600])
    print("\nSession closed cleanly.")
