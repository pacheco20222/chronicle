# Global install — design

Date: 2026-11-22. Status: draft, awaiting owner approval.

## Why

Installing Chronicle per project (plugin install, `chronicle setup`, register)
is friction nobody should have to repeat. Install once, and any folder an
agent opens in should just work. This is also the precondition for the next
project (Obsidian + files linked to memories, for non-programmers), whose users
will never run per-project commands.

Primary client is **Claude Code**. Obsidian users run Claude Code wrapped in an
Obsidian plugin, so it behaves like Claude Code with the working folder set to
the vault. Claude Desktop is the secondary client.

## Goals

- One install command per machine; no per-project command in normal use.
- A new git repo becomes a project automatically the first time an agent uses
  Chronicle there.
- Per-project install keeps working exactly as today, for people who want it.
- Claude Desktop needs one config entry total, not one per project.

## Non-goals

- Cross-project search by name ("what did we do in the Dolphin campaign") and
  search quality — next project.
- Obsidian vault connector, file-to-memory links — next project.
- claude.ai web (needs a remote server; out of scope).
- Container packaging (dropped).

## Anti-goals (failure even if it "works")

- **Memories leaking between projects.** The 2026-09 global plugin attempt was
  disabled for exactly this (a pinned project name applied everywhere). Every
  request must still resolve to exactly one project or fail closed.
- **Junk projects** from Downloads, Desktop, home, or random folders.
- **Two different repos silently merged** into one project because they share
  a folder name.

## Approaches considered

1. **Chronicle registers the folder itself (chosen).** Resolution logic in the
   core runtime auto-registers git repos; other folders get a clear "ask the
   user, then register" error. A `chronicle setup --global` mode writes each
   app's user-level config once. Same behavior in every client because it
   lives in Chronicle, not the client.
2. **Claude Code SessionStart hook registers the folder.** Rejected: only
   Claude Code has hooks; Desktop, Cursor, Codex don't, and Obsidian wrappers
   may not run them.
3. **Instructions only** ("if unregistered, register"). Rejected: depends on
   each model's judgment — inconsistent asking and naming.

## Design

### 1. Resolution order (core, not MCP/CLI)

When a tool needs the current project and no `scope_path` was passed:

1. `CHRONICLE_PROJECT` env var, if set (unchanged — per-project installs).
2. Registry lookup for the working folder, including the existing worktree →
   main-repo fallback (unchanged).
3. **New — auto-register:** if the working folder is inside a git repo, take
   the repo's top-level folder (main worktree for a worktree). Register it
   under the folder's name, normalized the same way manual registration names
   are (builder's call on exact normalization; keep it predictable), then use
   it.
4. Otherwise fail closed with an actionable error (see 3).

Auto-register is skipped — falls through to step 4 — when:
- the top-level folder is the home folder or filesystem root (existing guard);
- the derived name is **already used by a different path** (would merge two
  repos). The error says so and suggests a distinct name.

Auto-registration lives in the core/registry layer (e.g. a
`resolve_project(cwd)` used by `config.get_project()`), never in MCP tool
bodies, so CLI, recall hook and server behave identically.

### 2. Telling the user

The first time a folder is auto-registered, the user should learn it once:
"Registered this folder as Chronicle project `<name>`." Mechanism is the
builder's call (e.g. a `notice` field on that tool result, and/or the
Claude Code recall hook line). Must not repeat on later calls.

### 3. Non-git folders (Obsidian vaults, plain folders)

The error returned to the agent names the folder and instructs: ask the user
whether to make this folder a Chronicle project and under what name, then call
`memory_register_project(name)`. No silent registration. Server instructions
and SKILL.md get one line matching this.

### 4. Claude Desktop (no folder)

One global entry, **no** `CHRONICLE_PROJECT`. Desktop runs one server process
shared by all chats, so the "current project" cannot be server state — it must
travel with each call as `scope_path` (already supported on the read/write
tools). When a Desktop call has neither, the error tells the agent to find the
project the user means via `memory_list_scopes`, confirm with the user if
ambiguous, and pass that `scope_path` for the rest of the chat. Existing
per-project Desktop entries (`chronicle-<project>`) keep working.

### 5. `chronicle setup --global`

One command that, per app, does the user-level equivalent of today's setup
and **omits `CHRONICLE_PROJECT`**:
- Claude Code: user-scope MCP server (`claude mcp add --scope user` or the
  user config file — builder picks the supported mechanism) plus the recall
  hook at user level.
- Cursor: `~/.cursor/mcp.json`.
- Codex: unchanged (already global), but no longer requires a project.
- Claude Desktop: single `chronicle` entry.

Reuses existing merge/backup/dry-run helpers (`_merge_server`,
`_write_json_atomic`, symlink-safe `.bak`). `--dry-run` prints what it would
write. Detect and warn (don't delete) if a per-project `.mcp.json` in the
current folder also defines `chronicle` — duplicate servers in one session.

### 6. Docs

INSTALL.md leads with global install; per-project install moves to an
"alternative" section. CHANGELOG entry.

## Constraints

- Local-first; no new services or dependencies.
- Scope guard stays: no request ever runs without exactly one resolved project
  (or explicit `scope_path` / global search).
- Backward compatible: existing registry, env-pinned configs, per-project
  plugin installs unchanged.
- Tests: auto-register git repo; worktree resolves to main repo; non-git folder
  fails with ask-the-user error; home/root refused; name clash refused, nothing
  registered; env var still wins; Desktop-style call without project or
  scope_path fails with the list-scopes guidance; `setup --global --dry-run`
  output per app.

## Left to the builder

- Name normalization details; exact notice mechanism; whether `setup --global`
  writes Claude Code config via CLI or file; Windows paths for user configs.

## To verify during build (assumption)

- Obsidian Claude Code wrappers start Claude Code with the working folder set
  to the vault root. If a wrapper uses a different folder, the
  ask-then-register flow still works, just under that folder.
