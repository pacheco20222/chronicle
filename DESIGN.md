---
name: Chronicle Dashboard
description: A star-chart instrument for reading a local memory store — memories as stars, relationships as traced lines, health as gauge readouts.
colors:
  ground: "#090d1d"
  ground-raised: "#10172b"
  plate: "rgba(12, 18, 36, 0.88)"
  plate-solid: "#0d1428"
  ink: "#e8edf8"
  ink-dim: "#8d98b0"
  ink-faint: "#5f6a82"
  line: "rgba(176, 193, 224, 0.18)"
  line-strong: "rgba(206, 219, 245, 0.32)"
  brass: "#d8a84e"
  brass-bright: "#f0ca76"
  signal-good: "#a9ca9e"
  signal-bad: "#df897d"
  status-active: "#f2d68f"
  status-resolved: "#9ba8bd"
  status-superseded: "#667187"
  type-decision: "#e7c77a"
  type-architecture: "#a8b6dc"
  type-bug: "#e38b7c"
  type-todo: "#91b9a1"
  type-note: "#9ab9d8"
  type-checkpoint: "#e8d9b4"
  type-overview: "#c5b0d8"
  edge-semantic: "#c5cee0"
typography:
  display:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "clamp(27px, 4vw, 40px)"
    fontWeight: 550
    lineHeight: 1.1
    letterSpacing: "-0.045em"
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, monospace"
    fontSize: "9px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.14em"
  readout:
    fontFamily: "ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, monospace"
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "normal"
rounded:
  sm: "2px"
  checkbox: "4px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "22px"
  xl: "30px"
components:
  button-primary:
    backgroundColor: "{colors.brass}"
    textColor: "#131a2b"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.brass-bright}"
  button-soft:
    backgroundColor: "rgba(216, 168, 78, 0.08)"
    textColor: "{colors.brass-bright}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-dim}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
  badge:
    backgroundColor: "rgba(216, 168, 78, 0.07)"
    textColor: "{colors.brass-bright}"
    rounded: "{rounded.sm}"
    padding: "5px 7px"
  input:
    backgroundColor: "rgba(5, 10, 23, 0.56)"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 9px"
---

# Design System: Chronicle Dashboard

## Overview

**Creative North Star: "The Chart Room"**

The dashboard reads chronicle's memory store the way a navigator reads a star chart, not the way a SaaS product reads a graph. A near-black deep-indigo ground carries a faint star-field texture across nearly the whole viewport; memories plot onto it as small geometric points sized and lit by significance and status; relationships trace as lines, not force-directed spaghetti. A single warm brass/gold accent marks selection, active state, and the two things worth highlighting from chronicle's own CLI vocabulary (a ring for a core memory, a wireframe diamond for the latest checkpoint). Everything else — chrome, labels, plates, buttons — is flat, sharp-cornered (2px radius), and instrument-panel plain: this is Operate mode, not a marketing surface.

Two build-time corrections are now load-bearing parts of the system, not incidental fixes: node geometry is deliberately small (point-like polyhedra 0.09–0.14 scene units, not large flat shapes), and semantic-similarity edges are hidden by default behind an explicit legend toggle because at real data volume (87 nodes / 183 edges) they produce unreadable crosshatch density — only explicit, directional, typed-relation edges render by default. The chart must read as a chart first.

**Key Characteristics:**
- Near-black indigo ground (~70%+ of visual weight), one warm brass accent, everything else desaturated cool grays
- Flat 2px-radius "chart-plate" surfaces (frosted glass via backdrop-blur, not drop-shadow cards)
- Monospace for every number, ID, timestamp, and label; sans-serif only for headings/prose/nav
- Tiny glowing point-like node glyphs, colored per memory type, not uniform dots
- Semantic edges off by default; explicit typed-relation edges (dashed brass, directional) always on
- Scope hierarchy (a project nested under a shared parent) renders recursively: any scope with children is a luminous quasar beacon its children visibly orbit, never a dark or occluding body — presence in this chart comes from being lit, not from blocking light

## Colors

Overwhelmingly cool and dark, with brass as the sole warm note — reserved, not decorative.

### Primary
- **Brass** (`#d8a84e`): selection rings, active tab underline, primary buttons, explicit-relation edges and their directional arrowheads, brand mark. The only warm color in the system.
- **Brass Bright** (`#f0ca76`): hover/active state of brass elements, focus outlines, active-tab label text, badge text.

