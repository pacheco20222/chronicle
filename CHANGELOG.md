# Changelog

## 2.6.0 — 2026-09-22

### Added
- Memory lifecycle: every memory has a `status` (`active`, `resolved`,
  `superseded`; default `active`). `memory_add` accepts `supersedes=<old
  memory id>`, which marks the old memory superseded automatically. New
  `memory_set_status(memory_id, status)` tool marks a memory resolved or
  superseded directly. Default retrieval (`memory_search`,
  `memory_search_global`, `memory_get_latest`) hides superseded
  memories.

## 2.5.0 — 2026-09-22

### Changed
- `mnemo graph`: KNN edges now default to same-project only, even in
  `--all` view. New `--cross-project` opts back into edges across
  projects. New `--min-similarity` (default 0.3) drops an edge entirely
  when the best match is too weak, instead of always wiring up k
  neighbors regardless of similarity.

## 2.4.0 — 2026-09-20

### Added
- `mnemo graph`: core memory (project overview) drawn as a gold ring, the
  latest checkpoint per project as a pulsing diamond, both labeled. Project
  chips isolate one project; "core + latest checkpoint only" hides
  everything else; search box dims non-matching memories. Projects cluster
  in their own region of the 3D space in `--all` view; view auto-fits on
  filter change.

## 2.3.2 — 2026-09-20

### Fixed
- `memory_search(type="checkpoint")` now returns checkpoints newest-first
  (query ignored). Semantic ranking could put an old checkpoint ahead of
  the latest for any agent that searched instead of calling
  `memory_get_latest` — the wrong-checkpoint bug is now impossible via
  either tool.

## 2.3.1 — 2026-09-20

### Fixed
- Git worktrees resolve to their main repo's registered project. Registry
  lookup matched exact folder only, so a session inside
  `<repo>/.worktrees/x` failed with "not registered". A worktree's own
  registration still wins if present.
- `register` refuses the home directory and filesystem root (a stray
  `~` registration silently bound any session run from home to a project).

## 2.3.0 — 2026-09-20

### Added
- `mnemo graph` renders a glowing 3D network you can orbit (drag) and
  zoom (scroll), with depth fading and light pulses along edges.
  Node dragging removed in favor of orbit.

### Fixed
- Session-start recall now prints the latest checkpoint FIRST, labeled
  "LATEST CHECKPOINT", and labels the project overview "NOT a
  checkpoint". Previously overview came first and an agent asked for
  "the latest checkpoint" answered from the (older) overview instead.
  Server instructions also state the overview is not a checkpoint.
- Graph HTML declares UTF-8 (fixed `Â·` mojibake over HTTP).

## 2.2.0 — 2026-09-15

### Added
- Cursor support: `.cursor/mcp.json` documented alongside `.mcp.json`,
  and `mnemo setup` now prints that block too.
- `memory_get_latest(type)` tool — the chronological "newest by
  `created_at`" lookup that already backed the Claude Code
  `SessionStart` hook's checkpoint auto-load is now callable directly.
  Previously the only tool available for "what's the latest
  checkpoint" was `memory_search`, which ranks by semantic similarity
  and can return an older, more textually-relevant memory instead of
  the actual newest one.
- `/mnemo:mnemo-register` now offers to seed a project overview
  ("core memory") right after registering, from `CLAUDE.md`/
  `AGENTS.md`/`PROJECT.md`/`README.md` if one exists, or a short
  paragraph otherwise. `overview` added as a first-class memory type
  instead of overloading `architecture` for it.
- `mnemo graph --all` — explicit opt-in for graphing every project's
  memories together.

### Changed
- Plugin install quick start now recommends `--scope project` by
  default instead of the implicit `user` (global) scope, so installing
  the plugin doesn't silently attach it to every repo you open.
- `mnemo graph` with no `--project` now defaults to the current
  directory's registered project, matching `memory_add`/
  `memory_search`'s existing isolation — previously it defaulted to
  graphing every project together, which read as project data
  leaking when it wasn't.
- Codex's documented setup no longer pins `MNEMO_PROJECT` per
  `codex mcp add`. Codex genuinely resolves the project from the
  current working directory against the same shared registry Claude
  Code's plugin uses — this was never actually verified before and
  the docs claimed the opposite, recommending a per-project server or
  profile workaround that was never necessary.

### Fixed
- Qdrant's data now lives in a named Docker volume instead of a bind
  mount inside the plugin's own install directory. The old bind mount
  path (`~/.claude/plugins/cache/mnemo/mnemo/<version>/qdrant_storage`)
  is deleted on every plugin uninstall and replaced on every version
  update — silently destroying all stored memories in the process,
  while the still-running Qdrant container kept answering requests
  with an orphaned storage path, making the failure confusing to
  diagnose.

## 2.1.1 — 2026-09-07

