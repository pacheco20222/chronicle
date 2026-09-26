# Architecture

## Stack

| Layer | Choice | Why |
|---|---|---|
| Vector store | [Qdrant](https://qdrant.tech/) (Docker) | Single container, stores vectors + metadata together, free |
| Embeddings | `nomic-embed-text-v1.5` via [fastembed](https://github.com/qdrant/fastembed) | Local, free, CPU-only, no external API call, no background service |
| MCP server | [FastMCP](https://gofastmcp.com/) (Python), stdio transport | No network exposure, low boilerplate |

Qdrant is the only always-on process. The MCP server itself is spawned
as a subprocess per session by Claude Code or Codex — it is not a
background daemon.

## Data model

Every memory is one Qdrant point:

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Random for regular memories; deterministic (`uuid5(project:slug)`) for named documents |
| `vector` | float[768] | `nomic-embed-text-v1.5` embedding of `content` |
| `project` | string | Required on every point — the hard isolation boundary |
| `type` | string | `decision` \| `architecture` \| `bug` \| `todo` \| `note` \| `checkpoint` \| `overview` |
| `content` | string | The memory text |
| `created_at` | ISO8601 UTC | |
| `source` | string, optional | File path for `chronicle import`-created memories |
| `slug` | string, optional | Present only on named documents |
| `updated_at` | ISO8601 UTC, optional | Present only on named documents, refreshed on every `memory_set_document` call |

## Project isolation

Every tool except `memory_search_global` is implicitly scoped to a
project, resolved fresh on every call: `CHRONICLE_PROJECT` from the
environment if set, else a lookup of the current folder in a small
local registry (`~/.chronicle/projects.json`, written by
`memory_register_project` or `chronicle register --project X`) — fail-closed
if neither resolves. No tool takes a `project` parameter, so there's
no way to accidentally read or write another project's memories from
inside a session. `memory_search_global` is the one deliberate,
explicitly-named exception — isolation by tool choice, not a per-call
permission check.

## Tools

- **`memory_add(content: str, type: str) -> dict`** — always creates a new memory. `type` must be one of the five listed above, or `checkpoint`.
- **`memory_search(query: str, type: str | None = None, k: int = 5) -> list[dict]`** — semantic search, scoped to the current project.
- **`memory_search_global(query: str, type: str | None = None, k: int = 5) -> list[dict]`** — the same search, across every project. Use only for an explicitly cross-project ask.
- **`memory_set_document(slug: str, content: str, type: str) -> dict`** — replace-in-place, keyed by `(project, slug)`. Use for content that should supersede its previous version — a project overview, a running dev log — not accumulate.
- **`memory_get_document(slug: str) -> dict | None`** — exact lookup by slug, no embedding call involved.
- **`memory_get_latest(type: str) -> dict | None`** — newest memory of that type by `created_at`, no embedding call involved. Use this for "what's the latest checkpoint" — `memory_search` ranks by semantic similarity to the query text, not recency, and can return an older but more textually-relevant memory instead of the actual newest one.
- **`memory_register_project(name: str) -> dict`** — registers the current folder (the server's own working directory) under `name` in the local registry, so future calls in that folder resolve the project automatically. Needs no project to already be set — this is how a brand-new, unregistered folder bootstraps.

## Checkpoint / resume

`memory_add(..., type="checkpoint")` is a normal memory with one
convention: the server's own `instructions` field tells the connected
model to use it when asked to checkpoint, and to write it so someone
with zero memory of the conversation could resume from it alone.
Recall is a `SessionStart` hook running `chronicle-recall`, which does a
direct, chronological (`order_by`, not semantic search) Qdrant lookup
for the newest checkpoint — no embedding call on the read path.

## Named documents auto-load

By convention (not enforced in code), a project's own overview
document uses the project's own id as its `slug`. The same
`SessionStart` hook that recalls the latest checkpoint also looks up
that one document and prints it, so both show up automatically at the
start of every session.

## `chronicle import`

`chronicle import <file> --project X --type Y` splits the file on
paragraph breaks, grouping consecutive paragraphs up to ~24000
characters (~6000 tokens) per chunk — comfortably under
`nomic-embed-text-v1.5`'s 8192-token context window. Multi-chunk files
are tagged via `source`: `"<file> (chunk 2/5)"`. **Known limitation:**
unlike the previous Ollama backend, which raised a
clear error on over-length input, `fastembed` silently truncates text
beyond the context window instead of erroring. The ~24000-character chunk
size is sized for English prose (~4 chars/token) — code, JSON, and
non-Latin-script text tokenize far denser (measured: Python ~2.9
chars/token, JSON ~1.6, Chinese ~1.0), so a normally-sized chunk of
code-heavy or non-English content can already exceed the 8192-token limit
and get silently truncated, not only an oversized single paragraph. No
validation catches this today — a real fix (a token-count guard in
`chronicle import`, using the tokenizer already loaded in-process) is a
follow-up, not part of this change.

## `chronicle graph`

`chronicle graph [--project NAME] [--out PATH]` computes real pairwise
cosine similarity between every matching memory's embedding, keeps
each node's top-3 nearest neighbors as edges, and renders it as a
self-contained HTML file (dark, force-directed, Canvas-rendered) that
opens in your browser. Not decorative — the connections are the
model's own actual similarity judgments.

## `chronicle setup` / `chronicle register`

`chronicle setup` resolves its own install location at runtime
(`Path(__file__).resolve().parents[2]`) and prints ready-to-paste
Claude Code and Codex configuration — still the right tool for a
manual, non-plugin install, or for generating the Codex command by
hand. `chronicle register --project X` is the plugin-install path instead:
it writes `Path.cwd()` (the folder it's run from) against that project
name into `~/.chronicle/projects.json`, nothing into the repo itself. Both
are thin CLI wrappers with no logic of their own beyond argument
parsing — `chronicle setup` around string formatting, `chronicle register`
around `registry.register`.

## Backups

`scripts/backup.sh` creates a Qdrant snapshot; `scripts/export_json.sh`
exports every memory as a flat, human-readable JSON file (no vectors).
Both prune to the newest 14. `scripts/daily_backup.sh` runs both in
sequence — see `scripts/com.chronicle.dailybackup.plist` for the macOS
`launchd` schedule (3 AM daily).
