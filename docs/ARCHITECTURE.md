# Architecture

## Stack

| Layer | Choice | Why |
|---|---|---|
| Canonical storage | SQLite (SQLAlchemy 2 + Alembic migrations) | Single-file, zero-ops source of truth for every memory/source/episode/scope row |
| Lexical retrieval | SQLite FTS5 (`memory_fts`, sync triggers) | Real full-text search, not a substring scan |
| Semantic retrieval | [Qdrant](https://qdrant.tech/) (Docker), behind a `VectorIndex` protocol | Vector similarity only — a derived index, not the source of truth |
| Embeddings | `nomic-embed-text-v1.5` via [fastembed](https://github.com/qdrant/fastembed) | Local, free, CPU-only, no external API call, no background service |
| Application/core | `MemoryRepository` + `MemoryService` (`src/chronicle/core/`) | All business logic lives here; FastMCP and the CLI are thin wrappers over it |
| MCP server | [FastMCP](https://gofastmcp.com/) (Python), stdio transport | No network exposure, low boilerplate |
| Dashboard | React 19 + Vite + @react-three/fiber, served via FastAPI | Local-only 3D memory/scope explorer, `chronicle dashboard start` |

Qdrant is the only always-on background process, and it's a derived index —
deleting and rebuilding it from SQLite loses nothing durable. The MCP server
itself is spawned as a subprocess per session by Claude Code, Cursor, or
Codex; it is not a daemon. `Database.__init__` runs Alembic migrations
programmatically (not `create_all`), so a brand-new SQLite file always gets
its FTS5 virtual tables and triggers provisioned, not just its plain tables.

## Data model

SQLite is authoritative. Every memory/source/episode/scope lives here first;
Qdrant only ever holds a vector plus enough metadata to filter a similarity
search.

**Memory** (one row per memory or named-document version):

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `project` | string | The scope path this memory belongs to — the hard isolation boundary |
| `type` | string | `decision` \| `architecture` \| `bug` \| `todo` \| `note` \| `checkpoint` \| `overview` |
| `content` | string | The memory text |
| `status` | string | `active` \| `proposed` \| `resolved` \| `superseded` \| `expired` \| `deleted` \| `wrong` |
| `created_at` / `updated_at` | ISO8601 UTC | |
| `source_id` | FK, optional | Which `Source` row this memory came from (e.g. an imported file) |
| `episode_id` | FK, optional | Which ingestion event produced it (used for hash-based change detection) |
| `supersedes` | UUID, optional | The prior memory this one replaces |
| `confidence` | float, optional | Provenance signal, adjustable via `memory_confirm` |
| `extraction_method` | string, optional | Provenance signal — how this memory was derived |
| `slug` | string, optional | Present only on named documents (`memory_set_document`), unique per `(project, slug)` |
| `chunk_index` | int, optional | Position within a multi-chunk source (see "Docs chunking" below) |
| `valid_at` / `invalid_at` | ISO8601 UTC | `valid_at` defaults to `created_at`; `invalid_at` is set automatically when status moves to `superseded`/`expired`/`wrong` (never for `resolved`/`deleted`) — history is preserved, never overwritten |
| `relations` | list | Explicit typed links to other memories (see `memory_link`) |

**Source** rows are deduplicated per `(project, locator)` and reused across
writes to the same source rather than recreated. **Episode** rows track
individual ingestion events. **Scope** rows form the hierarchy (below) and
are a separate concept from all of the above — a scope is a place memories
live, not a memory itself.

## Scope hierarchy and project isolation

Above plain per-project isolation, scopes form a materialized-path tree:

| Field | Notes |
|---|---|
| `path` | Full materialized path, e.g. `personal_projects/heliofi/heliofi_backend` |
| `name` | The scope's own leaf name |
| `parent_path` | `null` for a root scope |
| `child_count` | Number of direct children |

Every tool except `memory_search_global` is implicitly scoped, resolved
fresh on every call: an explicit `scope_path` argument if the caller passes
one, else `CHRONICLE_PROJECT` from the environment, else a lookup of the
current folder in a small local registry (`~/.chronicle/projects.json`,
written by `memory_register_project` / `chronicle register --project X`) —
fail-closed if none resolve. `memory_search_global` is the one deliberate,
explicitly-named cross-project exception.

A **registered project** (the common case — a repo with an MCP session
attached) keeps its memories keyed by its own bare name regardless of where
that name has been organized in the scope tree; reparenting a project under
a sub-scope changes only where it renders in the taxonomy, never its actual
storage key, since `config.get_project()` always resolves to the bare name.
`memory_get_document`/`memory_dashboard_graph` fall back from a full-path
lookup to the bare-name convention for exactly this reason.

A **pure organizational scope** (created only to hold other scopes, e.g. a
`personal_projects` root with no memories of its own) can still carry a core
document, targeted with its own `scope_path` — there's no requirement that
every scope correspond to a registered project.

Manage the tree with `memory_list_scopes`, `memory_scope_reparent`, or
`chronicle scope create/list/move` from a terminal — reorganizing is always
a deliberate, user-requested action, never a side effect of another tool
call.

## Tools (20 MCP tools)

- **`memory_add(content, type, supersedes=None, confidence=None, extraction_method=None, scope_path=None) -> dict`** — always creates a new memory.
- **`memory_search(query, type=None, k=5, max_tokens=None, include_linked=False, scope_path=None) -> list[dict]`** — hybrid FTS5 + vector search, RRF-merged, scoped to the current project by default. `type="checkpoint"` returns the newest checkpoints chronologically instead — query text is ignored for that type, since a checkpoint history is a timeline, not a topic.
- **`memory_search_global(query, type=None, k=5, max_tokens=None, include_linked=False) -> list[dict]`** — the same search, across every project. The one deliberate unscoped path.
- **`memory_set_document(slug, content, type, confidence=None, extraction_method=None, scope_path=None) -> dict`** — replace-in-place, keyed by `(project, slug)`. For content that should supersede its previous version, not accumulate.
- **`memory_get_document(slug, scope_path=None) -> dict | None`** — exact lookup by slug, no embedding call.
- **`memory_get_latest(type, scope_path=None) -> dict | None`** — newest memory of that type by actual timestamp, no embedding call. Use for "what's the latest checkpoint" — `memory_search` ranks by semantic similarity to query text, not recency.
- **`memory_get_by_source(source_id) -> list[dict]`** — every chunk belonging to one source, in order (see "Docs chunking").
- **`memory_set_status(memory_id, status) -> dict`** — mark resolved/superseded/etc. without replacing the content.
- **`memory_confirm(memory_id, confidence=1.0) -> dict`** — bump confidence on human confirmation.
- **`memory_edit(memory_id, content) -> dict`** — in-place correction (typo/extraction slip); does **not** preserve history, does re-embed the vector. Use `memory_add(supersedes=...)` instead if the underlying claim actually changed.
- **`memory_retract(memory_id) -> dict`** — soft-delete.
- **`memory_mark_wrong(memory_id) -> dict`** — mark a fact that was never true (distinct from superseded/expired/deleted).
- **`memory_merge(content, type, source_ids, scope_path=None) -> dict`** — compose N sources into one memory; supersedes each source.
- **`memory_split(source_id, new_memories) -> dict`** — replace one source with N fragment memories, all superseding it.
- **`memory_link(source_id, relation_type, target_id) -> dict`** — explicit typed relationship, not just semantic similarity. `relation_type` ∈ `related_to`, `supersedes`, `caused_by`, `blocked_by`, `implements`, `relates_to_project`.
- **`memory_register_project(name) -> dict`** — registers the current folder (the server's own working directory) under `name` in the local registry. Needs no project to already be set — this is how an unregistered folder bootstraps.
- **`memory_list_scopes(prefix="") -> list[dict]`** — the scope tree, optionally filtered by path prefix.
- **`memory_scope_reparent(path, new_parent_path=None) -> dict`** — move a scope (and its descendants) under a different parent, or to root.
- **`memory_dashboard_graph(project=None, cross_project=False, k=..., min_similarity=...) -> dict`** — the graph data behind the 3D dashboard: nodes, similarity edges, and the scope tree together.
- **`memory_dashboard_snapshot() -> dict`** — a summary snapshot for the dashboard's control view.

## Checkpoint / resume

`memory_add(..., type="checkpoint")` is a normal memory with one convention:
the server's own `instructions` field (see `src/chronicle/server.py`) tells
the connected model to use it when asked to checkpoint, and to write it so
someone with zero memory of the conversation could resume the work from it
alone. Recall is a `SessionStart` hook running `chronicle-recall`, which does
a direct, chronological SQLite lookup for the newest checkpoint — no
embedding call on the read path.

## Named documents auto-load

By convention (not enforced in code), a project's own overview document uses
the project's own id as its `slug`. The same `SessionStart` hook that
recalls the latest checkpoint also looks up that one document and prints it,
so both show up automatically at the start of every session. For a client
with no project folder at all (Claude Desktop chat, for instance), pass
`scope_path` explicitly on the relevant call instead of relying on this
auto-load.

## `chronicle import` and docs chunking

`chronicle import <file-or-directory> --project X --type Y` splits a file on
paragraph breaks, grouping consecutive paragraphs up to ~24000 characters
(~6000 tokens) per chunk — comfortably under `nomic-embed-text-v1.5`'s
8192-token context window. Multi-chunk files share one `Source` row, with
each memory's `chunk_index` recording its position; `memory_get_by_source`
fetches every chunk of a source in order, and a search hit on one chunk
bundles neighboring chunks as context instead of returning it with nothing
around it. Importing a directory recursively ingests `.md`/`.txt` files, one
memory (or chunk set) per file, idempotent via a full-content SHA256 hash
embedded in the Episode title — unchanged files are skipped on rescan,
changed files supersede the prior memory for that path.

**Known limitation:** `fastembed` silently truncates text beyond the
context window instead of erroring. The ~24000-character chunk size is
sized for English prose (~4 chars/token) — code, JSON, and non-Latin-script
text tokenize far denser (measured: Python ~2.9 chars/token, JSON ~1.6,
Chinese ~1.0), so a normally-sized chunk of code-heavy or non-English
content can still exceed the 8192-token limit and get silently truncated.
No validation catches this today.

## `chronicle graph` and the dashboard

`chronicle graph [--project NAME] [--all] [--out PATH]` computes real
pairwise cosine similarity between every matching memory's embedding, keeps
each node's top-3 nearest neighbors as edges, and renders it as a
self-contained HTML file (dark, force-directed, Canvas-rendered) that opens
in your browser. `--all` graphs every project's memories together,
deliberately — otherwise it's scoped the same as everything else.

`chronicle dashboard start` (`--background` to persist, `stop` to stop it,
binds to `127.0.0.1:8765` by default — `CHRONICLE_DASHBOARD_PORT`/`--port`
to change it) serves a richer, persistent React/Three.js explorer over the
same graph data (`memory_dashboard_graph`/`memory_dashboard_snapshot`),
themed as a navigable "Chart Room" star chart:

- Every project's memory cluster renders as its own constellation, with its
  **core memory as the fixed center** everything else in that cluster
  orbits — the same way Sagittarius A* anchors the Milky Way, not just
  another point scattered on the cluster's surface.
- A scope with children (an organizational sub-core, not a leaf project)
  renders as its own body, styled by depth like a real solar system: the
  single root scope is a sun, its direct children are planets, and their
  children are moons — same construction throughout, differing only in
  color/size/corona per depth. Leaf project scopes render no separate body,
  just their existing constellation.
- Orbit lines connect a scope to its parent, and specifically target the
  parent's/child's actual core-memory node when one exists rather than an
  empty computed centroid.
- Sibling clusters and orbit rings are spaced by each scope's full subtree
  extent (its own size plus its children's own ring reach), computed
  bottom-up, so a densely-populated sub-scope can't spill into a
  neighboring sibling's territory.
- Clicking a node or a scope core opens its provenance trail, supersede
  history, and (for a core) an inline editor — no page leave.

## `chronicle setup` / `chronicle register` / `chronicle scope`

`chronicle setup` resolves its own install location at runtime
(`Path(__file__).resolve().parents[2]`) and prints ready-to-paste Claude
Code and Codex configuration — the right tool for a manual, non-plugin
install, or for generating the Codex command by hand. `chronicle register
--project X` is the plugin-install path instead: it writes `Path.cwd()`
(the folder it's run from) against that project name into
`~/.chronicle/projects.json`, nothing into the repo itself. `chronicle scope
create <path>` / `chronicle scope list [--prefix]` / `chronicle scope move
<path> [--to <parent>]` manage the scope tree from a terminal, equivalent to
the `memory_list_scopes`/`memory_scope_reparent` MCP tools. All are thin CLI
wrappers with no logic of their own beyond argument parsing and calling into
the shared runtime (`chronicle.core.runtime.get_runtime()`).

## `chronicle eval`

`chronicle eval --project X` reports 7 metrics against real stored data for
that project: self-retrieval recall proxy, stale-memory rate,
near-duplicate/contradiction proxy, duplicate rate, average tokens per
memory/search, latency, and provenance coverage. These are explicitly
labeled as proxies, never fabricated ground truth.

## Backups

`scripts/backup.sh` snapshots the Qdrant collection (the derived semantic
index); `scripts/export_json.sh` exports every memory as a flat,
human-readable JSON file (no vectors). Both prune to the newest 14.
`scripts/daily_backup.sh` runs both in sequence — see
`scripts/com.chronicle.dailybackup.plist` for the macOS `launchd` schedule
(3 AM daily). Windows equivalents (`backup.ps1`, `export_json.ps1`,
`daily_backup.ps1`) live in the same folder with the same behavior.

**Since the 3.0.0 storage rearchitecture, none of the above back up the
canonical SQLite database** (`~/.chronicle/chronicle.db`, one file for every
registered project). The Qdrant snapshot and the JSON export are both
*derived* from it and are not a substitute for backing it up directly — copy
`~/.chronicle/chronicle.db` itself (a plain file copy is sufficient; SQLite
requires no special snapshot tooling) before any operation that could lose
it. This is a known gap in the backup scripts, not a design choice.
