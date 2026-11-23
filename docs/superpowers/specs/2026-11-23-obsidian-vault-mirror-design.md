# Obsidian vault mirror — design

Date: 2026-11-23. Status: draft, awaiting owner approval.
Part 1 of the "Chronicle in Obsidian" project (order: 1 vault mirror →
2 PDF/Office conversion → 3 compiled wiki pages → 4 Notion connector →
5 cross-project named search + search quality).

## Why

People shouldn't have to open the dashboard to see what Chronicle knows.
Many already live in Obsidian (or Notion). Chronicle's memories should show up
there as browsable, interlinked pages — with Obsidian's graph view showing the
connections — so the knowledge sits where people already read.

Inspiration: Karpathy's "LLM Wiki" pattern. Raw sources stay immutable; an
LLM-maintained wiki of interlinked markdown sits on top; a schema tells the
agent how to maintain it; "Obsidian is the IDE, the LLM is the programmer, the
wiki is the codebase." Chronicle maps onto it:

| LLM Wiki layer | Chronicle |
|---|---|
| Raw sources (immutable) | The project folder (repo or plain folder of docs/PDFs) and any vault note the user points at. Chronicle reads, never writes. |
| The wiki (LLM-owned) | `<vault>/Chronicle/<project>/…`, written and refreshed by Chronicle from SQLite. Read-only for humans. |
| The schema | `skills/chronicle-memory/SKILL.md` + MCP server instructions. |
| log.md / lint | Per-project `log.md`; `chronicle eval` already approximates lint. |

Chronicle itself never calls an LLM (project rule). Synthesis comes from the
agent already in use, through MCP tools; Chronicle does the deterministic part:
storing, linking, rendering files.

## Audiences

- **Developers:** project folder is a git repo; memories come from coding
  sessions and repo docs.
- **Everyone else:** project folder holds PDFs, Word files, notes; memories
  point at those files ("payment questions → see `invoices/terms.pdf`").

Same model for both.

## Goals

1. Opt-in per project, a project's memories appear as markdown pages in one
   Obsidian vault, under `<vault>/Chronicle/<project>/`.
2. Pages are interlinked with `[[wikilinks]]` so Obsidian's graph, backlinks
   and Dataview work with no plugin.
3. The mirror updates live when memories change; a full rebuild command exists.
4. A memory can point at a source file (PDF, doc, vault note); the mirror links
   to it.
5. Each mirrored project has a file catalog page listing the project folder's
   files, so "there is a PDF about payments" is discoverable by people and
   agents.
6. Page format leaves room for agent-written topic/entity pages (Part 3)
   without breaking links.

## Non-goals (this part)

- Reading or syncing notes people write in the vault automatically
  (agent links them on request instead — see "Agent-linked notes").
- Converting PDFs/Office files to text (Part 2, MarkItDown as optional extra).
- Compiled topic/entity pages (Part 3).
- Notion (Part 4). Obsidian plugin (possible later add-on: dashboard pane,
  refresh command).
- Similarity links in the vault (optional setting, default off — see Links).

## Anti-goals

- **Client data leaking via vault sync.** Vaults are often synced (Obsidian
  Sync, iCloud, Dropbox). Nothing is mirrored unless the owner opted that
  project in.
- **Writing into project folders or code repos.** The mirror writes only inside
  `<vault>/Chronicle/`.
- **Destroying user notes.** Chronicle never modifies or deletes anything
  outside `<vault>/Chronicle/`, and inside it only files it generated.
- **SQLite stops being canonical.** The vault is a projection; edits there are
  overwritten on the next refresh.
- **Half-written pages** when two agent sessions write at once.

## Approaches considered

1. **Chronicle writes the markdown files (chosen).** Core vault writer renders
   pages from SQLite; refresh after each memory change; `chronicle vault sync`
   rebuilds. Works in plain Obsidian (graph, backlinks, Dataview) and any
   markdown tool. Matches the LLM Wiki pattern. No new codebase.
