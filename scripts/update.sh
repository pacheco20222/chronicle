#!/usr/bin/env bash
set -euo pipefail

echo "Refreshing the mnemo marketplace..."
claude plugin marketplace update mnemo

echo "Updating the mnemo plugin..."
claude plugin update mnemo

echo
echo "Done. The plugin is shared across every project that has it enabled"
echo "(one cache at ~/.claude/plugins/cache/mnemo) — restart any open"
echo "Claude Code or Codex session to pick up the new version."
