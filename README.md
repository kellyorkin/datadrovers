# Scope Scout

> An agentic assistant for Bloomreach SI partner solution architects at the pre-implementation scoping moment.

**Submitted to:** Loomi Connect AI Hackathon, Track 2 (Engagement Intelligence & Workspace Diagnostics).
**Demo:** [datadrovers.com/sawyer](https://datadrovers.com/sawyer)
**Submission deadline:** Tuesday, June 2, 2026 (4 PM PST)
**Demo day:** Thursday, June 4, 2026

---

## What this is

Scope Scout reads a client's stated trigger list (the messy mix of "wants," "doesn't have yet," and "we have something like X" that arrives at the start of a Bloomreach engagement) and produces a structured discovery agenda. It matches each request against the published Plug & Play library, probes the live client workspace through the Loomi Connect Marketing MCP, and identifies gaps in four categories: missing events, missing attributes on existing events, integration constraints, and mapping ambiguities. Every classification cites its evidence and its source. The architect reviews; Scope Scout proposes.

The agent in the demo is named **Sawyer**. Same project. Sawyer is the colleague-facing identity.

## Who it's for

Solution architects at Bloomreach SI partners, at the specific moment of receiving a client's stated trigger list and producing a scoping artifact for client review. Junior architects benefit most; senior architects benefit by being freed from the part of scoping that is pattern-matching rather than judgment.

## What's in this repo

```
datadrovers/
├── scope_scout/       Agent runtime (Python + Anthropic API + Loomi MCP)
├── sawyer.html        Deployed demo artifact (fixture-driven)
├── index.html         Landing page (datadrovers.com)
├── LOGO_B64.png       Logo asset
├── requirements.txt   Python dependencies for the agent
├── README.md          This file
└── .gitignore
```

The `scope_scout/` directory contains the live agent runtime: an agentic reasoning loop bounded at 25 tool iterations, cross-referencing local knowledge (a normalized representation of the Bloomreach P&P library) against live workspace state retrieved through the Loomi Connect Marketing MCP. The runtime uses Anthropic's `claude-sonnet-4-6` as the reasoning engine and the official `mcp` Python client for live workspace introspection.

`sawyer.html` is the demo artifact deployed at [datadrovers.com/sawyer](https://datadrovers.com/sawyer). It runs with fixture data so the demo is reproducible without rate-limit concerns or workspace access. The live runtime in `scope_scout/` makes real MCP calls when run locally with credentials.

## How it works

Two structured knowledge sources joined by agentic reasoning:

- **Local knowledge** ("what should be true"): the Plug & Play use case library (72 use cases), event matrix, data requirements per use case, channels, lifecycle stages, and add-ons. Pre-normalized into JSON; no external calls required.
- **Live workspace** ("what is true"): the Loomi Connect Marketing MCP, with introspection tools for project overview, event schema, taxonomy mapping, and customer attributes. Read-only by design.

The agent batches multiple tool calls into a single reasoning step (visible in the trace) and serializes execution against the live workspace at approximately one request per second for safety. The discovery agenda is the diff between what each matched use case requires and what the workspace actually has.

For architecture detail, see the Architecture Overview diagram in the submission materials.

## Responsible design

All agent actions against the workspace are read-only. The agent does not write, modify, configure, or send. The discovery agenda is a recommendation for architect review; the architect owns the output. Reasoning is fully traced and visible to the architect. Demo configuration serves fixture data only and makes no live MCP calls. Credentials are read from environment variables and never logged. Every tool invocation emits a structured access line to server-side `stderr` (no payloads, no credentials, no PII). The full Responsible Design Note is in the submission materials.

## Team

**The Scope Scouts:**

- **Kelly Brady** (Ansira), architect, lead, coordinator
- **Andy Daniels** (Amalgamation Services), MarTech direction, demo face
- **Multi-AI Ensemble** (Claude Suite), coordinated by Kelly Brady:  Cowork (strategy/synthesis), Claude Code (runtime/architecture), Claude.ai (creative direction/UI), Microsoft Copilot Studio (visual identity)*
  
*The ensemble pattern is on-thesis for the hackathon: agentic infrastructure coordinated by a human architect, with each surface bringing distinct capabilities to the same project.

## Submission materials

The submission documents (Project Summary, Architecture Overview, MCP Usage Explanation, Responsible Design Note) are submitted directly via the Hackathon portal. The repo here is the working code and the deployed demo; the submission portal is the canonical reference for the doc set.

## License

To be determined post-hackathon. Source is visible for hackathon-judging purposes.

---

*Repo maintained by Kelly Brady.*