### Neutral
- **Chart Ground** (`#090d1d`): the dominant field — app background, graph canvas, Canvas `background` color.
- **Ground Raised** (`#10172b`): secondary background layer (radial gradient partner behind the app shell).
- **Plate** (`rgba(12, 18, 36, 0.88)`): the frosted-glass surface color for every card/legend/panel (`.chart-plate`), paired with `backdrop-filter: blur(10px)`.
- **Plate Solid** (`#0d1428`): opaque variant used inside grid cells (project stats, control readouts) where blur isn't wanted.
- **Ink** (`#e8edf8`): primary text.
- **Ink Dim** (`#8d98b0`): secondary text, nav labels, tab-button default state.
- **Ink Faint** (`#5f6a82`): tertiary/placeholder text, uppercase micro-labels, endpoint status text.
- **Line** (`rgba(176, 193, 224, 0.18)`) / **Line Strong** (`rgba(206, 219, 245, 0.32)`): hairline borders and dividers throughout — plates, grids, process rows.

### Status & Signal
- **Status Active** (`#f2d68f`) / **Status Resolved** (`#9ba8bd`) / **Status Superseded** (`#667187`): memory node status, keyed in the legend and controlling node opacity (1 / 0.62 / 0.34).
- **Signal Good** (`#a9ca9e`) / **Signal Bad** (`#df897d`): Control-tab health readouts (Qdrant, Docker).

### Named Rules
**The One Warm Color Rule.** Brass is the only warm hue anywhere in the system. It marks selection, primary action, and the explicit-relation edge kind — never used decoratively or for a third purpose.

**The Legible Taxonomy Rule.** Memory-type colors (`type-decision` through `type-overview`) and status colors are a closed, reused set — the same seven type colors and three status colors appear identically in the legend, the graph nodes, and the project-card type chips. No screen invents a new color for an existing type or status.

## Typography

**Body/UI Font:** `ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` (system stack, no custom font loaded)
**Label/Mono Font:** `ui-monospace, "SF Mono", Menlo, Monaco, Consolas, monospace`

**Character:** A workhorse system pairing with no display face — correct for an Operate-mode instrument surface. The sans stack carries headings, nav, and prose; the mono stack carries everything numeric or technical (counts, PIDs, ports, timestamps, slugs, type/status labels) with `font-variant-numeric: tabular-nums`, reinforcing the chart-plate/readout feel without naming a trend font.

### Hierarchy
- **Display** (weight 550, `clamp(27px, 4vw, 40px)`, letter-spacing -0.045em): page headings (`.page-heading h1`) on Projects/Control tabs.
- **Title** (weight 550, 17px, letter-spacing -0.02em): card/plate titles (project name, control-plate `h2`).
- **Body** (weight 400, 13px, line-height 1.6): page-heading descriptions; case-plate content uses 12px/1.65.
- **Label** (weight 700, 8–9px, letter-spacing 0.14–0.16em, uppercase, mono): every micro-label — `plate-label`, `legend-heading`, `control-readout span`, `project-stats span`, `type-chip`, `brand small`.
- **Readout** (weight 500, 18–20px, mono, tabular-nums): the large numeric values in Control-tab and project-stat grids (point counts, PIDs, CPU/memory).

### Named Rules
**The Mono-For-Machine-Values Rule.** Any value the operator would use to verify system state — counts, IDs, PIDs, timestamps, ports, percentages — renders in the mono stack. The sans stack never carries a number the operator needs to trust.

## Layout

Full-bleed, no persistent sidebar. A 58px-min-height topbar (brand mark + Graph/Projects/Control tabs + endpoint status) sits above whichever tab is active. The Graph tab is edge-to-edge canvas with a floating legend plate anchored bottom-left (`22px` inset, `min(340px, 100%-44px)` wide) and a hint string bottom-right — no panel competing with the chart for the frame. Projects and Control tabs switch to a centered `data-page` column (`min(1240px, 100%)`, `42px 30px 64px` padding) using CSS grid: `project-grid` auto-fits `minmax(280px, 1fr)` cards at 14px gaps; `control-grid` is a fixed 2-column grid; `readout-grid` and `project-stats` are 1px-gap hairline grids (the gap itself is the divider, colored `var(--line)`). Below 760px, legend/hint insets tighten to 13px, control-grid collapses to 1 column, and the topbar hides the endpoint status and brand subtitle.

## Elevation & Depth