2. **Obsidian plugin rendering Chronicle live, no files.** Nothing on disk, so
   no sync leak — but Obsidian's graph/backlinks/search only see real files, so
   Chronicle wouldn't appear in the graph (the main goal). Needs the dashboard
   server running; second codebase (TypeScript). Rejected.
3. **1 now + small Obsidian plugin later.** Plugin only adds conveniences. Kept
   as a possible later add-on, not in this part.

## Design

### Configuration

Stored in `~/.chronicle/config.json` (same file and helpers as the `semantic`
setting):

- `vault_path`: absolute path to the Obsidian vault (one per machine).
- `vault_projects`: list of project names opted in.
- `vault_similarity_links`: bool, default false.

CLI (`chronicle vault …`, thin wrapper over core):
- `vault set <path>` — set the vault (creates `<path>/Chronicle/` if missing;
  refuses home or filesystem root; path may or may not already be a vault).
- `vault add <project>` / `vault remove <project>` — opt a project in/out.
  `add` renders the project immediately. `remove` stops updates and deletes
  that project's generated folder (only files carrying the generated marker,
  see Safety).
- `vault status` — vault path, opted-in projects, page counts, last sync.
- `vault sync [<project>]` — full rebuild of one or all opted-in projects.

MCP tools (thin, same core): `memory_vault_status`, `memory_vault_add_project`,
`memory_vault_remove_project`, `memory_vault_sync`. Agents call add/remove only
when the user asks (SKILL.md rule, like `memory_add_project`). Dashboard: a
per-project "Show in Obsidian" toggle and the vault path in the control view.

### Vault layout

```
<vault>/Chronicle/
  index.md                    # all mirrored projects, links to each project page
  <project>/
    <project>.md              # project page: overview doc, counts, links to sections
    log.md                    # chronological: checkpoints + memory events
    files.md                  # file catalog of the project folder
    memories/<slug>.md        # one page per memory
```

- **Memory page name:** stable and human-readable:
  `<type>-<short title>-<first 8 chars of id>.md` (title derived from the
  first line of content, sanitized for filenames; the id suffix guarantees
  uniqueness and stability even if content is edited — builder decides exact
  sanitization, max length ~80 chars). Renaming on content edit is NOT done;
  the id suffix keeps links stable.
- Project folder name = project name (sanitized the same way).

### Memory page format

YAML frontmatter (Obsidian "properties", Dataview-readable):

```yaml
chronicle_id: <uuid>
project: <project>
type: decision
status: active
created: 2026-11-23T10:00:00Z
updated: …
confidence: 0.9          # when set
source: <path or url>    # when set
generated_by: chronicle  # marker, see Safety
```

Body: the memory content verbatim, then a "Links" section with wikilinks:
- `Project: [[<project>]]`
- `Replaces: [[…]]` / `Replaced by: [[…]]` (supersede chain)
- explicit relations: `<relation_type>: [[…]]`
- `Source: …` (see Sources)

Superseded / wrong / retracted memories keep their page (history stays
browsable), with status in frontmatter and a one-line banner at the top
("Replaced by [[…]]" / "Marked wrong" / "Retracted").

### Links (what becomes a wikilink)

