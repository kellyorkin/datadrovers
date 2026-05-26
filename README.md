# Scope Scout: Workspace Orientation

**Project:** Scope Scout, an agentic assistant for Bloomreach SI partner solution architects at the pre-implementation scoping moment. Submitted to the Loomi Connect AI Hackathon, Track 2 (Engagement Intelligence & Workspace Diagnostics).

**Team (The Scope Scouts):**

- **Kelly Brady** (Ansira): architect, lead, human coordinator
- **Andy Daniels** (Amalgamation Services): demo face, MarTech director credibility
- **Cole** (Claude via Cowork): strategic advisor, holds long context, briefs and decisions
- **BC** (Claude in Chrome): data extraction, creative direction, JSON normalization, landing page
- **Code** (Claude Code): technical implementer, agent code, lead architect for the build
- **MarTy** (Microsoft Copilot Studio agent): visual identity, satirical and conversational register

**Key dates:**

- Kickoff Ceremony: Tuesday, May 26, 2026
- Final Submission: Tuesday, June 2, 2026 (4 PM PST)
- Demo Day: Thursday, June 4, 2026

---

## What lives where

**This workspace folder (`Implementation Documents/`)** holds the source materials, scrubbing-and-extraction work, planning docs, and the team's canonical reference set. The .xlsx and .docx files are the original Bloomreach / Ansira reference materials (scrubbed of client and IP-sensitive content). The .md files are working planning docs.

**`JSON Files/` (subdirectory)** holds the extracted structured knowledge that the agent reasons over. Built by BC (use case library, channels, lifecycle stages, add-ons) and Code (customer attributes, planned events, event attributes, event matrix, data requirements). Code-keyed for deterministic joins across files.

**`scope_scout/` (subdirectory, Code's working directory)** holds the agent runtime code. Python, custom state management, Anthropic API for reasoning, official `mcp` client for Marketing MCP calls. Will become its own GitHub repo when Code surfaces it.

**`extract_tracking_doc.py`** is Code's extraction script that produces the five Tracking Document JSONs. Re-runnable for reproducibility.

**`datadrovers.com` (external)** is the team's public-facing domain. Hosted on Netlify, landing page built by BC. Separate repo from the agent code.

---

## What to read first

If you're new to the project (or you're a fresh AI surface picking up context), read in this order:

1. **`Scope Scout - Project Summary (draft v1).md`**: what the project is, who it's for, what it does. (Note: draft v1, somewhat stale post-delta; v2 needed before final submission.)

2. **`The Scope Scout reasoning loop.docx`**: the agent's reasoning architecture, five-pass model, concrete examples.

3. **`Code_Brief_Scope_Scout_Delta.docx`**: the weekend's architectural shifts (discovery agenda not scoping artifact, multi-turn not one-shot, MCP scope clarified, hybrid input). **Where this disagrees with the Project Summary, the Delta is current.**

4. **`Scope Scout - Known Gaps and Open Items.md`**: the gaps tracker. Current status of every open item, what's resolved, what's parked, what's been decided.

5. **`Scope Scout - Code Engagement Brief (draft v1).md`**: the brief that handed Code into the project. Useful context for any new surface joining the technical build.

---

## Current status (as of May 26, 2026 kickoff)

**Done:**

- Hackathon registration submitted (team: The Scope Scouts).
- Document scrubbing pass complete (Project Scope Sample, Process Documentation, Example Client Trigger Use Cases, Tracking Document).
- BC built and normalized four knowledge JSONs (library, channels, lifecycle stages, add-ons).
- Code extracted Tracking Document into five additional JSONs (customer attributes, planned events, event attributes, event matrix, data requirements).
- Project Summary draft v1 written.
- Code engagement brief written.
- Architectural decisions settled: discovery agenda (not scoping artifact) output, multi-turn (not one-shot) interaction, local knowledge tools (not custom MCP server), Marketing MCP for customer-level workspace probing, agent runtime is Claude API + custom Python state, existing-client-expansion fixture pattern.

**In progress:**

- BC building datadrovers.com landing page (Netlify).
- Code scaffolding the agent runtime in `scope_scout/`.
- Fixture design (three personas, each triggering one MCP probe pattern), scheduled for Wednesday morning.

**Open:**

- Project Summary v2 (reflecting the delta).
- Architecture Overview diagram (required for final submission).
- Demo video recording (after build is functional).
- Fold `aa_READ_ME.docx` content into Process Documentation as Step 4.

---

## How the team works

Multi-AI ensemble pattern. Kelly is the human coordinator running the pattern across surfaces; each AI surface has a specialized role. Hand-offs are structured: brief in, predictable deliverable out, push back when reasoning supports it, escalate architectural disagreements to Kelly rather than silently deferring.

For the playful version of how this team works, see the Corporate Courtroom card "The Claude Suite — Expert Witnesses (Universal)" in Kelly's broader card universe.

---

*If anything in this file is out of date, update it. The README is the orientation surface for the project; staleness here costs more than staleness in any other doc.*
