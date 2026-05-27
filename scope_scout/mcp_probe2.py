"""Probe #2 — discovery. Confirms the token reads REAL data and captures what we
need to call the introspection tools correctly:
  - whoami            -> proves the session is authenticated as a real user
  - list_cloud_organizations / list_workspaces / list_projects -> find neon-sock's ID
  - input schemas for the introspection tools we plan to wire -> exact param names

No agent code involved. Token is already cached in ~/.mcp-auth, so no browser this run.
"""

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOOMI_MCP_URL = "https://loomi-mcp-alpha.bloomreach.com/mcp"
NPX = "npx.cmd" if os.name == "nt" else "npx"

server = StdioServerParameters(command=NPX, args=["-y", "mcp-remote", LOOMI_MCP_URL])

# The tools we expect to wire — we want to see their input schemas (required args).
INTROSPECTION_TOOLS = [
    "get_project_overview",
    "get_event_schema",
    "get_customer_property_schema",
    "get_customer_schema",
    "get_mapping",
    "list_projects",
    "list_workspaces",
]

# Navigation/auth calls to actually execute (these take no or simple args).
CALLS = [
    ("whoami", {}),
    ("list_cloud_organizations", {}),
    ("list_workspaces", {}),
    ("list_projects", {}),
]


def text_of(result) -> str:
    """MCP tool results come back as content blocks; pull the text out."""
    parts = []
    for block in result.content:
        parts.append(getattr(block, "text", str(block)))
    return "".join(parts)


async def main() -> None:
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            by_name = {t.name: t for t in listing.tools}

            print("=== INPUT SCHEMAS (required args per tool) ===")
            for name in INTROSPECTION_TOOLS:
                t = by_name.get(name)
                if not t:
                    print(f"- {name}: (NOT FOUND)")
                    continue
                schema = t.inputSchema or {}
                props = list((schema.get("properties") or {}).keys())
                req = schema.get("required") or []
                print(f"- {name}: required={req}  all_params={props}")

            print("\n=== LIVE CALLS ===")
            for name, args in CALLS:
                if name not in by_name:
                    print(f"\n## {name}: (NOT FOUND, skipping)")
                    continue
                try:
                    res = await session.call_tool(name, arguments=args)
                    body = text_of(res)
                    flag = " [isError]" if getattr(res, "isError", False) else ""
                    print(f"\n## {name}{flag} ({len(body)} chars):")
                    print(body[:1800])
                except Exception as e:
                    print(f"\n## {name}: EXCEPTION {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
