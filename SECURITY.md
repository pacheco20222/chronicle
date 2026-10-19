# Security

## Reporting a vulnerability

Please report security problems privately through GitHub's
[private vulnerability reporting](https://github.com/pacheco20222/chronicle/security/advisories/new)
instead of opening a public issue. Include what you did, what you expected,
and what happened. I aim to reply within a few days.

## Threat model and what Chronicle does

Chronicle is a local tool for a single user's own machine.

- **Data stays local.** Memories live in `~/.chronicle/chronicle.db` (SQLite)
  and a Qdrant container you run yourself. Chronicle makes no cloud or LLM
  calls and sends no telemetry. Its only outbound traffic is the one-time
  embedding-model download (Hugging Face), Docker image pulls, and
  `chronicle update` (git). Your AI agent, however, sends whatever it reads,
  including recalled memories, to its own model provider. Don't store secrets
  in memories.
- **Network exposure.** Qdrant is published on `127.0.0.1:6333` only, and the
  dashboard binds `127.0.0.1:8765`. Neither has authentication, so don't
  expose them to a network. If you started Chronicle before this was
  tightened, run `docker compose up -d` again from the clone to recreate the
  container with the loopback-only port.
- **Recalled memory is untrusted data.** The session-start hook fences saved
  text and labels it as data, not instructions, but a memory is only as
  trustworthy as whatever wrote it. Review what you save and what you import.
- **Project scoping is a convention enforced by the application**, not an
  authorization boundary: tools accept an explicit `scope_path`, and
  `memory_search_global` exists on purpose.
- **Config writing.** `chronicle setup <agent>` edits agent config files
  (merge, `.bak` backup, atomic write, refuses invalid JSON, refuses repo
  config paths that resolve outside the current folder). Use `--print` to
  preview. On Windows the session-start hook is a base64-encoded PowerShell
  command that only runs `chronicle-recall` with `CHRONICLE_PROJECT` set;
  decode it to check.

## Dependencies

Dependencies are locked in `uv.lock` and CI runs `pip-audit` against it.
