# Hierarchical scope + docs repository — design

Status: approved (conversational design), pending written-spec review
Date: 2026-09-26
Relates to: scope_project.md roadmap item 5 ("Hierarchical scopes") — this
spec implements the part explicitly deferred there: full user/domain/agent
hierarchy beyond the default-deny project isolation already shipped.

## Problem

Chronicle's only scope today is `project`, enforced default-deny at the
repository layer. That's correct for isolation but has no notion of
anything *above* a project: there is no way to hold context that is true
across all of "work" without dumping it into every individual project, no
way to file two related projects (e.g. `azure_vm_config`,
`azure_cosmos_db`) under a shared parent, and no first-class place for
documents that aren't owned by any single project.

The goal is to add that hierarchy and a project-agnostic docs repository
without violating the existing invariants:

- no silent global scope
- core is not an automatic dump
- project-scoped operations must never silently cross project boundaries

i.e. an agent must be able to *explicitly* reach up to a parent scope's
core or into the docs repository, but nothing is ever auto-injected into
a session that didn't ask for it.

## Non-goals

- Multi-user/multi-tenant support (this is still single-user; the
  hierarchy is a taxonomy, not an auth boundary between people).
- Automatic classification of existing projects into personal/work — that
  is a manual curation step the user does after migration, not something
  the system guesses.
- A general-purpose file storage/versioning system for docs. Docs remain
  Memory rows with Source provenance, same as everything else in
  Chronicle.
- LLM-based chunking. Chunking is deterministic (size/boundary-based).

## Design

### 1. Scope model (materialized path)

New table `scope`:

```
scope
  id          PK
  name        text                      -- "azure_vm_config", "work"
  parent_id   FK -> scope.id, nullable   -- null = root node
  path        text, unique, indexed      -- "work/azure/vm_config"
  created_at  timestamp
```

- A materialized-path hierarchy, not a fixed two-level column. Arbitrary
  depth, no schema change to add a new domain or grouping later. Lookups
  are indexed prefix matches (`path LIKE 'work/azure/%'`), not recursive
  CTEs — this is the standard, efficient pattern for tree data in SQL
  (same technique used for org charts, threaded comments, nested
  categories).
- Every existing `project` is a scope leaf. The `project` string
  parameter on every existing MCP tool keeps working unchanged — it
  resolves to a scope node by `name` under the hood. No caller-visible
  break.
- `core` (the existing "small deliberate high-priority context" concept,
  today keyed by a document `slug` equal to the project name) can now
  attach to **any** scope node, not only a project leaf. A `work` scope
  can have its own core doc; `work/azure` can have a different one;
  `work/azure/vm_config` (a project) keeps the one it has today.
- Retrieval stays default-deny: querying `scope_id=X` (or a path prefix)
  never returns rows outside that subtree. Reaching a parent or sibling
  scope's core/memories requires an explicit call naming that scope —
  there is no implicit inheritance or merge.

### 2. Docs repository + chunking

- Docs live under their own scope subtree by default (e.g. `docs/azure`,
  `docs/general`), not under any project's scope — that's what makes them
  project-agnostic.
- `chronicle import` (the existing folder connector) gains size-based
  chunking: files over a threshold (~1500 tokens, exact value tunable)
  are split on paragraph/heading boundaries at ingest time. Small files
  are unaffected — still one Memory row, exactly as today.
- Each chunk becomes its own `Memory` row, type=`document`, sharing the
  parent file's `source_id`, with a new `chunk_index` column for
  ordering. Hash-based dedup/change-detection is computed over the whole
  file before splitting, same as today — an unchanged file still produces
  zero writes on rescan; a changed file supersedes all of its prior
  chunks.
- **Retrieval surfacing**: a search match returns the matching chunk plus
  its immediate neighbors (`chunk_index - 1`, `chunk_index + 1`, same
  `source_id`) as one bundled unit, so a hit isn't context-free. The
  bundle counts as a single item against the existing `max_tokens` greedy
  packing — a bundle can still be dropped under a tight budget, same as
  any other ranked result today.
- **Fetching the rest of a document**: new tool `memory_get_by_source`
  returns every chunk for a `source_id` in order, for when an agent needs
  more than the bundle.
- **Linking to a project**: `memory_link` gets a new conventional
  relation-type string, `relates_to_project`, applied once at the
  **source level** (one link per doc-to-project relation, not one per
  chunk — all chunks of a linked source are transitively considered
  linked).
- **Consuming links**: `memory_search`/`memory_search_global` gain an
  opt-in `include_linked: bool = False` parameter. When set, the same
  hybrid RRF search also considers memories reachable via a
  `relates_to_project` link from the current scope, tagged `via_link` in
  results to distinguish them from native-scope hits. Never on by
  default.

### 3. MCP tool surface diff

Two new tools; everything else is additive parameters, no breaking
changes to existing signatures or behavior.

