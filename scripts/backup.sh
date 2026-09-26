#!/usr/bin/env bash
set -euo pipefail

QDRANT_URL="${CHRONICLE_QDRANT_URL:-http://localhost:6333}"
COLLECTION="${CHRONICLE_COLLECTION:-memories}"
BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backups"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"

if ! curl -sf -o /dev/null "$QDRANT_URL/collections/$COLLECTION"; then
    echo "Collection '$COLLECTION' doesn't exist yet — nothing to back up."
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

echo "Backup saved: $DEST ($(du -h "$DEST" | cut -f1))"

echo "Pruning old backups (keeping newest 14)..."
ls -1t "$BACKUP_DIR"/"${COLLECTION}"-*.snapshot 2>/dev/null | tail -n +15 | xargs -I {} rm -- {}
