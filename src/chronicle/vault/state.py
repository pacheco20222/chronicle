"""Process-independent mirror diagnostics; independent of the canonical DB."""
import json
import os
from pathlib import Path
import sys
import tempfile


def status_path() -> Path:
    return Path(os.environ.get('CHRONICLE_STATE_DIR', Path.home() / '.chronicle')) / 'vault-status.json'


def read_status() -> dict:
    try:
        data = json.loads(status_path().read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {'last_sync': {}, 'last_error': None, 'skipped_user_files': []}


def write_status(data: dict) -> None:
    path = status_path()
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=True)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def record_status(projects=(), skipped=(), error: Exception | None = None) -> None:
    from datetime import datetime, timezone

    if error is not None:
        print(f'Chronicle vault mirror failed: {error}', file=sys.stderr)
    try:
        data = read_status()
        data['last_error'] = str(error) if error is not None else None
        data['skipped_user_files'] = sorted(set(skipped))
        for project in projects:
            data.setdefault('last_sync', {})[project] = datetime.now(timezone.utc).isoformat()
        write_status(data)
    except Exception as failure:
        print(f'Chronicle vault status failed: {failure}', file=sys.stderr)
