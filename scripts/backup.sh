#!/usr/bin/env bash
set -euo pipefail

QDRANT_URL="${CHRONICLE_QDRANT_URL:-http://localhost:6333}"
COLLECTION="${CHRONICLE_COLLECTION:-memories}"
SQLITE_PATH="${CHRONICLE_SQLITE_PATH:-$HOME/.chronicle/chronicle.db}"
BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backups"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"

# SQLite is the canonical store (since the 3.0.0 rearchitecture) — every
# memory, source, and scope lives here first. The Qdrant snapshot below is
# a derived vector index only; back this up first since it's the one that
# actually matters if something is lost.
if [ -f "$SQLITE_PATH" ]; then
    echo "Backing up SQLite database ($SQLITE_PATH)..."
    DB_DEST="$BACKUP_DIR/chronicle-${TIMESTAMP}.db"
    if command -v sqlite3 >/dev/null 2>&1; then
        # .backup is safe against a concurrent writer (uses SQLite's own
        # online backup API); a plain cp could grab a half-written page.
        sqlite3 "$SQLITE_PATH" ".backup '$DB_DEST'"
    else
        cp "$SQLITE_PATH" "$DB_DEST"
    fi
    echo "Database backup saved: $DB_DEST ($(du -h "$DB_DEST" | cut -f1))"
    echo "Pruning old database backups (keeping newest 14)..."
    ls -1t "$BACKUP_DIR"/chronicle-*.db 2>/dev/null | tail -n +15 | xargs -I {} rm -- {}
else
    echo "No SQLite database found at $SQLITE_PATH — nothing to back up there yet."
fi

if ! curl -sf -o /dev/null "$QDRANT_URL/collections/$COLLECTION"; then
    echo "Collection '$COLLECTION' doesn't exist yet — nothing to snapshot."
    exit 0
fi

echo "Creating snapshot of collection '$COLLECTION'..."
SNAPSHOT_NAME=$(curl -sf -X POST "$QDRANT_URL/collections/$COLLECTION/snapshots" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['name'])")

echo "Downloading snapshot: $SNAPSHOT_NAME"
DEST="$BACKUP_DIR/${COLLECTION}-${TIMESTAMP}.snapshot"
curl -sf -o "$DEST" "$QDRANT_URL/collections/$COLLECTION/snapshots/$SNAPSHOT_NAME"

echo "Removing snapshot copy from Qdrant (kept locally at $DEST)..."
curl -sf -X DELETE "$QDRANT_URL/collections/$COLLECTION/snapshots/$SNAPSHOT_NAME" > /dev/null

echo "Vector index snapshot saved: $DEST ($(du -h "$DEST" | cut -f1))"

echo "Pruning old vector snapshots (keeping newest 14)..."
ls -1t "$BACKUP_DIR"/"${COLLECTION}"-*.snapshot 2>/dev/null | tail -n +15 | xargs -I {} rm -- {}
