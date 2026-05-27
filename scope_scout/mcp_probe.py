"""One-off smoke test: connect to the Bloomreach Loomi MCP and list its tools.

What this proves, in one run:
  1. The OAuth handshake works (a browser opens for your one-time login).
  2. The token we get back actually authorizes the MCP's tools.
  3. We see the real tool surface — names + descriptions — for the first time.

How it connects (Cole's bridge approach):
  - We spawn `npx -y mcp-remote <URL>` as a child process. `mcp-remote` does the
    entire OAuth dance (dynamic registration, PKCE, browser login, token cache in
    ~/.mcp-auth) and exposes the remote server to us over plain stdio.
  - We talk to that child over stdio using the standard `mcp` Python client.
  Nothing here touches the agent loop — it's a standalone probe.
"""

import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOOMI_MCP_URL = "https://loomi-mcp-alpha.bloomreach.com/mcp"

# On Windows the executable is `npx.cmd`, not `npx`. Pick the right one so the
# subprocess actually launches.
NPX = "npx.cmd" if os.name == "nt" else "npx"

server = StdioServerParameters(
    command=NPX,
    args=["-y", "mcp-remote", LOOMI_MCP_URL],
)


async def main() -> None:
    print(f"Spawning bridge:  {NPX} -y mcp-remote {LOOMI_MCP_URL}")
    print("First run downloads mcp-remote and opens a browser for login. Waiting...\n")

    # stdio_client launches the subprocess; (read, write) are the pipes we use
    # to speak the MCP protocol to it.
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            # Blocks here until the OAuth login completes in the browser.
            await session.initialize()

            result = await session.list_tools()
            print(f"=== Connected. {len(result.tools)} tools exposed ===\n")
            for t in result.tools:
                desc = (t.description or "").replace("\n", " ").strip()
                print(f"- {t.name}: {desc[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