Only what Chronicle stores: project membership, supersede chain, explicit
relations (`memory_link`, including cross-project links when both projects are
mirrored; if the target project isn't mirrored, render plain text "(in project
X, not mirrored)" — never leak its content). Similarity links only when
`vault_similarity_links` is true (top-k, threshold — builder reuses the
dashboard graph's existing k/min_similarity defaults).

### Sources: files and agent-linked notes

- `memory_add` gains an optional `source` parameter (path or URL), stored via
  the existing Source/locator provenance model. `memory_edit`/supersede keep
  or replace it as today's provenance rules do.
- Rendering:
  - source inside the vault → `[[relative/path/to/note]]` (real Obsidian link,
    shows in the graph and backlinks).
  - source elsewhere on disk → markdown link to a `file://` URL (opens in the
    OS viewer; Obsidian can't wikilink outside the vault).
  - URL → normal markdown link.
- **Agent-linked notes:** the user writes a note anywhere in the vault and says
  "note this in Chronicle"; the agent reads it and calls `memory_add` with
  `source=<vault note path>`. SKILL.md documents this flow.

### File catalog (`files.md`)

Generated from the project folder(s) in the registry at render time — not
stored in SQLite (the folder is the source of truth). Lists non-hidden files
(skipping the same dirs the importer skips: `node_modules`, `.git`, `dist`,
`build`, `venv`, `site-packages`, `__pycache__`), grouped by folder: name as
`file://` link, type, size, modified date. Bounded: cap at a builder-chosen
limit (e.g. 2,000 entries) with a "truncated" note. MCP tool
`memory_list_files(query=None, scope_path=None)` returns the same catalog
(bounded, optional case-insensitive name filter) so agents can find "the PDF
about payments". Project with no registered folder (e.g. Desktop-only) → page
says so.

### Project page, index, log

- `<project>.md`: overview document content (if any), counts by type/status,
  links to `log.md`, `files.md`, and the most recent N memories by type.
- `log.md`: newest-first list of checkpoints and memory events
  (`## [YYYY-MM-DD] <event> | <title>` lines, Karpathy's grep-friendly format),
  each linking the memory page. Built from timestamps/status in SQLite (no new
  event table).
- `Chronicle/index.md`: list of mirrored projects with one-line summaries.

### Live refresh

- A `VaultMirror` component in core, called by `MemoryService` after every
  mutation (add, edit, status change, confirm, retract, mark_wrong, link,
  merge, split, set_document) for the affected project(s) only. It re-renders
  the touched memory pages, their linked neighbors' pages (so backlink sections
  stay correct), the project page and `log.md`. `files.md` and `index.md`
  refresh on `vault sync`, `vault add`, and the dashboard "Sync vault" action.
- No-op (cheap check) when no vault is configured or the project isn't opted in.
- **Failure never breaks the memory write:** vault errors are logged and
  surfaced in `vault status`; the SQLite write already succeeded.
- Multiple agent processes may write concurrently: every file write is atomic
  (temp file in same dir + rename). Last writer wins; content is deterministic
  from SQLite, so a later render is always correct.
- Lives in core (not MCP/CLI) so every client path triggers it.

### Safety rules

- Write only under `<vault>/Chronicle/`; resolve paths and refuse anything that
  escapes it (symlinks, `..`, absolute names from content).
- Every generated file carries `generated_by: chronicle` frontmatter (and
  `index.md`/`log.md`/`files.md` too). Deletion/overwrite only touches files
  with the marker; a user file found at a generated path is left alone and
  reported in `vault status`.
- Pages for memories of non-opted-in projects are never written; cross-project
  link targets in non-opted-in projects render as plain text without content.
- Project/memory names sanitized for all OSes (Windows reserved names and
  characters).

### Part 3 compatibility (compiled wiki)

Topic/entity pages will be Chronicle documents (`memory_set_document` with a
new type or slug namespace) rendered to `<project>/topics/<slug>.md` with
wikilinks to the memories they cite. This design reserves `topics/` and keeps
memory page names stable so those links won't break.

## Constraints

- Local-first; no new required dependencies (YAML frontmatter written by hand
  or with the stdlib — no PyYAML requirement unless already present).
- SQLite stays canonical; mirror is derived and rebuildable.
- Business logic in core; CLI/MCP/dashboard thin.
- Existing behavior unchanged when no vault is configured.
- Files ~300 lines, functions ~40 lines (split renderer / layout / writer).

## Tests (minimum)

- Opt-in: unconfigured or non-opted-in project → nothing written.
- Page content: frontmatter fields, wikilinks for supersede/relations/project.
- Live refresh: add/edit/supersede/link updates the right pages and neighbors.
- Cross-project link to a non-mirrored project renders plain text, no content.
- Source rendering: in-vault → wikilink; outside → file:// link; URL → link.
- Safety: path traversal in names refused; user file without marker never
  overwritten/deleted; `vault remove` deletes only marked files.
- Atomic write: no partial file on simulated failure.
- Vault failure doesn't fail `memory_add`.
- File catalog skips ignored dirs, caps size; `memory_list_files` filter works.
- `vault sync` is idempotent (second run changes nothing).

## Clarifications (from builder check; all controller calls, owner may override)

1. **Scopes:** the mirror is keyed by the bare project name (what
   `config.get_project()` resolves to), flat under `Chronicle/`. The scope tree
   (parents, reparenting) does not affect folders in this part; parent scopes
   are not mirrored; reparenting moves nothing. Opt-in is per bare project
   name. *(my call — scopes are flat in practice today)*
2. **Wikilinks:** always full vault-relative paths with a display alias, e.g.
   `[[Chronicle/<project>/memories/<file>|<title>]]`, `[[Chronicle/<project>/<project>|<project>]]`,
   `[[Chronicle/<project>/log|log]]`. Never bare names, so other notes named
   `log`/`index`/`files` can't collide. Part 3 `topics/` links follow the same
   rule. *(my call)*
3. **Source model:**
   - `memory_add(source=…)` stores an absolute path (expanded, resolved) or a
     URL (`http://`/`https://` scheme = URL) as the Source locator with a new
     `kind="reference"`, distinct from importer-created sources.
   - The importer's dedupe/supersede must only act on memories it created
     (importer sources/episodes), never on `kind="reference"` memories that
     happen to share a locator. Builder adds a test for this.
   - `memory_edit` does not change the source; supersede (`memory_add` with
     `supersedes`) takes its own `source` argument.
   - Missing/moved file at render time: still rendered, with "(file not found)"
     after the link. *(my calls)*
4. **Refresh hook:** at the `MemoryService` level. Builder audits for direct
   repository mutation calls outside the service (importer, refresh, dashboard,
   CLI) and routes them through the service or the hook. Neighbors re-rendered:
   supersede predecessor/successor, both ends of an explicit link — including a
   link target in a *different* opted-in project. *(my call)*
5. **Deletes/orphans:** retracted (`deleted`) memories keep their page with a
   "Retracted" banner (no hard-delete path exists in the service). `vault sync`
   prunes orphaned generated files (marker present, no matching memory/project)
   so it converges to exactly what SQLite says; second run is a no-op.
   *(my call)*
6. **log.md without an event table:** derived from current state — one
   "created" entry per memory (`created_at`), plus a "superseded / marked wrong
   / retracted" entry at `invalid_at` (or `updated_at` for retracted) when set.
   Frontmatter `updated:` uses `Memory.updated_at`. No full edit history in
   this part. *(my call)*
7. **File catalog scope:** covers every registry folder mapped to the project
   (grouped per folder). `memory_list_files` follows the same project
   resolution and scope guard as other tools and is independent of vault
   opt-in (it reads the user's own folder for their own agent — no new
   exposure). Skip list = importer's `_SKIP_DIRS` plus all hidden dirs
   (covers `.git`). *(my call)*
8. **Config & jobs:** vault keys live in the same `config.json`, written
   atomically (temp + rename) via shared helpers alongside `semantic`;
   `vault_projects` holds bare project names. Full `vault sync` from the
   dashboard runs as a job through `refresh.py`'s single-job slot (same busy
   rule); dashboard "Update all" does not run it implicitly — a separate
   "Sync vault" action does. *(my call; replaces the earlier line saying
   files.md/index.md refresh on "Update all")*

## Left to the builder

Exact filename sanitization and length; catalog cap; recent-N on project page;
module split; how the service notifies the mirror (direct call vs small
observer); dashboard toggle styling.

## Open assumptions to verify during build

- Obsidian picks up externally written files live (expected; verify with a real
  vault if available, otherwise note unverified).
- `file://` links open from Obsidian on macOS/Windows.
