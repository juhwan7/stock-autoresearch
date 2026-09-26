from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = ROOT / 'data/news/issue-digest.json'
ARCHIVE = ROOT / 'data/news/archive'

def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}

def main() -> int:
    result_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = read_json(result_path) if result_path else {}
    digest = read_json(DIGEST)
    processed_at = str(result.get('processed_at') or digest.get('updated_at') or '')
    try:
        dt = datetime.fromisoformat(processed_at.replace('Z', '+00:00'))
    except ValueError:
        dt = datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    day = dt.strftime('%Y-%m-%d')
    path = ARCHIVE / f'{day}.jsonl'
    compact = []
    for item in digest.get('issues') or []:
        if not isinstance(item, dict):
            continue
        compact.append({
            'issue_id': item.get('issue_id'),
            'status': item.get('status'),
            'severity': item.get('severity'),
            'event_time': item.get('event_time'),
            'last_updated': item.get('last_updated'),
            'status_changed_at': item.get('status_changed_at'),
            'article_count': item.get('article_count'),
            'article_velocity': item.get('article_velocity'),
            'publisher_count': item.get('publisher_count'),
            'latest_update': item.get('latest_update'),
        })
    row = {
        'processed_at': processed_at,
        'batch_id': result.get('batch_id'),
        'supervisor': result.get('supervisor'),
        'issue_count': len(compact),
        'issues': compact,
    }
    with path.open('a', encoding='utf-8') as fp:
        fp.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')

    index_path = ARCHIVE / 'index.json'
    index = read_json(index_path)
    days = [x for x in (index.get('days') or []) if isinstance(x, dict) and x.get('date') != day]
    days.insert(0, {'date': day, 'file': str(path.relative_to(ROOT)), 'last_processed_at': processed_at})
    index_path.write_text(json.dumps({'updated_at': processed_at, 'days': days[:60]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'archive': str(path.relative_to(ROOT)), 'issue_count': len(compact)}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
