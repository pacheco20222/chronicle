# Windows support — design

## Problem

README/docs required "macOS or Linux." Nothing about the actual stack
(Qdrant via Docker, `uv`, fastembed/onnxruntime, FastMCP) is
Windows-incompatible — the only real gaps were the bash-only backup
scripts (`scripts/*.sh`) and the `launchd` plist, both POSIX-specific.

## Scope

Both native Windows (PowerShell/cmd, no WSL) and WSL2. WSL2 needs no
code changes — it's Linux underneath, everything already works there
unmodified, so it only needed a doc mention. Native Windows needed
real work: PowerShell equivalents of the backup scripts, and a
Task Scheduler equivalent of the `launchd` job.

## Approach

Standalone native PowerShell twins, one per existing bash script,
same directory, same naming pattern (`backup.ps1`, `export_json.ps1`,
`daily_backup.ps1` next to `backup.sh`, `export_json.sh`,
`daily_backup.sh`). No shared code with the bash versions — the logic
is small enough that duplication is cheaper than the indirection of a
shared Python core, and it means zero changes to the already-working,
already-shipped bash scripts.

Rejected alternative: move the backup/export logic into the `chronicle`
CLI itself (`chronicle backup`, `chronicle export`) as new Python subcommands,
cross-platform for free, eventually deleting both shell-script
flavors. More maintainable long-term, but a bigger change than "add
Windows support" — refactors an already-shipped piece for every
platform, not just Windows. Not done now; worth reconsidering if the
dual-script maintenance ever becomes a real burden.

For the scheduled daily run, no task-definition file is checked into
the repo (unlike `launchd`, Task Scheduler doesn't need one) — a
single `schtasks /create` command in the docs does it, with
`-ExecutionPolicy Bypass` scoped to just that task so nobody has to
weaken their system-wide PowerShell execution policy.

## Files

- `scripts/backup.ps1` — `Invoke-RestMethod`/`Invoke-WebRequest`
  equivalent of `backup.sh`: snapshot the collection, download it,
  delete the remote copy, prune to newest 14. Same env var overrides
  (`CHRONICLE_QDRANT_URL`, `CHRONICLE_COLLECTION`).
- `scripts/export_json.ps1` — equivalent of `export_json.sh`:
  paginated scroll, `ConvertTo-Json -AsArray` (needed explicitly —
  PowerShell's default `ConvertTo-Json` unwraps a single-element
  array into a bare object, which would silently break the "always a
  JSON array" contract the Python version guarantees), prune to
  newest 14.
- `scripts/daily_backup.ps1` — trivial wrapper, calls the two above
  via `$PSScriptRoot`.
- `$ErrorActionPreference = "Stop"` at the top of each, mirroring
  bash's `set -euo pipefail`.

## Testing

No Windows machine available to test on directly. Verified as far as
possible from macOS: installed a portable PowerShell 7.4.6 build (no
sudo/installer needed), ran all three scripts against a real, live,
throwaway Qdrant instance (not the shared dev instance) —
snapshot/download/prune cycle, JSON export with real payload data,
the empty-collection early-exit path, the single-element JSON array
edge case, and pruning behavior with more than 14 files present. All
passed against real HTTP calls and real files, not just parsed for
syntax.

What's *not* verified: actual behavior on Windows/PowerShell for
Windows specifically (path separator handling, execution policy
prompts, line-ending issues, `schtasks` itself). The Qdrant HTTP API
surface these scripts talk to is identical regardless of OS, so the
logic itself is exercised for real — only the Windows-specific
runtime environment is unverified. A real Windows user is expected to
run these and report back what breaks.

## Docs

- README's Requirements line: added Windows (PowerShell 5.1+/pwsh, or
  WSL2).
- `docs/INSTALL.md`: new §5 "Windows" between the Codex section and
  "Verify it worked" (renumbered to §6) — WSL2 pointer, native-Windows
  path-escaping note, the `.ps1` scripts, and the `schtasks` command.
