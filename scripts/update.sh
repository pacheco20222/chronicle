#!/usr/bin/env bash
set -euo pipefail

echo "Refreshing the chronicle marketplace..."
claude plugin marketplace update chronicle

echo "Updating the chronicle plugin..."
claude plugin update chronicle

echo
echo "Done. The plugin is shared across every project that has it enabled"
echo "(one cache at ~/.claude/plugins/cache/chronicle) — restart any open"
echo "Claude Code or Codex session to pick up the new version."
