# Lexical-by-default mode: Qdrant and the embedding model become opt-in

Status: implemented in 3.2.0 with the recommended decisions: default `lexical`;
setting in `~/.chronicle/config.json` with `CHRONICLE_SEMANTIC` override;
Porter-stemming migration deferred; shipped as 3.2.0 with a CHANGELOG notice.
Steps 1-3 and 5 below are done. Still open: a dedicated dashboard empty state
for the similarity graph (nodes render without edges today), the optional
`chronicle[semantic]` extra, and the tokenizer migration.

## Problem

The first useful memory today needs Docker (for Qdrant), a ~500 MB embedding
model download on the first save, and `fastembed`/`onnxruntime` installed.
Two independent pre-listing audits named this the single biggest
time-to-first-value drop-off: Docker not installed or not running, port 6333
busy, a first `memory_add` that looks hung during the download.

Almost none of what Chronicle does needs vectors:

| Capability | Needs vectors? |
|---|---|
| `memory_add`, status/edit/link/merge/split, scopes | No (stored in SQLite; the vector is a side write) |
| Checkpoint save and `memory_get_latest`, session-start recall | No (SQL `recent`) |
| Named documents (`memory_set_document`/`get_document`) | No |
| `memory_search` / `memory_search_global` | Hybrid today: vector + FTS5, merged with RRF (`core/service.py` `_search`) |
| Dashboard similarity edges, `chronicle graph` | Yes (`get_all_with_vectors`) |
| `chronicle eval` duplicate/contradiction proxies | Yes (already reports "unavailable" when vectors are missing) |

SQLite is already authoritative (CLAUDE.md memory invariants), and FTS5 with
`bm25()` already exists (`core/repository.py` `lexical`). The project rule
"do not make vector similarity the only retrieval mechanism" points the same
way.

## Simplest mechanism

One switch, `semantic`, off by default:

- **Off (new default):** no Qdrant, no model, no `fastembed` import. Writes
  skip the embedding and the vector upsert. Search is lexical only.
- **On:** exactly today's behavior (hybrid RRF).

Implementation shape, using the existing `VectorIndex` protocol
(`core/vector_index.py`) as the seam, so `MemoryService` barely changes:

1. `NullVectorIndex`: `upsert`/`delete` no-ops, `search` returns `[]`,
   `all` returns `[]`. `create_runtime` (`core/runtime.py`) picks it when
   semantic is off. `QdrantVectorIndex` is imported lazily so `qdrant_client`
   isn't loaded at all in lexical mode.
2. `config.semantic_enabled()` is the single place the mode is decided.
3. The server (`server.py`) and `import_cli.py` call
   `embeddings.embed_text(...)` before every write and search. Wrap that in one
   helper, `embed_or_empty(text)`, which returns `[]` when semantic is off, so
   the model is never touched. Service signatures stay unchanged (they accept a
   vector sequence; `NullVectorIndex` ignores it).
4. `QdrantUnavailableMiddleware` (`server.py`) only matters in semantic mode.
   `services.status_lines()` and `chronicle start` stop treating "Qdrant down"
   as an error in lexical mode, and report the mode instead.

## Lexical search must get better first

The current lexical path is the weak link. `_fts_phrase` wraps the whole query
in quotes, so only an **exact phrase** matches. In hybrid mode the vector side
hides that; in lexical-only mode a query like "what did we decide about auth"
would return nothing. Changes:

- Build the FTS5 query from tokens: strip punctuation, drop a small stopword
  list, prefix-match each token (`tok*`), join with `OR`, rank by `bm25()`
  (already used for ordering). Quote every token so user text can never inject
  FTS5 operators.
- Optional: rebuild `memory_fts` with `tokenize='porter unicode61'` so
  "deploying" matches "deploy". This is an Alembic migration that recreates the
  virtual table and its triggers and backfills from `memory` (SQLite stays
  authoritative, so it is safe and repeatable). Keep it a separate step from the
  mode switch so each can be reviewed and reverted on its own.
- Tests: recall of natural-language queries, prefix and stem matches, project
  isolation, superseded/deleted filtering, and injection-shaped queries
  (quotes, `NEAR`, `*`, `-`).

## Turning semantic search on later

