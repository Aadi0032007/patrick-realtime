"""Read reference files without treating their contents as executable instructions."""
import json
from pathlib import Path
import re

SUPPORTED = {'.json', '.jsonl', '.md', '.markdown', '.txt', '.text', '.csv', '.rst', '.pdf'}


def canonical(text):
    return ' '.join(text.split()).casefold()


def strip_robot_header(text):
    lines = text.split('\n', 2)
    if len(lines) == 3 and 'ROBOT KNOWLEDGE BASE' in lines[0] and 'RAG-ready technical reference' in lines[1]:
        return lines[2]
    return text


def json_records(data, source):
    if isinstance(data, dict) and ('records' in data or 'pages' in data):
        rows = data['records'] if 'records' in data else data['pages']
        if not isinstance(rows, list):
            raise ValueError('records/pages must be a list')
        source = data.get('source', source)
    else:
        rows = data if isinstance(data, list) else [data]
    for row in rows:
        if isinstance(row, dict) and 'text' in row:
            if not isinstance(row['text'], str):
                raise ValueError('Record text must be a string')
            yield {'source': source, 'collection': source, **row, 'text': strip_robot_header(row['text'])}
        else:
            yield {'source': source, 'text': row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)}


def load_records(path):
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob('*') if p.is_file() and not p.is_symlink()
                       and not any(part.startswith('.') for part in p.relative_to(path).parts)
                       and p.suffix.lower() in SUPPORTED)
    elif path.is_file() and path.suffix.lower() in SUPPORTED:
        files = [path]
    else:
        raise ValueError(f'Knowledge path is missing or unsupported: {path}')
    if not files:
        raise ValueError(f'No supported knowledge files found: {path}')
    records = []
    for file in files:
        label = str(file.relative_to(path)) if path.is_dir() else file.name
        try:
            suffix = file.suffix.lower()
            if suffix == '.pdf':
                try:
                    from pypdf import PdfReader
                except ImportError:
                    raise ValueError('PDF support requires pypdf; install updated requirements.') from None
                rows = [{'source': file.name, 'page': number, 'text': page.extract_text(extraction_mode='layout') or ''}
                        for number, page in enumerate(PdfReader(file).pages, 1)]
                if not any(row['text'].strip() for row in rows):
                    raise ValueError('PDF has no extractable text; OCR is required.')
            elif suffix == '.json':
                rows = list(json_records(json.loads(file.read_text(encoding='utf-8-sig')), file.name))
            elif suffix == '.jsonl':
                rows = [row for line in file.read_text(encoding='utf-8-sig').splitlines() if line.strip()
                        for row in json_records(json.loads(line), file.name)]
            else:
                rows = [{'source': file.name, 'text': file.read_text(encoding='utf-8-sig')}]
            records.extend({**row, 'file': label} for row in rows if row['text'].strip())
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ValueError(f'Could not load knowledge file {file}: {exc}') from exc
    if not records:
        raise ValueError(f'Knowledge contains no readable text: {path}')
    return records, [str(file.relative_to(path)) if path.is_dir() else file.name for file in files]
