# Installing Mnemo

## Prerequisites

1. **Docker or OrbStack** running locally.
2. **uv** installed ([docs.astral.sh/uv](https://docs.astral.sh/uv/)).

No GPU and no separate embedding service needed — `fastembed` runs
locally on CPU and installs the same way `uv sync` installs every
other Python dependency here. The model itself (~500MB) downloads
automatically, once, the first time you save a memory.

## Option A: Plugin install (recommended for Claude Code)

Inside Claude Code, in whichever repo you want Mnemo available in:

```
/plugin marketplace add pacheco20222/mnemo
/plugin install mnemo --scope project
/mnemo:mnemo-register my-project-name
```

`--scope project` installs the plugin for this repo only — it will not
appear in any other project. This is the recommended default: each
repo you do this in gets its own isolated memory, and nothing connects
across repos unless you deliberately make it. `/mnemo:mnemo-register`
starts Qdrant (via the plugin's own bundled `docker-compose.yml`) if
it isn't already running, then registers this folder under that
project name in `~/.mnemo/projects.json` — a file outside any repo,
not `.mcp.json`. Nothing gets written into this repo at all. The first
`memory_add` you make afterward downloads the embedding model
automatically (~500MB, one-time). `memory_add`/`memory_search` work
immediately, same session, no restart.

Right after registering, it asks whether you want to add a core
memory — a project overview seeded from `CLAUDE.md`, `AGENTS.md`,
`PROJECT.md`, or `README.md` if one of those exists (condensed, not
pasted in full), or a short paragraph you provide if none do. It's
optional, only happens on a yes, and can be added or replaced later
with `memory_set_document` regardless.

Repeat both commands (with that repo's own project name) in any other
repo you want Mnemo in — no cloning or hand-edited config, ever, and by
default each repo's memory stays separate from every other repo's.

Already registered this folder some other way — via Codex, or `mnemo
register` run from a terminal? Skip `/mnemo:mnemo-register` and just
install the plugin:

```
/plugin marketplace add pacheco20222/mnemo
/plugin install mnemo --scope project
```

The plugin resolves the project the same way Codex does — an explicit
env var if one's set, otherwise a lookup of this folder in the shared
registry (`~/.mnemo/projects.json`) — so an existing registration is
picked up automatically. Nothing about registration is tool-specific;
it only ever needs doing once, by whichever tool you happen to be
using first.

If you'd rather have Mnemo available in *every* project without
installing it repo by repo, use `--scope user` instead (Claude Code's
default if `--scope` is omitted) — the plugin and its MCP server are
then present everywhere, but each repo still needs its own
`/mnemo:mnemo-register` before memory tools work there, so nothing is
silently connected just because the plugin is present. The only way
two repos end up sharing memories is registering both of them under
the *same* project name — a deliberate choice, never a default.

If `/plugin install mnemo --scope project` reports "already installed"
instead of enabling it, mnemo is already installed elsewhere on this
machine (e.g. at `user` scope from an earlier setup) — Claude Code
installs a plugin's code once, machine-wide. Use
`/plugin enable mnemo --scope project` instead, which toggles a scope
on for an already-installed plugin.

This covers the Claude Code side only; Codex still needs the one-time
server setup in [§5](#5-codex) below, since Codex has no
plugin/marketplace system of its own. Codex still needs each folder
registered too, same as Claude Code — but it reads the same shared
registry, so if you already registered a folder via
`/mnemo:mnemo-register`, Codex picks it up with no separate step.

The rest of this doc (Option B) is the manual path — read it if you're
not using Claude Code, want to see exactly what the plugin command
does under the hood, or ran into something `/mnemo:mnemo-register` didn't
handle.

## Option B: Manual install

### 1. Clone and start the services

```bash
git clone git@github.com:pacheco20222/mnemo.git
cd mnemo
docker compose up -d
```

This starts one Qdrant container — the only always-on process Mnemo
needs. Verify it's up:

```bash
curl -s http://localhost:6333/collections
```

### 2. Get your install path

```bash
uv run mnemo setup
```

This prints a ready-to-paste `.mcp.json` block, an optional
`.claude/settings.json` hook block, and the equivalent `codex mcp add`
command, with your actual clone path already filled in — you don't
need to hand-edit any paths yourself. Re-run it with `--project NAME`
to have the project id filled in too, instead of a placeholder.

### 3. Claude Code

Claude Code scopes MCP servers **per repository**, automatically —
whichever repo's `.mcp.json` is present is what's active for that
session, with zero manual switching.

Copy the block `mnemo setup` printed into a `.mcp.json` file at the
root of whichever repo you want Mnemo available in:

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/mnemo", "run", "mnemo"],
      "env": {
        "MNEMO_PROJECT": "your-project-name"
      }
    }
  }
}
```

`MNEMO_PROJECT` should be different per repo — it's what keeps one
project's memories from ever showing up in another's. Open (or
restart) a Claude Code session in that repo and `memory_add`/
`memory_search` will be available.

#### Optional: auto-loading checkpoints and documents

Mnemo can automatically surface your latest checkpoint and project
overview at the start of every session, via a Claude Code hook. Add a
`.claude/settings.json` in the same repo:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          {
            "type": "command",
            "command": "MNEMO_PROJECT=your-project-name uv run --directory /absolute/path/to/mnemo mnemo-recall"
          }
        ]
      }
    ]
  }
}
```

If a `.claude/settings.json` already exists in that repo, add the
`"hooks"` key alongside whatever's already there rather than replacing
the file.

### 4. Cursor

Cursor's MCP config is the same `mcpServers` JSON shape as Claude
Code's, just a different file: `.cursor/mcp.json` at the root of
whichever repo you want Mnemo in, instead of `.mcp.json`. Cursor scopes
it per-repo automatically the same way Claude Code does — a project's
`.cursor/mcp.json` only applies inside that project.

Copy the exact same block `mnemo setup` printed for Claude Code into
`.cursor/mcp.json` instead:

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/mnemo", "run", "mnemo"],
      "env": {
        "MNEMO_PROJECT": "your-project-name"
      }
    }
  }
}
```

Same rule as Claude Code: give each repo its own `MNEMO_PROJECT` value.
Restart Cursor (or reload the window) after adding or editing this
file for it to pick up the server.

Cursor has no plugin/marketplace system and no `SessionStart`-hook
equivalent, so there's no bundled-plugin install path and no automatic
checkpoint/document auto-load the way Claude Code's optional hook
gives you — `memory_add`/`memory_search`/`memory_get_document` work
once the server's connected, but recall at the start of a session is
manual: ask the agent to call `memory_get_document` for the project
overview, and `memory_get_latest(type="checkpoint")` — **not**
`memory_search`, which ranks by semantic similarity to whatever query
text gets used and can surface an older but more textually-relevant
checkpoint instead of the actual newest one. Wire up your own
equivalent of Cursor's session-start behavior, if it has one in your
version, to make this automatic instead of asked-for.

### 5. Codex

Codex's MCP configuration is global (`~/.codex/config.toml`), not a
per-repo file like Claude Code's `.mcp.json` — but Codex *does* launch
the `mnemo` server with your actual current directory as its working
directory, and the server resolves the project the same way it does
for Claude Code's plugin: `MNEMO_PROJECT` if set, otherwise a lookup
of the current directory in the shared registry
(`~/.mnemo/projects.json`). So as long as you don't hardcode
`MNEMO_PROJECT`, Codex automatically picks up whichever project a
folder is registered as — using Claude Code's own registration
mechanism (`mnemo register` / `/mnemo:mnemo-register`), not a
Codex-specific one.

This is two separate steps, not one command per project — easy to
miss since the whole point is that step 1 never mentions a project at
all.

**Step 1 — once, ever, on this machine.** Run the command `mnemo setup`
printed:

```bash
codex mcp add mnemo -- uv run --project /absolute/path/to/mnemo mnemo
```

Use `--project`, not `--directory` — `--directory` changes Codex's
own working directory before running `mnemo`, which breaks the
cwd-based lookup step 2 depends on. `--project` only tells `uv` where
to find mnemo's own code to run, without touching the working
directory. Never repeat this step for a new project; one server entry
serves all of them.

**Step 2 — once per folder you want memory in.** Register it, from
inside that folder:

```bash
cd /path/to/your-project
uv run --project /absolute/path/to/mnemo mnemo register --project your-project-name
```

(Already registered that folder via Claude Code's `/mnemo:mnemo-register`
instead? Same registry, so this step is already done — skip it.)

After that, any Codex session started in that folder resolves to
`your-project-name` automatically, with no further Codex-specific
step. Register a different folder for a different project the same
way, and Codex follows along. Git worktrees of a registered repo
resolve to that repo's project automatically — no separate
registration per worktree.

If you genuinely need two Codex sessions open in two different
projects to resolve differently *at the exact same time*, that still
works automatically too, since resolution happens per-invocation from
each session's own working directory — there's no shared state between
them beyond the registry file both read from.

### 6. Running `mnemo`'s other commands (import, graph)

`mnemo import` and `mnemo graph` aren't called by Claude Code or
Codex — you run these yourself, directly. Like every `uv run mnemo`
invocation, `uv` needs to find mnemo's own code, either by cwd or by
`--directory`:

```bash
cd /path/to/mnemo   # wherever you cloned it
uv run mnemo graph --project your-project-name
uv run mnemo import notes.md --project your-project-name --type note
```

or from anywhere else:

```bash
uv run --directory /path/to/mnemo mnemo graph --project your-project-name
```

Real gotcha with `--directory`: it changes the command's working
directory to wherever you cloned mnemo, not wherever you actually are
— so a relative file path passed to `mnemo import` (e.g. `notes.md`)
resolves against **mnemo's** folder, not yours, unless you `cd` into
mnemo first (first example above) or pass an absolute path to the
file instead.

`mnemo graph` defaults to the same project `memory_add`/`memory_search`
would resolve to from your current directory (env var, then the
registry) — same isolation as everything else. Pass `--project X` to
graph a specific project regardless of where you're standing, or
`--all` to deliberately graph every project's memories together (real
cross-project similarities can be genuinely useful to see, just ask
for it explicitly). It needs at least 2 memories in scope to draw
anything, writes a self-contained HTML file (`--out path.html` to
control where — defaults to your current directory), and opens it in
your default browser automatically.

### 7. Windows

Two real options, same as always — pick one, don't mix them for the
same install:

**WSL2** — this is just Linux underneath. Everything above (Option A
or B, Claude Code or Codex) works completely unmodified inside a WSL2
distro. If you're already comfortable with WSL2, this is the easy path
and there's nothing else in this section for you.

**Native Windows (PowerShell/cmd, no WSL)** — Docker Desktop, `uv`,
and `docker compose` all work natively; nothing above needs to change
except two things:

- Paths in `.mcp.json`, `~/.codex/config.toml`, or the `codex mcp add`
  command need either forward slashes or doubled backslashes — both
  `C:/Users/you/mnemo` and `C:\\Users\\you\\mnemo` are valid; a single
  backslash isn't, in JSON or TOML.
- The backup scripts are PowerShell twins (`backup.ps1`,
  `export_json.ps1`, `daily_backup.ps1` in `scripts/`) — same
  behavior as the `.sh` versions, same env vars
  (`MNEMO_QDRANT_URL`, `MNEMO_COLLECTION`). Run them directly:
  ```powershell
  .\scripts\daily_backup.ps1
  ```
  For the daily schedule (replaces `launchd` on macOS), one command —
  no separate task-definition file needed:
  ```
  schtasks /create /tn "MnemoDailyBackup" /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"C:\path\to\mnemo\scripts\daily_backup.ps1\"" /sc daily /st 03:00
  ```
  `-ExecutionPolicy Bypass` is scoped to just this scheduled task —
  it doesn't change your system-wide PowerShell execution policy.

`mnemo import` and `mnemo graph` (§5 above) need nothing extra on
Windows — both are plain, cross-platform Python: `mnemo graph`'s
browser-opening and `mnemo import`'s file reading have no OS-specific
code path to work around. The same `cd` / `--directory` rule from §5
applies exactly as written.

#### MCP connects, but the first memory tool fails

Mnemo now waits until the first `memory_add` or `memory_search` call to
load FastEmbed and, on a new install, download the embedding model. This
keeps model setup out of the MCP initialization handshake. If that first
tool call fails or times out, while the MCP itself still shows as
connected, look for a FastEmbed, Hugging Face, ONNX, download, or model
cache error in the tool result. Check your network connection, available
disk space, and write access to `%USERPROFILE%\.mnemo\models`.

You can retry the model load directly in PowerShell and see the complete
error outside the MCP client:

```powershell
uv run --directory 'C:/path/to/mnemo' python -c "from mnemo.embeddings import embed_text; print(len(embed_text('warmup')))"
```

A successful run prints `768`. If the first MCP call merely timed out
while the download continued, let the download finish and retry the same
memory tool. If the command above reports an error, fix that error and
run it again; a failed initialization leaves the model uninitialized, so
the next call retries it.

### 8. Verify it worked

This is just seeding one test memory so there's something to recall —
on a fresh install the collection is empty, so say anything you like.
In a Claude Code or Codex session in your configured repo:

> "Remember that we're using Mnemo to give you persistent memory."

Then in a later session:

> "What do you know about this project?"

If it recalls the note, it's working.
