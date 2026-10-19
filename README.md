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
- **Hierarchical scopes** — group related projects under a shared parent (e.g. `personal_projects/heliofi/heliofi_backend`) with `memory_list_scopes`/`memory_scope_reparent`, or `chronicle scope create/list/move` from a terminal — see [docs/INSTALL.md § Organizing projects](docs/INSTALL.md#organizing-projects-into-cores-and-sub-cores) for the exact commands to build one and connect existing projects to it. Reorganizing is always something you ask for, never automatic — a project's own memories stay keyed to it regardless of where it's filed in the tree.
- **`memory_search_global`** — the one explicit, deliberate escape hatch for a genuinely cross-project question.
- **`chronicle import`** — bulk-load an existing file (or a whole directory of `.md`/`.txt` files) into a project's memory, chunking large files instead of truncating them. Run yourself, from a terminal — see [docs/INSTALL.md §7](docs/INSTALL.md#7-running-chronicles-other-commands-import-graph-dashboard-scope).
- **`chronicle graph`** — a real, embedding-similarity graph of your memories, rendered as a glowing 3D network you can orbit and zoom (core memory = gold ring, latest checkpoint = diamond; filter by project, search, or show only key memories), locally and opened in your browser. Scoped to the current project by default, same as everything else; `--all` graphs every project together, deliberately. Same terminal invocation as `import` above.
- **`chronicle dashboard`** — a persistent, local React/Three.js memory explorer, themed as a navigable star chart: every project is its own constellation with its core memory anchoring the center (the way Sagittarius A* anchors the Milky Way), and a scope with children renders as its own sun/planet/moon body — depth in your taxonomy maps onto depth in the solar system, children always orbiting their parent. From inside your chronicle clone:
  ```bash
  cd /path/to/chronicle
  (cd dashboard && npm ci && npm run build)     # once, needs Node.js
  uv run chronicle dashboard start              # foreground
  uv run chronicle dashboard start --background  # persistent local process
  uv run chronicle dashboard stop                # stop a backgrounded one
  ```
  or, with `chronicle` on your PATH (below), just `chronicle start` from anywhere — it also starts Qdrant if it isn't running. It binds only to `127.0.0.1:8765` by default; set `CHRONICLE_DASHBOARD_PORT` or pass `--port` to change the port. It always serves every registered project at once, not just the one you're standing in — see [docs/INSTALL.md §7](docs/INSTALL.md#7-running-chronicles-other-commands-import-graph-dashboard-scope) for more.
- **The `chronicle` command** — `uv tool install --editable .` from your clone puts `chronicle` on your PATH (bash, zsh, PowerShell, cmd). Then `chronicle --help` (or plain `chronicle` in a terminal) lists every command, `chronicle start` / `chronicle stop` replace the long `uv run --directory …` lines, and `chronicle update` pulls the latest version. MCP configs are unaffected — see [docs/INSTALL.md §7](docs/INSTALL.md#recommended-put-chronicle-on-your-path).

## Requirements

- macOS, Linux, or Windows 10/11 — natively from PowerShell 7, Windows
  PowerShell 5.1, cmd, or Git Bash, or under WSL2 (anything Linux-based in
  this repo works unmodified there). Windows users: see
  [Windows](#windows) for the full setup.
- [uv](https://docs.astral.sh/uv/)
- *Optional:* [Docker](https://www.docker.com/) or [OrbStack](https://orbstack.dev/), only for similarity (semantic) search; see below
- [Node.js](https://nodejs.org/), only to build the dashboard frontend

**Out of the box, Chronicle needs no Docker and downloads no model.** Saving,
checkpoints, project documents and keyword search (SQLite FTS5) work
immediately. To also find memories by meaning (paraphrases, synonyms) and get
the similarity graph, turn on semantic search once:

```bash
uv tool install --editable ".[semantic]" --force   # once, from your clone: adds fastembed + qdrant-client
chronicle semantic enable    # starts Qdrant in Docker, downloads the ~500MB model once, indexes your memories
chronicle semantic disable   # back to keyword-only; nothing is deleted
```

The base install is small on purpose: `fastembed` and `qdrant-client` live in the
optional `semantic` extra.

No GPU and no separate embedding service: `fastembed` runs locally on CPU, and
the model is only loaded when semantic search is on.

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
```

(Docker is only needed if you later turn on semantic search with
`chronicle semantic enable`.)

These three work differently from each other — read the one that
applies to you, not all three in sequence.

**Claude Code (manual, non-plugin):** for each repo you want memory
in, run `uv run chronicle setup --project my-project-name` and paste the
printed `.mcp.json` block into that repo. The project is baked into
the pasted file — nothing else to do, no separate registration.
Repeat per repo, with that repo's own `--project` value.

**Cursor:** same idea as Claude Code above, just a different filename.
For each repo you want memory in, run:

```bash
uv run chronicle setup --project my-project-name
```

and paste the `.mcp.json` block it prints into a **`.cursor/mcp.json`**
file (not `.mcp.json`) at that repo's root — it's the identical JSON
shape either way:

```json
{
  "mcpServers": {
    "chronicle": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/chronicle", "run", "chronicle"],
      "env": {
        "CHRONICLE_PROJECT": "my-project-name"
      }
    }
  }
}
```

The project is baked into this file, so nothing else to do — no
separate registration step, unlike Codex below. Then, in Cursor, open
**Settings → Tools & MCP** and switch the `chronicle` server **on** —
Cursor detects the new file but does not start a newly added project
server by itself, so until you flip that toggle it shows as
disconnected and the agent has no chronicle tools at all. Wait for a
green/connected status (reload the window if it doesn't appear), and
only then ask the agent to use it. The project itself is created the
first time a memory is saved. Repeat per repo, with that repo's own
`--project` value.
Cursor has no plugin/marketplace system and no session-start-hook
equivalent, so there's no one-command install path the way Claude
Code's plugin has, and no automatic checkpoint/document recall at the
start of a session — see
[docs/INSTALL.md §5](docs/INSTALL.md#5-cursor) for how to ask for that
recall manually instead.

**Claude Desktop app (Chat tab):** different from Claude Code: no plugin,
no auto-recall hook, and no folder to infer a project from. You edit
`claude_desktop_config.json` by hand, with an **absolute path to `uv`**
(the app does not see your shell `PATH`), then fully quit and reopen the
app. Follow the numbered steps in
[docs/INSTALL.md §4](docs/INSTALL.md#4-claude-desktop-the-chat-tab).
This does not cover claude.ai in a browser, see
[Known gap](#known-gap-local-clients-only-not-cloud-chat).

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

## Windows

Chronicle runs natively on Windows 10/11; no WSL needed. Every command
below works the same in PowerShell 7, Windows PowerShell 5.1, cmd, and
Git Bash (including the older mintty window).

### One-time setup

1. **Install the prerequisites.** In PowerShell (or download each installer):
   ```powershell
   winget install Docker.DockerDesktop
   winget install astral-sh.uv
   winget install Git.Git
   winget install OpenJS.NodeJS.LTS   # only needed for the dashboard
   ```
   Then open **Docker Desktop** once and let it finish starting.
2. **Clone Chronicle and put the `chronicle` command on your PATH:**
   ```powershell
   git clone https://github.com/pacheco20222/chronicle.git
   cd chronicle
   uv tool install --editable .
   ```
   This installs `chronicle.exe` into `%USERPROFILE%\.local\bin`. If a new
   terminal says `chronicle` isn't recognized, run `uv tool update-shell`
   once and open a new terminal.
3. **Build the dashboard** (optional, needs Node.js):
   ```powershell
   cd dashboard; npm ci; npm run build; cd ..
   ```
4. **Start everything and check it's healthy:**
   ```powershell
   chronicle start
   ```
   This starts Qdrant in Docker if it isn't running, then the dashboard at
   http://127.0.0.1:8765. Typing plain `chronicle` at any time shows every
   command plus a status line telling you whether Qdrant and Docker are up.
5. **Connect a project.** Either install the Claude Code plugin from
   [Quick start (Claude Code plugin)](#quick-start-claude-code-plugin) (it
   works the same on Windows), or, for a manual setup, run this from your
   project folder and paste what it prints:
   ```powershell
   chronicle setup --project my-project
   ```
   On Windows it prints forward-slash paths and a PowerShell-safe
   session-start hook, so the output can be pasted as-is.

### Everyday commands

| Command | What it does |
|---|---|
| `chronicle` | Command list + Docker/Qdrant status |
| `chronicle start` | Start Qdrant (if needed) and the dashboard; add `--port N` or `--background` |
| `chronicle stop` | Stop a `--background` dashboard |
| `chronicle register NAME` | Register the current folder as a project (`--force` to re-register under a new name) |
| `chronicle setup AGENT --project NAME` | Write the MCP config for `claude-desktop`, `claude-code`, `cursor` or `codex` (`--print` to preview) |
| `chronicle update` | Switch the clone to `main`, pull the latest, sync dependencies, rebuild the dashboard |
| `chronicle <command> --help` | Every option for one command |

You never have to start the MCP server yourself: Claude Code, Cursor,
Codex and Claude Desktop launch it on their own. Only Docker Desktop has
to be running.

### Good to know on Windows

- **Docker Desktop must be running.** If it isn't, `chronicle`,
  `chronicle start`, and memory tools in Claude all say so ("Docker is
  installed but not running. Open Docker Desktop…") instead of showing a
  raw `WinError 10061`.
- **Paths in JSON/TOML configs** (`.mcp.json`, `.cursor/mcp.json`,
  `claude_desktop_config.json`, Codex `config.toml`) need forward slashes
  (`C:/Users/you/chronicle`) or doubled backslashes. A single backslash is
  invalid.
- **Your data** lives in `%USERPROFILE%\.chronicle`: the SQLite database,
  the project registry, and the embedding model (~500MB, downloaded on the
  first memory you save).
- **Background dashboard:** `chronicle start --background` keeps running
  after you close the terminal; stop it with `chronicle stop`.
- **Claude Desktop app:** use an absolute path in `command`, e.g.
  `C:/Users/you/.local/bin/chronicle.exe` with no `args`; see
  [docs/INSTALL.md §4](docs/INSTALL.md#4-claude-desktop-the-chat-tab).
- **Backups:** `scripts\daily_backup.ps1` works in both Windows PowerShell
  5.1 and PowerShell 7; schedule it with `schtasks` as shown in
  [docs/INSTALL.md §8](docs/INSTALL.md#8-windows).
- **Updating a plugin install** (not a git clone): `.\scripts\update.ps1`.

### Troubleshooting

| You see | Do this |
|---|---|
| `Docker is installed but not running` | Open Docker Desktop, wait until it's running, retry |
| `Docker is not installed` | Install Docker Desktop (step 1) |
| `chronicle` is not recognized | `uv tool update-shell`, then open a new terminal |
| Dashboard page says "not built" | `cd dashboard; npm ci; npm run build`, then restart `chronicle start` |
| `chronicle update` says dependencies failed | `chronicle stop`, close Claude Code/Cursor sessions, run it again |
| `chronicle update` says you have uncommitted changes | Commit or stash your changes in the chronicle folder first |
| Claude Desktop shows `spawn uv ENOENT` | Use the absolute path to `uv.exe` or `chronicle.exe` in `command` |

More detail, including WSL2, is in [docs/INSTALL.md §8](docs/INSTALL.md#8-windows).

## macOS and Linux

Same `chronicle` command as Windows; use it from zsh (the macOS default),
bash, or fish.

### One-time setup

1. **Install the prerequisites.** On macOS with [Homebrew](https://brew.sh):
   ```bash
   brew install uv git node          # node: only for the dashboard
   brew install --cask docker        # or: brew install orbstack
   ```
   Then open Docker Desktop (or OrbStack) once and let it finish starting.
2. **Clone Chronicle and put the `chronicle` command on your PATH:**
   ```bash
   git clone https://github.com/pacheco20222/chronicle.git
   cd chronicle
   uv tool install --editable .
   ```
   This installs `chronicle` into `~/.local/bin`. If a new terminal says
   `command not found: chronicle`, run `uv tool update-shell` once and open
   a new terminal (it edits `~/.zshrc` or `~/.bashrc` for you).
3. **Build the dashboard** (optional, needs Node.js):
   ```bash
   (cd dashboard && npm ci && npm run build)
   ```
4. **Start everything and check it's healthy:**
   ```bash
   chronicle start
   ```
5. **Connect a project:** `chronicle setup claude-desktop --project my-project` writes the Claude Desktop config for you (also `claude-code`, `cursor`, `codex`, run from the repo folder; add `--print` to preview). Or use the Claude Code plugin
   ([Quick start](#quick-start-claude-code-plugin)), or
   `chronicle setup --project my-project` and paste what it prints. Details for
   the Desktop app:
   [docs/INSTALL.md §4](docs/INSTALL.md#4-claude-desktop-the-chat-tab).

Everyday commands are the same as in the [Windows table](#everyday-commands).
In config files (`.mcp.json`, `claude_desktop_config.json`) you can use
`chronicle` in place of `uv --directory … run chronicle`; the app does not
see your shell `PATH`, so give the absolute path from `which chronicle`
(for example `/Users/you/.local/bin/chronicle`) as `command`, with no `args`.

| You see | Do this |
|---|---|
| `command not found: chronicle` | `uv tool update-shell`, then open a new terminal |
| `Docker is installed but not running` | Open Docker Desktop or OrbStack, wait, retry |
| Dashboard page says "not built" | `(cd dashboard && npm ci && npm run build)`, restart `chronicle start` |
| Claude Desktop shows `spawn chronicle ENOENT` | `command` must be the absolute path from `which chronicle` |

## How it works

SQLite (SQLAlchemy 2 + Alembic migrations) is the canonical store for
every memory, source, and scope — one file at `~/.chronicle/chronicle.db`,
shared by every registered project. Qdrant is reduced to a derived
semantic-similarity index (deleting and rebuilding it loses nothing
durable); lexical search is real SQLite FTS5; fastembed
(`nomic-embed-text-v1.5`, local CPU embeddings, no separate service) does
the embedding; FastMCP is the MCP server itself, stdio transport. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design, the
scope hierarchy, and every tool's exact signature.

## Upgrading

**3.0.0** rearchitected storage: SQLite became canonical, Qdrant was
reduced to a derived vector index. If you're upgrading from an install
older than 3.0.0, back up `~/.chronicle` first — see
[docs/ARCHITECTURE.md § Backups](docs/ARCHITECTURE.md#backups) for what
today's backup scripts do and do not cover (notably: they snapshot
Qdrant and export a JSON dump, but do not yet back up
`~/.chronicle/chronicle.db` itself — copy that file directly too).

**2.0.0** changed the embedding backend (Ollama → fastembed) — see
[CHANGELOG.md](CHANGELOG.md). Old and new embeddings share the same 768
dimensions but are **not** the same vector space, and Qdrant can't detect
the difference. If you're upgrading from before 2.0.0, either start a
fresh `memories` collection, or expect old memories to rank essentially
randomly against new ones in semantic search until you re-add them.

## How this compares to Graphiti/Zep

[Graphiti](https://github.com/getzep/graphiti) (the open-source engine
behind [Zep](https://www.getzep.com)) is a genuinely different kind of
tool, not just a competing UI on the same idea, so "which is better" is
the wrong question — they solve different problems:

| | Chronicle | Graphiti |
|---|---|---|
| What gets remembered | Explicit — an agent/user decides to call `memory_add` | Automatic — an LLM extracts entities and facts from whatever data you feed it |
| Storage | One SQLite file + local Qdrant, zero external deps beyond Docker | Requires a graph database (Neo4j, etc.) or Zep's hosted engine |
| Isolation model | Per-repo/project scope tree — built for one developer, many codebases | Per-entity/user context graphs — built for one product, many end-users |
| Change tracking | Whole-memory supersede/status (active/resolved/superseded/expired/wrong) | Sub-fact-level bi-temporal validity windows ("true from March to June") |
| Setup cost | `docker compose up`, `uv run`, done | Graph DB provisioning, optional ontology design, an extraction pipeline |
| Extraction cost | None — nothing runs unless you explicitly save something | An LLM call to extract structure from every ingested episode |

Graphiti genuinely wins on fact-level temporal precision, not having to
remember to save anything yourself, and production scale (built for
"millions of context graphs"). Chronicle's actual pitch: it costs
nothing to run beyond what a solo developer already has installed, and
it never does anything you didn't explicitly ask it to.

## Known gap: local clients only, not cloud chat

Chronicle's MCP server runs as a local process a client spawns and
talks to over stdio — that's what Claude Code, Cursor, Codex, and the
**Claude Desktop app** all do (see
[docs/INSTALL.md §4](docs/INSTALL.md#4-claude-desktop-the-chat-tab) for the desktop
app specifically). **claude.ai and ChatGPT's web/app chat interfaces
are cloud-hosted and can't spawn a local process** — they'd need a
remote, authenticated HTTP MCP endpoint instead. Chronicle's dashboard
already serves the same tools over streamable HTTP at `/mcp`
(`chronicle dashboard start`, see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)), but that endpoint binds
to `127.0.0.1` only and has no authentication — appropriate for a
trusted local dev tool, not for exposing to the public internet as-is.
Bridging this (a tunnel plus real auth, at minimum) is a real, unbuilt
feature, not a documentation gap.

## License

MIT — see [LICENSE](LICENSE).
