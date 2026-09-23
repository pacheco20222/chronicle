# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React 19 + Vite + Tailwind v4 + shadcn/radix-ui + @react-three/fiber/drei/postprocessing/three, served as static assets by mnemo's own FastMCP streamable-HTTP process (`mnemo dashboard`). Already decided and scaffolded in `dashboard/` before this file was written — not a greenfield stack choice.

## Users
[Inferred — user said proceed without an interview round.] The maintainer/operator of a self-hosted mnemo install: a developer running Claude Code, Cursor, or Codex across multiple local repos, who registered several projects with mnemo and wants to see what's actually stored — browse memories per project, see how they relate, and eyeball the health of the local Qdrant/MCP processes. Same audience as the existing `mnemo graph` CLI and `mnemo` MCP tools generally: technical, comfortable with a terminal, running everything on their own machine. Not a multi-tenant or public-facing audience — the dashboard binds to localhost only, by design.

## Product Purpose
[Inferred from README.md and this session's decisions.] Mnemo is a self-hosted, project-scoped memory MCP server ("no cloud services, no paid APIs — everything runs on your own machine") that gives AI coding agents persistent memory across sessions, hard-scoped per project. The dashboard is a new visualization/control surface for that memory store: a live, browsable view of every registered project's memories and their relationships (semantic similarity + explicit typed links), replacing the need to run the one-shot `mnemo graph` CLI export to see the graph. Success = the operator can open the dashboard, immediately see which project's memory is healthy/current, drill into any project's graph, and trust that nothing here talks to the network beyond their own machine.

## Positioning
[Inferred.] Unlike a hosted "AI memory" SaaS product, mnemo's mechanism is: single local Qdrant collection, local embedding inference (fastembed, no external API calls), strict per-project isolation enforced server-side, and now a dashboard that is itself just another local MCP client over HTTP — no new backend, no new data model, no cloud dependency introduced by adding a UI.

## Operating Context
Launched via `uv run mnemo dashboard start` (foreground) or `--background` (persistent local process, PID-tracked under `~/.mnemo/dashboard.pid`), stopped via `mnemo dashboard stop`. Runs alongside Qdrant (Docker container) and any number of per-session stdio MCP processes (`uv run mnemo`) that Claude Code/Cursor/Codex sessions spawn. The operator is typically also mid-coding-session in one of those tools while glancing at the dashboard — a monitoring/reference surface, not the primary workspace.

## Capabilities and Constraints
- Localhost-only (`127.0.0.1`), hardcoded, not configurable — confirmed in code, this session's explicit security decision.
- No auth layer — acceptable only because it never leaves the operator's machine.
- Reuses existing server-side logic (`_build_graph_data` project isolation/cross-project/min-similarity, `relations` typed-edge data) rather than duplicating it — the dashboard must not drift from what the CLI graph and MCP tools already compute.
- Two edge kinds must stay visually distinct: semantic-similarity (KNN) edges vs. explicit typed relation edges (`related_to`/`supersedes`/`caused_by`/`blocked_by`/`implements`).
- Node taxonomy: memory `type` (decision/architecture/bug/todo/note/checkpoint/overview) and `status` (active/resolved/superseded) — both must remain visually legible, not just color-coded decoration.
- Control tab must stay lightweight — sampled on demand, not continuously polled, to avoid meaningful RAM/CPU overhead on the operator's machine.
- Currently a functional scaffold only (Codex-built, verified working end-to-end: builds, tests pass, MCP endpoint responds) with no visual design pass yet — this is genuinely a first visual pass, not a redesign of an existing look.

## Brand Commitments
Product name is "Mnemo." No logo, no established color palette, no marketing site — a developer tool distributed as a GitHub repo + Claude Code plugin. Explicit, repeated instruction (this session): do not visually copy the reference tool codebase-memory-mcp's `graph-ui` (teal-on-dark) — use a distinct palette, reference its structure/patterns only.

## Evidence on Hand
- Reference implementation for structural/UX patterns (tabs, project cards, control panel, graph interaction model): github.com/DeusData/codebase-memory-mcp, `graph-ui` subdirectory — evidence for mechanism, explicitly anti-reference for color/visual identity.
- Existing precedent inside this repo: `mnemo graph` CLI (`src/mnemo/graph_cli.py`) already renders a 3D orbitable similarity graph (gold ring = core memory, diamond = latest checkpoint) — establishes some existing visual vocabulary worth knowing even though it's a separate, simpler static-HTML renderer, not the same codebase as `dashboard/`.
- No real user research, no screenshots of a finished dashboard, no existing DESIGN.md.

## Product Principles
1. Never let the dashboard's visuals imply data the underlying store doesn't have — no fabricated metrics, no decorative "activity" that isn't real.
2. The dashboard is a lens onto mnemo's actual data model (memories, types, statuses, two edge kinds), not a generic graph-explorer skin — visual choices should make that model legible, not abstract it away.
3. Stay lightweight: this runs on the operator's own machine alongside their actual dev work; resource cost is a real constraint, not a nice-to-have.
4. Local-only, no-cloud is core identity, inherited from mnemo itself — nothing in the dashboard should read as "phoning home," even cosmetically (no fake network activity indicators, etc.).
5. Distinct from, not derivative of, the reference tool's look — same category of app, different visual identity.

## Accessibility & Inclusion
[Not established — no product-specific requirement confirmed yet.]