### Fixed
- FastEmbed's eager construction at module import (blocking the MCP stdio
  handshake past the client's startup timeout) is now deferred universally,
  not just on Windows — matching the same lazy-init pattern already used
  for the Qdrant client. Guarded with a lock against the first two
  concurrent tool calls racing to construct the model twice.
- `mnemo setup`'s generated Windows commands no longer corrupt project
  names or paths containing `` ` ``, `$`, or `"` — the SessionStart hook
  command is now passed via PowerShell's `-EncodedCommand` (base64)
  instead of hand-escaped nested quoting, which also sidesteps `cmd.exe`
  metacharacters entirely. The printed Codex command now states it must
  be run from PowerShell, not `cmd.exe`.
- Windows CI job now has a 15-minute timeout, so a stalled model download
  fails the run instead of hanging silently.

## 2.1.0 — 2026-09-06

### Added
- Native Windows support: `scripts/backup.ps1`, `export_json.ps1`, and
  `daily_backup.ps1` as PowerShell twins of the existing bash scripts
  (same behavior, no shared code). Documented `schtasks` command as
  the `launchd`-plist equivalent for the daily schedule. WSL2 needs no
  code changes — it's Linux underneath, and is now called out in the
  README/docs as a supported path.

## 2.0.1 — 2026-09-05

### Fixed
- Qdrant client connection deferred to first actual tool use instead of at
  module import — a fresh install (Qdrant not started yet) used to crash
  the MCP server before it could even start, surfacing only as a generic
  connection failure with no indication why.
- `/mnemo:mnemo-register` no longer prints a Codex command unconditionally
  — only relevant if you actually use Codex, and Codex has no way to
  invoke this command in the first place.
- README.md and docs/INSTALL.md corrected: the register command's real
  invocable name is `/mnemo:mnemo-register` (plugin-namespaced), not
  `/mnemo-register`.

### Added
- The server now asks before updating the project overview document when
  it notices a relevant change, and periodically asks about saving a note
  — both opt-in, never automatic.

## 2.0.0 — 2026-09-03

### Changed
- **Breaking:** embeddings now run locally via `fastembed` (`nomic-embed-text-v1.5`, ONNX Runtime, CPU-only) instead of Ollama. No GPU, no background service, no separate app to install — `fastembed` installs like any other Python dependency. Existing memories remain valid Qdrant points but are no longer in the same embedding space as anything newly written; no automatic migration is performed.
- `mnemo import`'s chunk size widened from ~1500 to ~6000 tokens (6000→24000 chars), taking advantage of the new backend's 8192-token context window (vs. Ollama's configured 2048).

### Removed
- Ollama and `httpx` as dependencies.

## 1.2.0 — 2026-09-02

### Added
- Local folder-to-project registry (`~/.mnemo/projects.json`) and `memory_register_project` tool / `mnemo register --project X` CLI — lets a repo register itself without writing any file into that repo.
- `.mcp.json` and `hooks/hooks.json` now bundled directly in the plugin — installing it once makes the MCP server and the checkpoint/resume hook available in every session, everywhere. `MNEMO_PROJECT` no longer needs to be baked into either.
- `/mnemo-register <project>` replaces `/mnemo-setup` — same Qdrant/Ollama checks, but registers the folder instead of writing `.mcp.json` into it.

### Fixed
- `server.py` no longer resolves the project once at import time — it's now resolved per tool call, so the server always starts even in a brand-new, unregistered folder (previously it would crash before a registration tool could ever run there).

## 1.1.0 — 2026-09-02

### Added
- Claude Code plugin packaging (`.claude-plugin/plugin.json` + `marketplace.json`) — installable via `/plugin marketplace add pacheco20222/mnemo` then `/plugin install mnemo`, no cloning required for the Claude Code side.
- `/mnemo-setup <project>` command — starts Qdrant if it isn't running, checks for the `nomic-embed-text` model, and writes/merges this repo's `.mcp.json` and (optionally) the checkpoint/resume `SessionStart` hook. Replaces copy-pasting `mnemo setup`'s terminal output by hand.
- `mnemo setup` now also prints the `SessionStart` hook block (previously only documented manually in INSTALL.md, not printed).

## 1.0.0 — 2026-09-02

First packaged release. Everything below was built and proven across
five real repositories before this release was cut.

### Added
- Core memory: `memory_add`, `memory_search`, hard project isolation via `MNEMO_PROJECT`.
- `memory_search_global` — explicit cross-project search.
- `mnemo import` — bulk-load a file into a project's memory, with paragraph-aware chunking to stay under the embedding model's context window.
- Checkpoint/resume — `memory_add(type="checkpoint")` + automatic recall via a `SessionStart` hook.
- Named documents — `memory_set_document`/`memory_get_document`, replace-in-place by slug, with the project overview auto-loading every session.
- `mnemo graph` — a real embedding-similarity graph of your memories, rendered locally.
- `mnemo setup` — prints ready-to-paste Claude Code and Codex configuration with the real install path filled in.
- Scheduled backups (`launchd`) with retention, plus a flat JSON export.
