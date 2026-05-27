"""Knowledge layer: loads the nine JSON files in `data/` into in-memory
structures and exposes query helpers the agent's tool surface dispatches to.

The data files come from two sources:
  - BC's extracts (P&P library, lifecycle stages, channels, add-ons)
  - Code's extracts from the Tracking Document (customer attributes,
    planned events, event attributes, event matrix, data requirements)

All five matrix files are keyed by canonical 4-letter use case codes; lookups
that don't resolve are flagged with `match_status: "unmatched"` so the agent
can surface gaps for architect review.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Raw loaders (cached so each file is read once per process)
# ---------------------------------------------------------------------------

@cache
def _load(filename: str) -> dict[str, Any]:
    with (DATA_DIR / filename).open(encoding="utf-8") as f:
        return json.load(f)


def library() -> list[dict]:
    return _load("scope_scout_pnp_library.json")["use_cases"]


def lifecycle() -> list[dict]:
    return _load("scope_scout_lifecycle_stages.json")["stages"]


def channels() -> list[dict]:
    return _load("scope_scout_channels.json")["entries"]


def addons() -> dict:
    return _load("scope_scout_addons.json")


def customer_attributes() -> list[dict]:
    return _load("scope_scout_customer_attributes.json")["attributes"]


def planned_events() -> list[dict]:
    return _load("scope_scout_planned_events.json")["events"]


def event_attributes() -> list[dict]:
    return _load("scope_scout_event_attributes.json")["events_with_attributes"]


def event_matrix() -> list[dict]:
    return _load("scope_scout_event_matrix.json")["use_cases"]


def data_requirements() -> list[dict]:
    return _load("scope_scout_data_requirements.json")["use_cases"]


# ---------------------------------------------------------------------------
# Indexes (built once, derived from the raw structures)
# ---------------------------------------------------------------------------

@cache
def _by_code() -> dict[str, dict]:
    return {uc["code"]: uc for uc in library()}


@cache
def _drm_by_code() -> dict[str, dict]:
    return {uc["code"]: uc for uc in data_requirements() if uc.get("code")}


@cache
def _em_by_code() -> dict[str, dict]:
    return {uc["code"]: uc for uc in event_matrix() if uc.get("code")}


@cache
def _channels_by_code() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in channels():
        code = entry.get("code")
        if code:
            out.setdefault(code, []).append(entry)
    return out


@cache
def _stage_for_code() -> dict[str, str]:
    """Map use case code → lifecycle stage (Awareness/Interest/Convert/Loyalty)."""
    out: dict[str, str] = {}
    for stage in lifecycle():
        for uc in stage["use_cases"]:
            if uc.get("code"):
                out[uc["code"]] = stage["stage"]
    return out


# ---------------------------------------------------------------------------
# Query helpers (the tool surface dispatches to these)
# ---------------------------------------------------------------------------

def list_use_cases(family: str | None = None) -> list[dict]:
    """Return a light listing (code, name, family, impact) of all use cases,
    optionally filtered by family."""
    items = library()
    if family:
        items = [uc for uc in items if uc.get("family", "").lower() == family.lower()]
    return [
        {"code": uc["code"], "name": uc["name"], "family": uc.get("family"), "impact": uc.get("impact")}
        for uc in items
    ]


def get_use_case(code: str) -> dict | None:
    """Full bundled entry for one use case: library metadata + DRM + Event
    Matrix + channels + lifecycle stage. Returns None if the code is unknown.
    """
    base = _by_code().get(code)
    if not base:
        return None
    drm = _drm_by_code().get(code, {})
    em = _em_by_code().get(code, {})
    return {
        **base,
        "lifecycle_stage": _stage_for_code().get(code),
        "data_requirements": {
            "customer_attributes": drm.get("required_customer_attributes", []),
            "event_attributes": drm.get("required_event_attributes", {}),
            "catalog_fields": drm.get("required_catalog_fields", {}),
        },
        # Per architectural decision: prefer DRM event keys (denser, more reliable)
        # over Event Matrix's required_events for "what events does this need".
        "required_events": sorted((drm.get("required_event_attributes") or {}).keys()),
        "required_catalogs": em.get("required_catalogs", []),
        "channels": _channels_by_code().get(code, []),
    }


def find_use_cases_by_lifecycle_stage(stage: str) -> list[dict]:
    """Return use cases tagged to a lifecycle stage (Awareness/Interest/Convert/Loyalty),
    with their impacted KPIs from the stage definition."""
    for s in lifecycle():
        if s["stage"].lower() == stage.lower():
            return {
                "stage": s["stage"],
                "impacted_kpis": s.get("impacted_kpis", []),
                "use_cases": s["use_cases"],
            }
    return {"stage": stage, "impacted_kpis": [], "use_cases": []}


def find_use_cases_sharing_event(event_name: str) -> list[dict]:
    """Return all use cases whose data requirements include the given event.
    Critical for consequence-propagation reasoning: 'if consent isn't configured,
    which other use cases are also blocked?'
    """
    out = []
    for uc in data_requirements():
        if not uc.get("code"):
            continue
        if event_name in (uc.get("required_event_attributes") or {}):
            out.append({"code": uc["code"], "name": uc["name"]})
    return out


def find_use_cases_sharing_attribute(attribute_name: str) -> list[dict]:
    """Return all use cases whose data requirements include the given customer
    attribute or event attribute (searched across all events)."""
    out = []
    for uc in data_requirements():
        if not uc.get("code"):
            continue
        if attribute_name in uc.get("required_customer_attributes", []):
            out.append({"code": uc["code"], "name": uc["name"], "where": "customer_attribute"})
            continue
        for event, attrs in (uc.get("required_event_attributes") or {}).items():
            if attribute_name in attrs:
                out.append({"code": uc["code"], "name": uc["name"], "where": f"event:{event}"})
                break
    return out


def get_lifecycle_stages() -> list[dict]:
    """Return the full lifecycle stage → impacted KPIs → use cases map."""
    return [
        {
            "stage": s["stage"],
            "impacted_kpis": s.get("impacted_kpis", []),
            "use_case_count": len(s["use_cases"]),
        }
        for s in lifecycle()
    ]


def search_use_cases(query: str) -> list[dict]:
    """Loose name search across the library. Case-insensitive substring match.
    Returns lightweight hits (code, name, family) for the agent to follow up on."""
    q = query.lower().strip()
    if not q:
        return []
    hits = []
    for uc in library():
        if q in uc["name"].lower():
            hits.append({"code": uc["code"], "name": uc["name"], "family": uc.get("family")})
    return hits


def get_event_definition(event_name: str) -> dict | None:
    """Return the planned event entry (description, type, tracking status) plus
    its attribute dictionary."""
    pe = next((e for e in planned_events() if e["name"] == event_name), None)
    if not pe:
        return None
    ea = next((e for e in event_attributes() if e["event"] == event_name), None)
    return {
        **pe,
        "attributes": ea["attributes"] if ea else [],
    }
