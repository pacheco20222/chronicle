$ErrorActionPreference = "Stop"

Write-Host "Refreshing the chronicle marketplace..."
claude plugin marketplace update chronicle
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Updating the chronicle plugin..."
claude plugin update chronicle
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. The plugin is shared across every project that has it enabled"
Write-Host "(one cache at ~/.claude/plugins/cache/chronicle) - restart any open"
Write-Host "Claude Code or Codex session to pick up the new version."
