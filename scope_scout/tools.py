"""Tool definitions for the agent's local-knowledge surface.

`TOOL_SCHEMAS` is the list passed to Claude's `tools` parameter. `dispatch()`
takes a tool name + input dict from a Claude `tool_use` block and returns the
result string Claude will see in the next turn's `tool_result`.

The surface is intentionally small but deep: each tool returns rich relational
context (channels, lifecycle stage, data requirements bundled together) rather
than a thin shallow lookup. Keeps the agent's prompt simple and gives Claude
room to reason instead of orchestrating five lookups for one question.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from . import knowledge as k


# ---------------------------------------------------------------------------
# Tool schemas (the contract Claude sees)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_use_cases",
        "description": (
            "Return a light listing (code, name, family, impact) of Bloomreach's "
            "published Plug & Play use cases. Use this for browsing by family "
            "or getting an overview. For full details of one use case, call "
            "get_use_case instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "family": {
                    "type": "string",
                    "description": (
                        "Optional filter by use case family (e.g., 'Analytics & "
                        "Dashboards', 'Orchestration (Email/Multichannel)', 'Web Layer')."
                    ),
                },
            },
        },
    },
    {
        "name": "get_use_case",
        "description": (
            "Return the full bundled entry for one use case by 4-letter code: "
            "library metadata, lifecycle stage, data requirements (customer "
            "attributes, per-event attribute requirements, catalog field "
            "requirements), required events, required catalogs, and supporting "
            "channels. This is the agent's primary deep-dive tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "4-letter use case code (e.g., 'OABF', 'OWEF', 'ATAD').",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "search_use_cases",
        "description": (
            "Loose case-insensitive substring search across use case names. "
            "Use this when the architect's wording doesn't match a code (e.g., "
            "search_use_cases('abandoned') returns all abandoned-* variants). "
            "Returns light hits; follow up with get_use_case for full detail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring to search for (case-insensitive).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_use_cases_by_lifecycle_stage",
        "description": (
            "Return all use cases tagged to a lifecycle stage, together with "
            "the KPIs that stage impacts. Stages: 'Awareness', 'Interest', "
            "'Convert', 'Loyalty'. Use this when reasoning about which use "
            "cases serve a stated business goal (e.g., a stated goal of "
            "'reduce churn' maps to Loyalty stage)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {
                    "type": "string",
                    "description": "Awareness | Interest | Convert | Loyalty",
                },
            },
            "required": ["stage"],
        },
    },
    {
        "name": "find_use_cases_sharing_event",
        "description": (
            "Return all use cases whose data requirements include the given "
            "event. Critical for consequence-propagation reasoning: when a "
            "data feasibility gap is identified for one use case (e.g., "
            "'consent event not configured'), use this to identify which other "
            "use cases are also blocked by the same gap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_name": {
                    "type": "string",
                    "description": "Event name (e.g., 'consent', 'purchase', 'view_item').",
                },
            },
            "required": ["event_name"],
        },
    },
    {
        "name": "find_use_cases_sharing_attribute",
        "description": (
            "Return all use cases whose data requirements include the given "
            "customer attribute or event attribute (searched across all "
            "events). Use for consequence propagation across attribute gaps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "attribute_name": {
                    "type": "string",
                    "description": "Attribute name (e.g., 'email', 'product_id', 'consent_list').",
                },
            },
            "required": ["attribute_name"],
        },
    },
    {
        "name": "get_lifecycle_stages",
        "description": (
            "Return the full lifecycle stage → impacted KPIs map (light "
            "summary, no use case detail). Use this for orientation when "
            "reasoning about a stated business goal."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_event_definition",
        "description": (
            "Return the canonical definition of one Bloomreach event "
            "(description, type, tracking status) plus its full attribute "
            "dictionary. Use this when reasoning about whether a client "
            "request requires events beyond what's currently in the standard "
            "data model, or when surfacing event-attribute prerequisites."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_name": {
                    "type": "string",
                    "description": "Event name (e.g., 'consent', 'purchase', 'cart_update').",
                },
            },
            "required": ["event_name"],
        },
    },
]


# ---------------------------------------------------------------------------
# Live-workspace tools (Bloomreach Loomi MCP)
#
# These read the ACTUAL neon-sock workspace via the live MCP — ground truth,
# as distinct from the canonical-data-model tools above (which describe what
# Bloomreach's standard model *should* look like). They take no parameters from
# Claude's side: the workspace (neon-sock) is fixed and project_id is injected
# by the LoomiMCP wrapper. Each maps to a real MCP tool name.
# ---------------------------------------------------------------------------

MCP_TOOL_MAP: dict[str, str] = {
    "workspace_overview": "get_project_overview",
    "workspace_event_schema": "get_event_schema",
    "workspace_customer_attributes": "get_customer_property_schema",
    "workspace_mapping": "get_mapping",
}

MCP_TOOL_SCHEMAS: list[dict] = [
    {
        "name": "workspace_overview",
        "description": (
            "LIVE: a statistics snapshot of the actual client workspace (neon-sock) "
            "— total customers, total events, and per-event-type counts. Use this "
            "to see what data is ACTUALLY flowing, in what volume, rather than "
            "assuming. Ground truth, not the canonical model."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "workspace_event_schema",
        "description": (
            "LIVE: the actual event types and their attributes tracked in the "
            "client workspace right now. Compare against a use case's required "
            "events (from get_use_case) to verify feasibility against reality "
            "instead of assumption."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "workspace_customer_attributes",
        "description": (
            "LIVE: the actual customer attributes (properties) defined on profiles "
            "in the client workspace. Compare against a use case's required "
            "customer attributes to find real gaps (e.g. a missing birthday "
            "attribute blocking a Birthday Campaign)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "workspace_mapping",
        "description": (
            "LIVE: the workspace's mapping of tracked events to Bloomreach's "
            "standard event taxonomy. CRITICAL for feasibility reasoning: events "
            "can be flowing yet unmapped (event present, standard-taxonomy slot "
            "null), which makes them invisible to taxonomy-matched use cases. A "
            "null mapping with data present is a 'present-but-unmapped' finding, "
            "not a 'missing data' finding — surface the distinction."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------------------
# Access logging
#
# Every tool invocation is recorded at the "access" level: timestamp, tool
# name, the query parameters, the response size in bytes, and ok/error status —
# but NOT the response body. That gives an auditable record of what the agent
# touched (and, for live tools, that it touched the real workspace) without
# persisting any workspace data. Records go to stderr, scoped to the session;
# nothing is written to disk. The access tier is ALWAYS ON — it's the audit
# trail the responsible-design note relies on. A separate development-only tier
# (SCOPE_SCOUT_VERBOSE_LOG=1, off in every default config) adds full response
# bodies and full tracebacks — the complete picture, for debugging only.
# ---------------------------------------------------------------------------

VERBOSE_TOOL_LOG = os.environ.get("SCOPE_SCOUT_VERBOSE_LOG") == "1"

_access_log = logging.getLogger("scope_scout.access")
if not _access_log.handlers:
    _handler = logging.StreamHandler()  # stderr; not persisted to disk
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s scope_scout.access %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    _access_log.addHandler(_handler)
    _access_log.setLevel(logging.DEBUG if VERBOSE_TOOL_LOG else logging.INFO)
    _access_log.propagate = False


def _log_access(
    name: str, source: str, params: dict, result: str, *, ok: bool, started: float
) -> None:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    _access_log.info(
        "tool=%s source=%s params=%s bytes=%d status=%s ms=%d",
        name,
        source,
        json.dumps(params, ensure_ascii=False, default=str),
        len(result),
        "ok" if ok else "error",
        elapsed_ms,
    )
    if VERBOSE_TOOL_LOG:
        _access_log.debug("tool=%s response=%s", name, result)


# ---------------------------------------------------------------------------
# Dispatcher (called from the agent loop on each tool_use block)
# ---------------------------------------------------------------------------

def dispatch(name: str, params: dict[str, Any], mcp=None) -> str:
    """Run a tool call, return a JSON string Claude can read in tool_result.

    `mcp` is an optional live LoomiMCP session. Live-workspace tools route to it;
    if it's absent (e.g. the recording-safe / hosted build), they degrade to a
    clear error the agent can reason around rather than crashing.

    Every call is recorded by the access logger (see above) before returning.
    """
    started = time.monotonic()
    if name in MCP_TOOL_MAP:
        source = "live-mcp"
        if mcp is None:
            result = json.dumps(
                {"error": f"{name}: live workspace not connected in this build"}
            )
            ok = False
        else:
            result = mcp.read(MCP_TOOL_MAP[name])  # already a JSON string from the MCP
            ok = "error" not in result[:40].lower()
    else:
        source = "local"
        try:
            obj = _invoke(name, params)
            result = json.dumps(obj, ensure_ascii=False, default=str)
            ok = not (isinstance(obj, dict) and "error" in obj)
        except Exception as e:  # surface errors as tool_result content so the loop continues
            result = json.dumps({"error": f"{type(e).__name__}: {e}"})
            ok = False
            if VERBOSE_TOOL_LOG:  # dev-only: full traceback alongside the error body
                _access_log.debug("tool=%s raised", name, exc_info=True)
    _log_access(name, source, params, result, ok=ok, started=started)
    return result


def _invoke(name: str, p: dict[str, Any]) -> Any:
    if name == "list_use_cases":
        return k.list_use_cases(family=p.get("family"))
    if name == "get_use_case":
        result = k.get_use_case(p["code"])
        if result is None:
            return {"error": f"Unknown use case code: {p['code']!r}"}
        return result
    if name == "search_use_cases":
        return k.search_use_cases(p["query"])
    if name == "find_use_cases_by_lifecycle_stage":
        return k.find_use_cases_by_lifecycle_stage(p["stage"])
    if name == "find_use_cases_sharing_event":
        return k.find_use_cases_sharing_event(p["event_name"])
    if name == "find_use_cases_sharing_attribute":
        return k.find_use_cases_sharing_attribute(p["attribute_name"])
    if name == "get_lifecycle_stages":
        return k.get_lifecycle_stages()
    if name == "get_event_definition":
        result = k.get_event_definition(p["event_name"])
        if result is None:
            return {"error": f"Unknown event name: {p['event_name']!r}"}
        return result
    raise ValueError(f"Unknown tool: {name!r}")