Flat by default — 2px corner radius everywhere, no shadow ramp. Depth comes from two devices instead: frosted-glass plates (`backdrop-filter: blur(10px)` plus a single soft shadow `0 18px 60px rgba(0,0,0,.24)`) that float over the star field, and hairline 1px dividers/grid-gaps that separate content without lifting it. The topbar gets one exception, a directional shadow (`0 8px 28px rgba(0,0,0,.22)`) to read as a fixed plane above the scrolling content below it.

### Shadow Vocabulary
- **Plate ambient** (`box-shadow: 0 18px 60px rgba(0,0,0,.24), inset 0 1px rgba(235,240,255,.035)`): every `.chart-plate` (cards, legend, case panel).
- **Topbar overhead** (`box-shadow: 0 8px 28px rgba(0,0,0,.22)`): the fixed header only.

### Named Rules
**The Flat-Plate Rule.** No component lifts on hover or interaction via shadow. State changes are communicated by color (brass) and opacity, never by adding elevation.

## Shapes

Sharp, nearly-square corners throughout: 2px radius is the system's only radius value for buttons, inputs, badges, chips, and plates (the checkbox is the sole exception at 4px, inherited from its Radix primitive). Borders are 1px hairlines in `--line`/`--line-strong`, never heavier. In the 3D scene, memory nodes are small spheres (0.1 scene-unit radius) colored per type and scaled by degree/role/status — deliberately tiny and point-like ("stars"), a corrected-in-build departure from an earlier, larger flat-shape pass. Selection/role markers are thin brass toruses layered around a node, not solid overlays; a scope-hierarchy beacon (see Components → Star Chart) is the one signature element built from soft additive glow sprites rather than shaded solid geometry, so it stays luminous and reads correctly from any camera angle instead of presenting a flat silhouette.

## Components

### Buttons
- **Shape:** 2px radius, 34px min-height, 0–12px horizontal padding, 11px bold uppercase label at 0.04em tracking.
- **Primary (`solid`):** brass background (`#d8a84e`), dark ink text (`#131a2b`); hover → brass-bright.
- **Soft:** transparent brass-tinted background (`rgba(216,168,78,.08)`), brass-bright text, brass-tinted border; hover deepens both.
- **Ghost:** transparent, dim-ink text; hover → full ink + faint white wash.
- **Disabled:** 0.55 opacity, wait cursor.

### Badges / Chips
- **Badge:** brass-tinted border and background, brass-bright uppercase mono text, 2px radius — used for counts (`87 stars`).
- **Type chip:** per-type color border/text (type color at ~33% alpha border), small dot glyph, used on project cards to summarize memory-type counts.

### Cards / Plates
- **Corner Style:** 2px radius.
- **Background:** `--plate` (frosted) for legend/case/project/control plates; `--plate-solid` for nested grid cells.
- **Shadow Strategy:** see Elevation & Depth — ambient plate shadow only, no hover lift.
- **Border:** 1px `--line`; project/control plates carry a 2px brass gradient top accent (`linear-gradient(90deg, brass, transparent 60%)`) as their only decorative flourish.
- **Internal Padding:** 12–14px within readout/stat cells; card header/content follow Tailwind `p-5`/`px-5 pb-5`.

### Inputs / Fields
- **Style:** mono text, 10px, `rgba(5,10,23,.56)` background, 1px `--line` border, 2px radius, 8px 9px padding.
- **Focus:** border shifts to `rgba(216,168,78,.7)` (brass), no glow.

### Navigation
- **Style:** uppercase 12px bold tab labels in the topbar, dim-ink default, ink on hover, brass-bright + 2px brass underline when active. A trailing mono count badge (`span`) rides each tab label.

### Star Chart (signature component)
The `GraphScene` — a `@react-three/fiber` Canvas over the indigo ground. Memory nodes are small spheres colored per type, sized by degree/role/status, and glow via an additive-blended sprite plus subtle Bloom postprocessing. A project's own core memory gets a warm sun-colored halo sprite (`#ff8f57`, scaled to 1.9x the node) at 3.2x the base node scale, the same family of treatment as a scope beacon (see below) at node scale — the type-colored sphere underneath is untouched, so taxonomy color stays legible; the latest checkpoint keeps a single thin brass ring at 1.12x scale (unchanged — this is the one place a ring is still the right signature). Explicit typed-relation edges render as dashed brass lines with a directional cone arrowhead and are always visible; semantic-similarity edges render as thin, very-faint cool-gray lines (`#c5cee0` at ~0.055 opacity) and are hidden by default behind a legend checkbox — even when shown, each node retains only its top-2 nearest semantic neighbors by similarity to keep the field legible. Selecting a node dollies the camera toward it, brightens its direct connections, and dims everything else to ~30%; at rest the whole chart drifts in slow continuous rotation, interruptible by any drag/zoom and disabled under `prefers-reduced-motion`.

