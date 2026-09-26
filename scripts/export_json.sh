#!/usr/bin/env bash
set -euo pipefail

QDRANT_URL="${CHRONICLE_QDRANT_URL:-http://localhost:6333}"
COLLECTION="${CHRONICLE_COLLECTION:-memories}"
BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backups"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"

if ! curl -sf -o /dev/null "$QDRANT_URL/collections/$COLLECTION"; then
    echo "Collection '$COLLECTION' doesn't exist yet — nothing to export."
    exit 0
fi

DEST="$BACKUP_DIR/${COLLECTION}-${TIMESTAMP}.json"

echo "Exporting collection '$COLLECTION' to JSON..."
python3 -c "
import json
import urllib.request

qdrant_url = '$QDRANT_URL'
collection = '$COLLECTION'

points = []
offset = None
while True:
    body = {'limit': 200, 'with_payload': True, 'with_vector': False}
    if offset is not None:
        body['offset'] = offset
    req = urllib.request.Request(
        f'{qdrant_url}/collections/{collection}/points/scroll',
        data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)['result']
    for p in result['points']:
        points.append({'id': p['id'], **p['payload']})
    offset = result.get('next_page_offset')
    if offset is None:
        break

with open('$DEST', 'w') as f:
    json.dump(points, f, indent=2)

print(f'Exported {len(points)} memories to $DEST')
"

echo "Pruning old exports (keeping newest 14)..."
ls -1t "$BACKUP_DIR"/"${COLLECTION}"-*.json 2>/dev/null | tail -n +15 | xargs -I {} rm -- {}
