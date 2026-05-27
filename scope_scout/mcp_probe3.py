"""Probe #3 — walk org -> workspace(neon-sock) -> project, then read the live
schema/mapping for that project. This reproduces the neon-sock inventory findings
(events, attributes, mapping state) LIVE instead of from the static doc.

Respects the MCP's rate limit (1 request / second / user) by pacing every call.
Does NOT call whoami (its body contains the access token — keep it out of logs).
"""

import asyncio
import json
import os
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOOMI_MCP_URL = "https://loomi-mcp-alpha.bloomreach.com/mcp"
NPX = "npx.cmd" if os.name == "nt" else "npx"
PACE_SECONDS = 1.2  # > the 1 req/sec server limit

server = StdioServerParameters(command=NPX, args=["-y", "mcp-remote", LOOMI_MCP_URL])


def text_of(result) -> str:
    return "".join(getattr(b, "text", str(b)) for b in result.content)


async def call(session, name, args, *, retries=2):
    """Paced tool call with a read timeout and retry on rate-limit OR stream drop."""
    for attempt in range(retries + 1):
        await asyncio.sleep(PACE_SECONDS)
        try:
            res = await session.call_tool(
                name, arguments=args, read_timeout_seconds=timedelta(seconds=30)
            )
        except Exception as e:  # SSE drop / timeout — retry on a fresh attempt
            if attempt < retries:
                await asyncio.sleep(1.5)
                continue
            return True, f"EXCEPTION {type(e).__name__}: {e}"
        body = text_of(res)
        if getattr(res, "isError", False) and "Too many requests" in body and attempt < retries:
            await asyncio.sleep(1.5)
            continue
        return getattr(res, "isError", False), body
    return True, body


def find(items, substr, key_candidates=("id", "workspace_id", "project_id", "token")):
    """Find the first dict whose name/slug contains substr; return (id, dict)."""
    for it in items:
        blob = json.dumps(it).lower()
        if substr in blob:
            for k in key_candidates:
                if k in it:
                    return it[k], it
    return None, None


def as_list(body):
    try:
        data = json.loads(body)
    except Exception:
        return None
    if isinstance(data, list):
        return data
    for v in data.values() if isinstance(data, dict) else []:
        if isinstance(v, list):
            return v
    return None


async def main() -> None:
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Cloud organizations
            err, body = await call(session, "list_cloud_organizations", {})
            print(f"## list_cloud_organizations (err={err}):\n{body[:1200]}\n")
            orgs = as_list(body) or []
            if not orgs:
                print("No orgs parsed — stopping.")
                return
            org_id = orgs[0].get("id") or orgs[0].get("cloud_organization_id")
            print(f">>> using cloud_organization_id = {org_id}\n")

            # 2. Workspaces -> find neon-sock
            err, body = await call(session, "list_workspaces", {"cloud_organization_id": org_id})
            print(f"## list_workspaces (err={err}):\n{body[:1500]}\n")
            ws_id, ws = find(as_list(body) or [], "neon")
            print(f">>> neon-sock workspace_id = {ws_id}\n")

            # 3. Projects in that workspace -> find neon-sock project
            args = {"cloud_organization_id": org_id}
            if ws_id:
                args["workspace_id"] = ws_id
            err, body = await call(session, "list_projects", args)
            print(f"## list_projects (err={err}):\n{body[:1500]}\n")
            proj_id, proj = find(as_list(body) or [], "neon")
            if not proj_id:
                lst = as_list(body) or []
                proj_id = (lst[0].get("id") or lst[0].get("project_id")) if lst else None
            print(f">>> neon-sock project_id = {proj_id}\n")
            if not proj_id:
                print("No project_id — stopping before schema reads.")
                return

            # 4. Live introspection reads
            for tool in ("get_project_overview", "get_event_schema",
                         "get_customer_property_schema", "get_mapping"):
                err, body = await call(session, tool, {"project_id": proj_id})
                print(f"## {tool} (err={err}, {len(body)} chars):\n{body[:2500]}\n")


if __name__ == "__main__":
    asyncio.run(main())