A scope (a project, or a named parent grouping several projects/sub-scopes) that has children renders recursively as a warm-colored star: a solid sphere (`#e8703a`) with a thin, dim corona sprite just large enough to suggest radiated heat, not a glow effect standing in for the body itself — no texture, no ring, no rotation. A present core document brightens the corona's base opacity slightly rather than adding a marker; a linked doc adds a small companion sparkle offset to one side, not a ring. Siblings under the same parent are placed via `siblingPoint` — a tight arc (not the full-sphere `fibonacciPoint` spread used for unrelated top-level projects), so two children read as a grouped pair rather than opposite poles of a sphere — at a radius that always clears both the parent's and the child's own size plus a fixed gap, so nothing ever visually touches. Every child — sub-scope or leaf project — is joined to its parent by a **plain orbit line**: solid, thin, low-opacity brass, no glow, no dashing (dashing is reserved for explicit memory relations, see above). That line targets the child's own core-memory node position when it has one (the same halo marker described above, not the cluster's fibonacci-computed centroid, which has no glyph rendered there at all) so the connector visibly plugs into something real; it falls back to the child scope's own body only when that scope has no core yet. This design went through several earlier, rejected passes: a dark, light-occluding sphere with one thin ring (invisible against the near-black ground); a bright ring plus twin jets (read as "planet with rings," and the jets looked like an unintended connection line between two beacons that happened to align); a procedural granulation texture with a big pulsing corona (imperceptible at actual render scale — complexity that wasn't earning its keep); and a full-sphere sibling spread that put two children of the same parent on opposite sides of their parent instead of grouped together.

### Named Rules
**The Luminous-Not-Occluding Rule.** Every signature 3D element reads by emitting light (additive glow sprites, bright rings, pulsing cores), never by blocking it. A dark or occluding shape against this chart's near-black ground has almost no visual weight — "more important" always means "brighter and bigger," never "darker."

**The Real Connections Rule.** A line in this chart always represents an actual relationship, targets the real marker it connects to (never an empty computed point), and is drawn as a plain line — additive glow and stacked decorative geometry read as ambience, not as a connection, and must not be used to imply one.

## Do's and Don'ts

### Do:
- **Do** keep brass as the only warm accent — reserve it for selection, primary action, and explicit-relation edges.
- **Do** render every machine-readable value (counts, PIDs, timestamps, ports) in the mono stack with tabular numerals.
- **Do** keep the Graph tab's first viewport chart-first: one floating legend plate, no competing sidebar or panel stack.
- **Do** default semantic-similarity edges to hidden and cap rendered neighbors per node — the un-culled union view is a known illegible state, kept only as an opt-in toggle.
- **Do** use the 2px radius / hairline-border / flat-plate vocabulary for any new panel; don't introduce a second corner-radius scale.

### Don't:
- **Don't** add drop-shadow "lift" on hover — state changes are color/opacity only (see The Flat-Plate Rule).
- **Don't** render large flat node shapes in the graph — nodes are small point-like spheres by corrected design, not big geometric icons.
- **Don't** stack multiple overlapping graph-tab panels — the legend was consolidated from three redundant panels into one during finish review; don't reintroduce that duplication.
- **Don't** fabricate activity, metrics, or network status the underlying store doesn't have — every readout (Qdrant, Docker, process list, counts) must reflect real sampled data, inherited from PRODUCT.md's core no-cloud/no-fabrication commitment.
- **Don't** render a scope-hierarchy body as a dark or occluding shape — see The Luminous-Not-Occluding Rule; presence in this chart always comes from emitted light, not from a bigger dark silhouette.
- **Don't** reach for ring geometry as the default way to mark significance — a ring around a sphere reads as "planet with rings," not "star." Scale, brightness, and layered soft glow are the vocabulary for "bigger/more important" here; a ring is a specific, deliberate signature (core memory, latest checkpoint) reserved for those exact two markers, not a general-purpose emphasis device.
- **Don't** draw a connector line to a computed centroid or any point with no glyph rendered there — see The Real Connections Rule; a line always terminates on the actual marker it represents a relationship to.
- **Don't** lean on a big glow sprite as a body's primary visual — glow reads as atmosphere around something, not as the something. A scope beacon's presence comes from its actual textured, sized surface; the corona is a thin accent on top of that, not a substitute for it.
