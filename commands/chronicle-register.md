---
description: Register this repo with chronicle (starts Qdrant if needed, no files written into this repo)
argument-hint: [project-name]
allowed-tools: Bash, Read, mcp__chronicle__memory_set_document
---

Register this repo with chronicle, as project "$1".

If `$1` is empty, ask the user for the project name before doing anything else — don't guess one.

1. Check whether Qdrant is already reachable (`curl -s http://localhost:6333/collections`). If not, run `docker compose -f ${CLAUDE_PLUGIN_ROOT}/docker-compose.yml up -d` to start it (the plugin's own bundled compose file — safe and idempotent even if some other Qdrant is already up on port 6333, in which case explain the outcome to the user rather than guessing).
2. Run `uv run --project ${CLAUDE_PLUGIN_ROOT} chronicle register --project $1` from the current directory. This writes nothing into this repo — it records this folder's absolute path against the project name in a registry outside any repo (`~/.chronicle/projects.json`).
3. Tell the user `memory_add`/`memory_search`/etc. work immediately, in this same session — no restart needed, since the project resolves fresh on every call. The first `memory_add` downloads the embedding model automatically (~500MB, one-time) — mention this so it isn't a silent surprise. The checkpoint/project-overview auto-load hook takes effect starting the *next* session (inherent to what a `SessionStart` hook is).
4. Ask the user: "Want to add a core memory now — a project overview that auto-loads at the start of every future session?" Don't do this silently; wait for a yes.
   - If they say yes: look for `CLAUDE.md`, `AGENTS.md`, `PROJECT.md`, then `README.md`, in that order, in the current directory. If one exists, offer to condense it into the overview rather than pasting it verbatim — memories should stay concise, not a full file dump. If none exist, ask the user for a short paragraph describing the project instead.
   - Either way, save the result with `memory_set_document(slug="$1", content=<condensed text>, type="overview")` — the slug matches the project name by convention, so it auto-loads at the start of every session in this repo from here on.
   - If they say no, or don't want to do it right now, don't push — this is optional, and `memory_set_document` works the same way any time later.
   - That's it — don't mention Codex, or any other tool, unless the user asks.
