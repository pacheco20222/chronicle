# Chronicle

Self-hosted, project-scoped memory for Claude Code, Cursor, and Codex.
No cloud services, no paid APIs — everything runs on your own machine.

Chronicle gives an AI coding agent a place to remember things across
sessions: architecture decisions, in-progress debugging state, a
running project brief — scoped so a session in one repo can never see
another repo's memory by accident.

## What it does

- **`memory_add` / `memory_search`** — write and recall memories, hard-scoped to the current project.
- **Checkpoint/resume** — say "checkpoint this" before a long session ends; it's recalled automatically the next time you start one.
- **Named documents** — a project overview or running dev log that updates in place instead of piling up, also auto-loaded every session.
- **`memory_search_global`** — the one explicit, deliberate escape hatch for a genuinely cross-project question.
- **`chronicle import`** — bulk-load an existing file into a project's memory. Run yourself, from a terminal — see [docs/INSTALL.md §6](docs/INSTALL.md#6-running-chronicles-other-commands-import-graph).
- **`chronicle graph`** — a real, embedding-similarity graph of your memories, rendered as a glowing 3D network you can orbit and zoom (core memory = gold ring, latest checkpoint = diamond; filter by project, search, or show only key memories), locally and opened in your browser. Scoped to the current project by default, same as everything else; `--all` graphs every project together, deliberately. Same terminal invocation as `import` above.

- **`chronicle dashboard`** — a local React/Three.js memory dashboard served through FastMCP streamable HTTP. Run `uv run chronicle dashboard start` for foreground mode, `uv run chronicle dashboard start --background` for a persistent local process, and `uv run chronicle dashboard stop` to stop it. It binds only to `127.0.0.1:8765` by default; set `CHRONICLE_DASHBOARD_PORT` or pass `--port` to change the port.

## Requirements

- macOS, Linux, or Windows (PowerShell 5.1+/pwsh, or WSL2 — anything
  Linux-based in this repo just works unmodified under WSL2)
