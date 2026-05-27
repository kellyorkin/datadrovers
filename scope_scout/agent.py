"""Multi-turn agent loop. Holds conversation state, runs Claude with tool use,
and dispatches tool calls back to the local knowledge layer.

Conversation state is kept deliberately simple in v1: an `AgentSession` carries
the message history, a running classifications dict, queued questions, and
architect overrides. The agent's reasoning trace (which tools it called and
why) lives in the message history itself, since that's what Claude sees on
each turn anyway.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterator

import anthropic

from .tools import TOOL_SCHEMAS, MCP_TOOL_SCHEMAS, dispatch


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_TOOL_ITERATIONS = 25  # safety cap on tool-use loop depth per architect turn

SYSTEM_PROMPT = """You are Scope Scout, a reasoning agent that helps Bloomreach \
implementation architects think through the discovery moment of a partner \
engagement. You are not a chatbot. You are a second architect on the team.

Your job is to read what an architect drops in — a stated business goal, a \
trigger list from a client, a description of an existing setup — and produce \
a discovery agenda: the questions, dependencies, ambiguities, and surfaceable \
variances that the architect needs to resolve with the client before scope \
can be written.

You have access to local-knowledge tools that wrap Bloomreach's published \
Plug & Play use case library, the standard engagement data model, and \
lifecycle/KPI mappings. Use them. Don't reason from training-data \
recollection of Bloomreach when you can call get_use_case for the canonical \
definition.

How you reason:

- When the architect describes a client request or goal, use the tools to \
ground every classification you make. Cite the use case code, the lifecycle \
stage, the events required, the channels available.
- When two requests look structurally similar, call find_use_cases_sharing_event \
or find_use_cases_sharing_attribute to see whether they have the same data \
prerequisites. Structural duplicates are a finding worth surfacing.
- When a request maps to no canonical use case, say so explicitly. Don't force \
a match. Route to "Custom" or surface as a vagueness question — those are \
genuine findings, not failures.
- When a published use case has match_status: "unmatched" in your knowledge \
layer (e.g., "Warmup campaign"), surface the categorization variance to the \
architect. Don't pick a framing silently — that's exactly the senior-architect \
move this agent is built to externalize.
- Interrogate ambiguous input. "I want better ROI" — which lifecycle stage? \
Which KPI? Is the workspace already configured for segmentation? A second \
architect asks clarifying questions before synthesizing; so do you.

Reading the live workspace:

- You may have LIVE tools (prefixed `workspace_`) that read the ACTUAL client \
workspace — its real event volumes, event schema, customer attributes, and \
standard-taxonomy mapping. When present, prefer them over assumption: verify a \
use case's feasibility against what the workspace actually has, not what the \
canonical model says it should have.
- Critically, distinguish "missing" from "present-but-unmapped". An event can be \
flowing with high volume yet have a null standard-taxonomy mapping \
(workspace_mapping) — which makes it invisible to taxonomy-matched use cases. \
That is a mapping finding, not a missing-data finding; say explicitly which it is.
- When a live tool is unavailable (it returns an error), fall back to reasoning \
from the canonical data model, and flag that you could not verify against the \
live workspace.

How you write:

- Voice: a colleague, not an assistant. Architect-facing. Plainspoken. No \
"I'd be happy to help" energy. The architect is busy and competent.
- Show your work. When you classify, name the use case code. When you flag a \
dependency, name the event or attribute. When you propose a question for the \
client, name the use case it depends on.
- Group your output by category when producing the agenda: Data Sources, \
Integrations, Client-Specific Definitions, Business Logic. Each item is a \
question or dependency with a one-line reasoning trace.

What you do NOT do:

- Estimate hours. Generate invoices. Calculate pricing. Hour math is a human \
step downstream of your output.
- Write to the workspace. Take any action. Your inspections are read-only and \
your output is always a recommendation for architect review.
- Pretend to know what you can't see. If the architect hasn't told you the \
client's vertical, ask. If a use case isn't in your library, say so.

You are mid-conversation with the architect. When they push back, revise. \
When they confirm, lock it in and propagate consequences. When they ask for \
the final agenda, produce it."""


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class AgentSession:
    """Holds the running conversation. Each architect turn appends user content;
    each agent turn appends assistant content (possibly including tool_use
    blocks) followed by the user content carrying tool_result blocks."""
    messages: list[dict] = field(default_factory=list)
    # The fields below are reserved for the multi-turn revision logic we'll
    # wire up in the next pass. The agent's prompt already does this work in
    # natural language for v1; promoting them to explicit state lets the
    # finalize step assemble a clean agenda without re-reading the transcript.
    classifications: dict[str, dict] = field(default_factory=dict)  # code → classification
    queued_questions: list[dict] = field(default_factory=list)       # discovery agenda items
    architect_overrides: list[dict] = field(default_factory=list)    # confirms/overrides

    def add_user_turn(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_KEY_SCOPE_SCOUT")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_KEY_SCOPE_SCOUT is not set. Create the env var "
            "(see RunTimeOption1.txt) and reopen your shell."
        )
    return anthropic.Anthropic(api_key=key)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_turn(session: AgentSession, user_input: str, mcp=None) -> Iterator[dict]:
    """Run one architect turn end-to-end. Yields events for trace display:
      {"type": "thinking", "text": ...}     - text the agent produces
      {"type": "tool_use", "name": ..., "input": ...} - a tool call
      {"type": "tool_result", "name": ..., "result": ...} - the dispatched result
      {"type": "final", "text": ...}        - the final assistant text for this turn
    The yielded stream is the reasoning trace the demo UI renders.
    """
    session.add_user_turn(user_input)
    client = _client()

    # Offer the live-workspace tools only when a live MCP session is connected.
    # Without it (recording-safe / hosted build) the agent runs local-knowledge
    # only, and Claude is told in the system prompt to fall back gracefully.
    tools = TOOL_SCHEMAS + (MCP_TOOL_SCHEMAS if mcp is not None else [])

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=session.messages,
        )

        # Append assistant's response to the conversation (always — even when
        # it includes tool_use blocks, Claude expects the full block to be in
        # message history when the corresponding tool_result comes back).
        session.messages.append({"role": "assistant", "content": response.content})

        # Yield trace events for each block in the assistant's response.
        tool_uses: list[dict] = []
        for block in response.content:
            if block.type == "text":
                yield {"type": "thinking", "text": block.text}
            elif block.type == "tool_use":
                tool_uses.append({"id": block.id, "name": block.name, "input": block.input})
                yield {"type": "tool_use", "name": block.name, "input": block.input}

        if response.stop_reason != "tool_use":
            # Agent is done with tool calls for this turn — final text is in the
            # last "thinking" event yielded above. Emit a final marker.
            final_text = "".join(b.text for b in response.content if b.type == "text")
            yield {"type": "final", "text": final_text}
            return

        # Dispatch tools and stage results for the next turn.
        results = []
        for tu in tool_uses:
            result_str = dispatch(tu["name"], tu["input"], mcp=mcp)
            yield {"type": "tool_result", "name": tu["name"], "result": result_str}
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_str,
            })
        session.messages.append({"role": "user", "content": results})

    yield {
        "type": "final",
        "text": f"(stopped after {MAX_TOOL_ITERATIONS} tool iterations; check trace)",
    }