| Tool | Change |
|---|---|
| `memory_add`, `memory_confirm`, `memory_edit`, `memory_retract`, `memory_mark_wrong`, `memory_merge`, `memory_split`, `memory_register_project`, `memory_dashboard_snapshot` | Unchanged. `project` param still resolves to a scope leaf by name. |
| `memory_search`, `memory_search_global` | + optional `include_linked: bool = False`. |
| `memory_set_document`, `memory_get_document` | + optional `scope_path` param to target any scope node's core doc (e.g. `"work/azure"`). Omitted → identical to today's project-scoped behavior. |
| `memory_link` | No schema change — `"relates_to_project"` is a new valid value for the existing free-text relation type. |
| `memory_dashboard_graph` | Emits scope nodes (path, parent, child count, core-present flag, linked-doc count) alongside memory nodes, for the dashboard visualization (Section 5). |
| **`memory_get_by_source(source_id)`** *(new)* | Returns a source's chunks in order. |
| **`memory_list_scopes(prefix: str = "")`** *(new)* | Lists scope paths matching a prefix — lets an agent discover that `work/azure/vm_config` exists before querying it by name. Without this, an agent can only reach scopes it already knows the name of. |

Reparenting a scope (e.g. moving `chronicle` under `work/`) is a
dashboard-only operation, not an agent-facing MCP tool — reorganizing the
taxonomy is curation, the same trust tier as editing core, not something
an agent does unprompted.

### 4. Migration plan

1. Alembic migration adds the `scope` table and a nullable `scope_id` FK
   on `Memory`/`Source`/`Episode`.
2. Backfill: every distinct existing `project` value (chronicle,
   NeuroMesh, forgeai, heliofi_backend, ragforge, control_asistencias)
   becomes a **top-level scope node** (`parent_id = null`,
   `path = <project name>`). The migration does not guess personal vs.
   work — that classification is an explicit step the user does
   afterward (dashboard reparent), not part of the migration. This keeps
   the migration itself additive and low-risk: nothing changes for
   existing callers until the user chooses to reorganize.
3. `scope_id` is made required only after backfill is verified complete
   (same two-phase pattern as the confidence/extraction_method columns
   added in the 3.0.0 rearchitecture).
4. Qdrant snapshot backup (`scripts/backup.sh`) before running, same
   discipline as the 3.0.0 storage cutover.

### 5. Dashboard visualization

No new rendering stack — this extends the existing `@react-three/fiber`
"Chart Room" scene (orbitable camera, per-project galaxy clusters, nebula
halos, click-to-drill provenance/core editor) that already exists.

- Any scope node with children renders as a black hole — larger/darker,
  sized roughly by descendant count — at the center of an orbit. Its
  children (sub-scopes or leaf projects) render as the existing
  galaxy/star visuals, orbiting it. This is recursive by construction:
  `work`/`personal` are the largest black holes at the center; `work/
  azure` is itself a smaller black hole orbiting `work`, with
  `azure_vm_config`/`azure_cosmos_db` orbiting *it*. One visual rule,
  arbitrary depth — falls directly out of the materialized-path model in
  Section 1.
- The `docs` subtree renders the same way (its own black hole/orbit
  cluster). A doc chunk that is `relates_to_project`-linked to a project
  gets a faint connecting thread drawn to that project's galaxy, reusing
  the graph's existing semantic-edge rendering.
- Clicking a black hole drills the camera in and reveals its children,
  reusing the existing "click reaches full detail without leaving the
  page" interaction already built for provenance/supersede history.
  Clicking further reveals that node's core doc, editable inline exactly
  like project core is today.
- Exact visual treatment (shaders, colors, sizing curve) is impeccable's
  call at implementation time — this section specifies the data contract
  and interaction model, not pixels.

## Testing

- Migration: `alembic upgrade head` on a copy of the real DB backfills
  every existing project into a top-level scope with no data loss;
  `alembic downgrade` reverses cleanly.
- Scope isolation: a query scoped to `work/azure/vm_config` cannot return
  rows from a sibling `work/azure/cosmos_db` or from `work` itself,
  without `include_linked`/an explicit ancestor query.
- Chunking: a file under the threshold produces exactly one Memory row
  (unchanged behavior); a file over the threshold produces N rows sharing
  one `source_id` with correct `chunk_index` ordering; rescanning an
  unchanged large file produces zero writes; rescanning a changed one
  supersedes all prior chunks for that source.
- Neighbor bundling: a search hit on chunk `i` returns `i-1`, `i`, `i+1`
  (or fewer at document boundaries) as one packed unit.
- Linking: `relates_to_project` created once at the source level makes
  every chunk of that source appear in `include_linked=True` results for
  the target project; `include_linked=False` (default) never surfaces
  them.
- New tools: `memory_get_by_source` returns chunks in order for a known
  `source_id`; `memory_list_scopes` prefix-matches correctly including
  no-match and root-level (`prefix=""`) cases.
- Backward compatibility: every existing test in the current suite (164
  passing as of the 2026-09-26 rename) continues to pass unmodified,
  since `project=` behavior is unchanged.

## Open questions for implementation (not blocking this spec)

- Exact chunk size/boundary heuristic (token threshold, paragraph vs.
  heading splitting) — tune during implementation against real docs, not
  decided a priori.
- Whether `memory_list_scopes` needs pagination for very large trees —
  defer until a real tree is large enough to need it.