- `chronicle semantic enable`: checks Docker, starts Qdrant (`services.ensure_qdrant`),
  writes the setting, then runs `chronicle reindex` so existing memories get
  vectors (downloads the model once, with progress output instead of a silent
  hang).
- `chronicle semantic disable`: writes the setting; leaves Qdrant data alone.
- `chronicle reindex` is needed anyway: there is currently no way to rebuild the
  derived index from SQLite, although the docs say the index is "rebuildable".
  It iterates memories in SQLite and upserts embeddings. It also repairs the
  case where a memory was saved while Qdrant was unreachable.
- Where the setting lives: `~/.chronicle/config.json` (`{"semantic": true}`),
  overridable by `CHRONICLE_SEMANTIC=1|0`. A file, not only an env var,
  because the MCP processes launched by Claude Desktop/Cursor/Codex don't share
  a shell environment, and users shouldn't edit each agent's config to switch
  modes.

## What degrades in lexical mode (and how it is surfaced)

- Search is keyword-based: synonyms and paraphrases won't match. Tool results
  and `chronicle` status say `search: keyword (semantic off)`.
- Dashboard and `chronicle graph`: no similarity edges. The scope tree,
  core/checkpoint markers, and memory list still work; the graph view needs a
  clear empty state ("enable semantic search for the similarity graph") instead
  of an error. `get_all_with_vectors` returns records with no vector.
- `chronicle eval` duplicate/contradiction proxies print "unavailable" (that
  code path already exists).

## Packaging follow-up (optional, separate PR)

Move `fastembed` and `qdrant-client` into an extra, `chronicle[semantic]`, so
the base install is small and quick. `chronicle semantic enable` would tell the
user to run `uv tool install --editable ".[semantic]"` (or the PyPI equivalent
once published). This is what makes "install in under a minute" true, but it
changes installation commands in every doc, so it ships after the mode switch
is proven.

## Migration and compatibility

- Fresh installs: lexical, nothing to start.
- Existing installs have semantic memories in Qdrant. After upgrading they get
  lexical search until they run `chronicle semantic enable` (a no-op reindex
  if Qdrant already holds the vectors; it just flips the setting). This is a
  behavior change, so it needs a prominent CHANGELOG entry and a one-time notice
  in the session-start/`chronicle` status output.
- No schema change for the mode switch itself. The tokenizer migration is
  forward-compatible (rebuilds a derived table).
- `docker-compose.yml`, `chronicle start`, and the Qdrant docs stay, now under
  "optional semantic search".

## Tradeoffs

- (+) Time to first value drops to: install, `chronicle setup <agent>`, save.
  No Docker, no download.
- (+) Fewer failure modes (port conflicts, Docker not running, model download).
- (+) Matches the repo's own rule that vectors must not be the only retrieval.
- (-) Lower recall on paraphrased queries until semantic is enabled. Mitigated by
  better lexical matching, and by recall being mostly "latest checkpoint" and
  "named document", which never needed vectors.
- (-) Two modes to test and document. Mitigated by keeping one seam
  (`VectorIndex`) and running the existing hybrid tests unchanged.
- (-) The dashboard graph is the flagship visual and needs vectors. Mitigated by
  an honest empty state and a one-command upgrade.

## Open decisions

1. **Default mode:** `lexical` (recommended, predictable) vs `auto` (use hybrid
   when Qdrant answers, else lexical). `auto` is friendlier to existing users
   but silently triggers the 500 MB download for anyone who happens to have
   Qdrant running, and memories saved during an outage miss vectors.
2. **Setting location:** `~/.chronicle/config.json` plus env override
   (recommended) vs env var only.
3. **Porter stemming migration:** include in the first PR or follow up.
4. **Version:** ship as 3.2.0 with a clear notice, or 4.0.0 because default
   search behavior changes.

## Suggested order of work

1. Better lexical query building + tests (valuable even in hybrid mode).
2. `NullVectorIndex`, `embed_or_empty`, `config.semantic_enabled()`, lazy
   imports, status/middleware changes, tests for both modes.
3. `chronicle reindex`, `chronicle semantic enable|disable`.
4. Dashboard/graph empty state.
5. Docs: quick start without Docker; semantic search as an upgrade.
6. Optional extras packaging and tokenizer migration.
