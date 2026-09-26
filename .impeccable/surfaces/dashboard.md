---
version: 1
slug: "dashboard"
primary_target: "dashboard"
related_targets: []
---

# Dashboard surface brief

Scope: `dashboard/` — the chronicle web dashboard (Graph / Projects / Control tabs), Operate mode.
Audience: the operator of a self-hosted chronicle install — a developer running Claude Code/Cursor/Codex across local repos, checking on their own memory store. Localhost-only, no auth, single user.
Job/task: browse memories per project, understand how they relate (semantic similarity + explicit typed links), confirm the local stack (Qdrant, MCP processes) is healthy, at a glance, without burning CPU/RAM.
Proof/content: real data only — memory counts, types, statuses, edges, Qdrant/process stats. No fabricated activity or metrics.
Constraints: graph composition is user-pinned (dense glowing radial network, per reference image) — not open for reinterpretation. Palette must be distinct from the reference tool codebase-memory-mcp's teal-on-dark. Must stay visually legible for its actual data model (memory type, status, two edge kinds), not just decorative.

## Direction contract

THESIS: The dashboard reads chronicle's memory store the way a navigator reads a star chart — each memory a plotted point, its relationships the traced lines between them — refusing the generic "AI graph cloud" default (undifferentiated glowing points, no legible structure) that the category, including the very tool this dashboard is modeled on, always ships.

OWN-WORLD: Near-black deep-indigo chart ground (the dominant field, ~70%+ of visual weight) with a faint star-field texture. Warm gold/brass is the single accent — selection rings, active toggles, primary actions — extending chronicle's own existing CLI graph vocabulary (gold ring = core memory, diamond = latest checkpoint) rather than inventing unrelated iconography. Memory nodes render as stars: size/brightness by significance and status (active bright, resolved dimmer, superseded faint). Semantic-similarity edges are thin faint white constellation lines; explicit typed relations (`related_to`/`supersedes`/`caused_by`/`blocked_by`/`implements`) are brighter dashed gold lines with directional glyphs. Typography: system-ui stack for chrome/labels/nav (workhorse, Operate-mode appropriate, no decorative display face), monospace stack (ui-monospace/SF Mono/Menlo) for numeric/technical readouts — ports, PIDs, counts, timestamps — reinforcing the instrument/chart-plate feel without naming a trend face.

STORY: The operator opens the dashboard, immediately reads the all-projects chart as "here is everything chronicle remembers, plotted," picks a project card to narrow to just its chart, and checks the Control tab's instrument-style readouts to confirm the local stack is healthy — all without the surface ever implying data or activity that isn't real.

FIRST VIEWPORT: Graph tab, all-projects view, full-bleed indigo star-field. Header bar (thin, dark, brass wordmark accent) with Graph/Projects/Control tabs. The star field fills the viewport below the header; a compact legend (bottom-left, chart-plate style) keys node status colors and the two edge-line treatments. No sidebar chrome competing with the chart itself — this view is the thesis, and it must read as a chart, not a card-and-panel dashboard shell with a graph embedded in it.

FORM: "Constellation / star chart," candidate 1 of 7 in this session's grounded list (assigned index 3 from the concept seed was a transit-network diagram; user chose this candidate instead as the stronger fit — a user-made choice beats the roll). Seed key: dffae362.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

SIGNATURE INTERACTION: Selecting a node dollies the camera softly toward it while its direct connections (both edge kinds) brighten and every unrelated star dims to ~30% opacity — a focus pulse, not an instant cut. At rest, the whole star field drifts in a slow continuous rotation (planetarium-dome idle motion), so the chart has presence even untouched. Both motions are interruptible (dragging/zooming cancels the idle drift immediately) and capped to a sane frame budget — this runs on the operator's own machine alongside their actual dev work.
