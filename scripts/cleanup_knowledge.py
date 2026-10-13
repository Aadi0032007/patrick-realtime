"""Remove only old snapshots whose complete text is preserved in combined.json."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from patrick.knowledge_files import canonical, strip_robot_header


def cleanup(dry_run=False):
    root = (PROJECT / 'knowledge').resolve()
    index = root / 'combined.json'
    data = json.loads(index.read_text(encoding='utf-8'))
    records = {r.get('id'): r for r in data['records']}
    candidates = []
    for filename, prefix in [('revobots.json', 'robot-page-'), ('revobots-full-pdf.json', 'full-pdf-page-')]:
        path = root / filename
        if not path.exists():
            continue
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError(f'Unexpected snapshot path: {path}')
        old = json.loads(path.read_text(encoding='utf-8'))
        pages = old.get('pages', [])
        if not pages or not all(canonical(strip_robot_header(p['text'])) ==
                                canonical(records.get(prefix + str(p['page']), {}).get('text', '')) for p in pages):
            print(f'Kept {filename}: contains text not fully preserved in combined.json.')
            continue
        candidates.append(path)
        data.setdefault('source_metadata', {})[old['source']] = {k: v for k, v in old.items() if k != 'pages'}
    if not candidates:
        print('No redundant snapshot files to remove.')
        return
    if dry_run:
        print('Verified redundant files: ' + ', '.join(p.name for p in candidates))
        return
    folder = PROJECT / 'build' / 'rag-backups'
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.zip')
    with ZipFile(backup, 'w', ZIP_DEFLATED) as archive:
        for path in [index, *candidates]:
            archive.write(path, path.name)
    index.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for path in candidates:
        path.unlink()
    print(f'Removed {len(candidates)} fully duplicated snapshots. Backup: {backup}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    cleanup(parser.parse_args().dry_run)
