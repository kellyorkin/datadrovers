# Running Scope Scout (Sawyer) locally

Scope Scout is a standalone Python application. It calls the Anthropic API directly for reasoning and — optionally — reads a live Bloomreach workspace through the Loomi Connect Marketing MCP. No AI coding tool is required to run it.

## Two modes

- **Local-knowledge (default).** Sawyer reasons over Bloomreach's published Plug & Play use case library. No Bloomreach login and no Node required — the easiest way to try it.
- **Live (`--live`).** Adds real workspace introspection against the Loomi Connect Marketing MCP, using your own Bloomreach login. Requires Node/npx.

Both modes use Claude as the reasoning engine, so **an Anthropic API key is required either way.**

## Prerequisites

- **Python 3.11**
- **An Anthropic API key** — required for both modes
- **Node.js / npx** — only for `--live` (runs the MCP bridge)
- **A Bloomreach login with sandbox access** — only for `--live`

## Setup

1. Clone and enter the repo:
   ```
   git clone https://github.com/kellyorkin/datadrovers.git
   cd datadrovers
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set your Anthropic key as the environment variable `ANTHROPIC_KEY_SCOPE_SCOUT`:
   - **Windows (PowerShell):** `setx ANTHROPIC_KEY_SCOPE_SCOUT "sk-ant-..."` — then open a **new** terminal (`setx` does not affect the current one).
   - **macOS / Linux:** `export ANTHROPIC_KEY_SCOPE_SCOUT="sk-ant-..."` (add to your shell profile to persist).

   > Never commit your key. `.env` is gitignored; keep the key in the environment variable only.

## Run

- **Reasoning console (recommended):**
  ```
  python -m scope_scout.web
  ```
  Open http://127.0.0.1:5000, enter a client trigger list, and watch the reasoning trace build the discovery agenda. (Local-knowledge mode.)

- **Command line:**
  ```
  python -m scope_scout.cli            # runs a sample brief
  python -m scope_scout.cli --repl     # interactive, multi-turn
  ```

- **Live workspace:** add `--live`:
  ```
  python -m scope_scout.web --live
  ```
  The first `--live` run opens a browser to log into Bloomreach (OAuth via `mcp-remote`); the token is cached afterward, so later runs are browser-free. Requires Node/npx.

## Notes

- The Loomi Connect Marketing MCP is rate-limited to ~1 request/second; the runtime paces itself, so `--live` runs are intentionally a little slower.
- The hosted demo at [datadrovers.com/sawyer](https://datadrovers.com/sawyer) serves fixture data only — running `--live` locally is the only path to a real workspace.
- All workspace access is read-only by design.