- [Docker](https://www.docker.com/) or [OrbStack](https://orbstack.dev/) (Qdrant runs in a container)
- [uv](https://docs.astral.sh/uv/)

No GPU, no separate embedding service — `fastembed` runs locally on CPU
and installs like any other Python dependency. Chronicle initializes it only
when the first memory tool is called, so loading or downloading the model
does not delay the MCP startup handshake on Windows, macOS, or Linux.

## Quick start (Claude Code plugin)

Prerequisite: [Docker](https://www.docker.com/)/[OrbStack](https://orbstack.dev/)
installed (running is enough — `/chronicle:chronicle-register` starts Qdrant for you).

Inside Claude Code, in whichever repo you want memory in:

```
/plugin marketplace add pacheco20222/chronicle
/plugin install chronicle --scope project
/chronicle:chronicle-register my-first-project
```

`--scope project` keeps Chronicle scoped to this one repo — installing it
here doesn't make it show up in any other project you open. That's the
recommended default: each repo gets its own isolated memory, and
nothing connects to anything else unless you say so. Want it available
in another repo too? Run the same three commands there (with that
repo's own project name) — nothing gets written into either repo
either way. `/chronicle:chronicle-register` starts Qdrant if it isn't already
running, then registers the current folder under that project name in
a small file outside any repo (`~/.chronicle/projects.json`). The first
`memory_add` you make downloads the embedding model automatically
(~500MB, one-time). `memory_add`/`memory_search` work immediately,
same session, no restart.

Right after registering, it asks if you want to add a core memory —
a project overview, seeded from `CLAUDE.md`/`AGENTS.md`/`PROJECT.md`/
`README.md` if one exists (condensed, not pasted verbatim) or a short
paragraph you give it otherwise. It's optional and only happens if you
say yes; you can always add or replace it later the same way.

Already registered this folder some other way — via Codex, or `chronicle
register` from a terminal — and just want Claude Code to pick up the
same project here? Skip `/chronicle:chronicle-register` entirely:

```
/plugin marketplace add pacheco20222/chronicle
/plugin install chronicle --scope project
```

That's the whole thing. The plugin resolves the project the same way
Codex does — env var if set, otherwise the shared registry
(`~/.chronicle/projects.json`) keyed by this folder — so an existing
registration just works, no re-registering per tool.

Want Chronicle available everywhere without installing it repo by repo?
Use `--scope user` instead (Claude Code's default if you omit
`--scope`) — the plugin itself is then available in every project, but
each repo still needs its own `/chronicle:chronicle-register` before memory
tools work there, so nothing is silently connected. Two repos only
ever share the same memories if you deliberately register both under
the *same* project name — that's the one supported way to "join"
projects, and it's opt-in, never automatic.

If `/plugin install chronicle --scope project` says "already installed"
instead of enabling it, that means chronicle is already installed
somewhere else on your machine (e.g. at `user` scope from an earlier
setup) — Claude Code only ever installs a plugin's code once. Use
`/plugin enable chronicle --scope project` instead; that's the command
that actually toggles a scope on for an already-installed plugin.

## Quick start (manual / Cursor / Codex)

First, once, regardless of which of these you use:

```bash
git clone git@github.com:pacheco20222/chronicle.git
cd chronicle
docker compose up -d
```

These three work differently from each other — read the one that
applies to you, not all three in sequence.

**Claude Code (manual, non-plugin):** for each repo you want memory
in, run `uv run chronicle setup --project my-project-name` and paste the
printed `.mcp.json` block into that repo. The project is baked into
the pasted file — nothing else to do, no separate registration.
Repeat per repo, with that repo's own `--project` value.

**Cursor:** identical to Claude Code above — same `chronicle setup
--project X`, same per-repo repeat — except paste the block into
`.cursor/mcp.json` instead of `.mcp.json`.

**Codex is different: two separate steps, not one command per
project.**

1. Set up the MCP server **once, ever**, with no project attached:
   ```bash
   codex mcp add chronicle -- uv run --project /absolute/path/to/chronicle chronicle
   ```
   Never repeat this for a new project — one server entry serves
   every project you register from here on.
2. **For every project folder** you want memory in, register it —
   this is the step it's easy to miss, since Codex has no plugin
   command to do it for you:
   ```bash
   cd /path/to/your-project
   uv run --project /absolute/path/to/chronicle chronicle register --project your-project-name
   ```
   Run once per folder, from inside that folder. From then on, any
   Codex session started there resolves to `your-project-name`
   automatically — Codex reads the project from your current
   directory against the same registry Claude Code's plugin uses
   (`~/.chronicle/projects.json`), not from anything in step 1.

On native Windows, run `uv run chronicle setup` from PowerShell for the
Claude Code/Cursor blocks and the Codex one-time command, with
quoting handled for you — `chronicle register` itself needs no special
Windows handling.

See [docs/INSTALL.md](docs/INSTALL.md) for the full walkthrough. If
the MCP connects but the first `memory_add` or `memory_search` fails
while FastEmbed loads or downloads the model, follow the
[first-tool troubleshooting steps](docs/INSTALL.md#mcp-connects-but-the-first-memory-tool-fails).

## How it works

Qdrant (vector store) + fastembed (`nomic-embed-text-v1.5`, local
CPU embeddings, no separate service) + FastMCP (the MCP server itself,
stdio transport). See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
every tool's exact signature.

## Upgrading from 1.x

2.0.0 changes the embedding backend (Ollama → fastembed) — see
[CHANGELOG.md](CHANGELOG.md). Old and new embeddings share the same 768
dimensions but are **not** the same vector space, and Qdrant can't detect
the difference. If you're upgrading an existing install, either start a
fresh `memories` collection, or expect old memories to rank essentially
randomly against new ones in semantic search until you re-add them.

## License

MIT — see [LICENSE](LICENSE).
