#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Query prepared API/demo/vanilla knowledge indexes."""
import argparse
import json
import re
import sqlite3
import subprocess
from compat import run_command, try_load_json
import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent

def load_json(path):
    return try_load_json(path)

def find_registry(path, root):
    candidates = []
    if path:
        candidates.append(Path(path).expanduser())
    if root:
        candidates.append(Path(root).expanduser() / 'knowledge_registry.json')
    candidates.append(Path.home() / '.codex' / 'mc-bedrock-fast-code-data' / 'knowledge_registry.json')
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise SystemExit('knowledge_registry.json not found; use mc-bedrock-knowledge-setup for the required source or pass --registry')

def text_match(text, query):
    return query.lower() in text.lower()

def load_registry(args):
    path = find_registry(args.registry, args.root)
    data = load_json(path)
    if not isinstance(data, dict):
        raise SystemExit('invalid registry: {}'.format(path))
    data['_registry_path'] = str(path)
    return data

def query_demo(registry, query, kind, limit):
    demo_root = registry.get('demo_index')
    if not demo_root:
        return []
    index = load_json(Path(demo_root) / 'demo_index.json')
    if not isinstance(index, dict):
        return []
    results = []
    for rec in index.get('records', []):
        if not isinstance(rec, dict):
            continue
        if kind and kind != 'all' and (kind not in str(rec.get('category', ''))):
            continue
        blob = json.dumps(rec, ensure_ascii=False)
        if text_match(blob, query):
            results.append({'source': 'demo', 'category': rec.get('category'), 'demo': rec.get('demo'), 'path': rec.get('path'), 'identifier': (rec.get('json') or {}).get('identifier') if isinstance(rec.get('json'), dict) else '', 'sample': rec.get('sample', '')[:300]})
        if len(results) >= limit:
            break
    return results

def api_index_files(api_kind):
    if api_kind == 'interface':
        return ['interfaces.md']
    if api_kind == 'event':
        return ['events.md']
    return ['interfaces.md', 'events.md']


def official_api_doc_files(api_kind):
    if api_kind == 'interface':
        return ['official-api-interfaces.md']
    if api_kind == 'event':
        return ['official-api-events.md']
    return ['official-api-docs.md']


def mirror_api_root(api_root, api_kind):
    root = Path(api_root) / 'wiki' / 'docs' / 'mcdocs' / '1-ModAPI'
    if api_kind == 'interface':
        return root / '接口'
    if api_kind == 'event':
        return root / '事件'
    return Path(api_root) / 'wiki' / 'docs' / 'mcdocs'


def query_index_files(api_root, files, query, limit, source):
    results = []
    seen = set()
    for name in files:
        path = Path(api_root) / name
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if not text_match(line, query):
                continue
            key = (str(path), lineno)
            if key in seen:
                continue
            seen.add(key)
            results.append({'source': source, 'path': str(path), 'line': lineno, 'text': line[:500]})
            if len(results) >= limit:
                return results
    return results


def query_api_type(api_root, query, limit, api_kind):
    results = query_index_files(api_root, api_index_files(api_kind), query, limit, 'api_{}'.format(api_kind))
    if not results:
        results = query_index_files(api_root, official_api_doc_files(api_kind), query, limit, 'official_api_doc_{}'.format(api_kind))
    if not results:
        results = query_document_tree(mirror_api_root(api_root, api_kind), query, limit, 'mirror_api_doc_{}'.format(api_kind), '*.md')
    return results


def query_api(registry, query, kind, limit, api_kind='auto', include_non_api_docs=False, api_only=False):
    api_root = registry.get('api_references')
    if not api_root:
        return []
    results = query_api_type(api_root, query, limit, api_kind)
    if not results and api_kind in {'interface', 'event'}:
        alternate_kind = 'event' if api_kind == 'interface' else 'interface'
        results = query_api_type(api_root, query, limit, alternate_kind)
    if results and not include_non_api_docs:
        return results
    if api_only:
        return results
    remaining = limit - len(results)
    if remaining > 0:
        results.extend(query_index_files(api_root, ['official-development-guides.md', 'official-tutorials.md'], query, remaining, 'non_api_index'))
    if not results:
        results.extend(query_document_tree(Path(api_root) / 'official', query, limit, 'official_non_api_doc', '*.html'))
    if not results:
        results.extend(query_document_tree(Path(api_root) / 'wiki' / 'docs', query, limit, 'mirror_non_api_doc', '*.md'))
    return results


def query_document_tree(root, query, limit, source, pattern):
    if not root.exists():
        return []
    results = []
    for path in sorted(root.rglob(pattern)):
        value = path.read_text(encoding='utf-8', errors='replace')
        if not text_match(value, query):
            continue
        position = value.lower().find(query.lower())
        start = max(0, position - 300)
        end = min(len(value), position + len(query) + 900)
        results.append({'source': source, 'path': str(path), 'text': value[start:end]})
        if len(results) >= limit:
            break
    return results


def query_api_updates(registry, query, limit):
    api_root = registry.get('api_references')
    if not api_root:
        return []
    root = Path(api_root) / 'wiki'
    if not root.exists():
        return []
    hints = ('update', '更新', 'deprecated', '废弃', 'changelog', 'change')
    results = []
    for path in sorted(root.rglob('*.md')):
        path_text = path.as_posix().lower()
        text = path.read_text(encoding='utf-8', errors='replace')
        if not any(h.lower() in path_text or h.lower() in text.lower() for h in hints):
            continue
        if text_match(text, query):
            results.append({'source': 'api_update_note', 'path': str(path), 'text': text[:1200], 'recommendation': 'This API may be old or changed; prefer the newer API described by the update note and ask before rewriting project code.'})
        if len(results) >= limit:
            break
    return results


def custom_indexes(registry):
    found = []
    for item in registry.get('custom_project_indexes', []) or []:
        if not isinstance(item, dict):
            continue
        path = item.get('index')
        if path and Path(path).exists():
            found.append((item, Path(path)))
    return found


def query_custom(registry, query, kind, limit):
    results = []
    for meta, index_path in custom_indexes(registry):
        index = load_json(index_path)
        if not isinstance(index, dict):
            continue
        records = index.get('records', []) or []
        def rank(rec):
            return 0 if rec.get('category') == 'lang_zh_cn' or str(rec.get('path', '')).endswith('zh_CN.lang') else 1
        for rec in sorted(records, key=rank):
            if not isinstance(rec, dict):
                continue
            if kind and kind != 'all' and kind not in str(rec.get('category', '')):
                continue
            blob = json.dumps(rec, ensure_ascii=False)
            if text_match(blob, query):
                results.append({'source': 'custom_local', 'index': str(index_path), 'name': meta.get('name') or index.get('name'), 'repo': meta.get('repo') or index.get('repo'), 'path': rec.get('path'), 'category': rec.get('category'), 'text': blob[:1500]})
            if len(results) >= limit:
                return results
    return results

def query_remote(registry, query, kind, limit):
    remote_root = registry.get('remote_public_indexes')
    if not remote_root:
        return []
    root = Path(remote_root)
    if not root.exists():
        return []
    results = []
    for path in sorted(root.rglob('*.json')):
        data = load_json(path)
        blob = json.dumps(data, ensure_ascii=False) if data is not None else path.read_text(encoding='utf-8', errors='replace')
        if kind and kind != 'all' and (kind.lower() not in blob.lower()) and (kind.lower() not in path.as_posix().lower()):
            continue
        if text_match(blob, query):
            results.append({'source': 'remote_public', 'path': str(path), 'text': blob[:1500]})
        if len(results) >= limit:
            break
    return results


def sqlite_filters(source_filter, kind, alias='d'):
    clauses = []
    params = []
    if source_filter:
        clauses.append('{}.source = ?'.format(alias))
        params.append(source_filter)
    if kind and kind != 'all':
        clauses.append('lower({}.search_types) LIKE ?'.format(alias))
        params.append('%{}%'.format(kind.lower()))
    return clauses, params


def sqlite_result(row, match_kind, score=None):
    result = {
        'source': row['source'],
        'version': row['version'],
        'title': row['title'],
        'url': row['source_url'],
        'match': match_kind,
        'identifiers': ', '.join((row['identifiers'] or '').splitlines()[:20]),
        'text': row['snippet'] or row['description'] or '',
    }
    if score is not None:
        result['score'] = '{:.6f}'.format(score)
    return result


def fts_query_text(query):
    terms = re.findall(r'[A-Za-z0-9_]+|[^\W\x00-\x7f]+', query, re.UNICODE)
    return ' AND '.join(('"{}"'.format(term.replace('"', '""')) for term in terms if term))


def query_minecraft_json_sqlite(root, query, kind, limit, source_filter=None):
    path = Path(root) / 'search.sqlite3'
    if not path.exists():
        return None
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute('SELECT key, value FROM metadata'))
        clauses, filter_params = sqlite_filters(source_filter, kind)
        where = (' AND ' + ' AND '.join(clauses)) if clauses else ''
        base_columns = 'd.source, d.version, d.title, d.description, d.source_url, d.identifiers'
        exact_sql = '''SELECT {columns}, '' AS snippet
            FROM exact_identifiers e JOIN documents d ON d.id = e.document_id
            WHERE e.identifier_norm = ?{where}
            ORDER BY d.authority_rank, CASE WHEN lower(d.title) LIKE ? THEN 0 ELSE 1 END, d.title LIMIT ?'''.format(columns=base_columns, where=where)
        rows = connection.execute(exact_sql, [query.lower()] + filter_params + ['%{}%'.format(query.lower()), limit]).fetchall()
        results = [sqlite_result(row, 'exact_identifier') for row in rows]
        seen = set((row['source'], row['version'], row['source_url']) for row in rows)
        remaining = limit - len(results)
        if remaining > 0 and re.match(r'^\d+\.\d+(?:\.\d+)?$', query):
            version_sql = '''SELECT {columns}, '' AS snippet
                FROM format_versions v JOIN documents d ON d.id = v.document_id
                WHERE v.version_norm = ?{where}
                ORDER BY d.authority_rank, CASE WHEN lower(d.title) LIKE ? THEN 0 ELSE 1 END, d.title LIMIT ?'''.format(columns=base_columns, where=where)
            for row in connection.execute(version_sql, [query.lower()] + filter_params + ['%{}%'.format(query.lower()), remaining]).fetchall():
                key = (row['source'], row['version'], row['source_url'])
                if key not in seen:
                    seen.add(key)
                    results.append(sqlite_result(row, 'exact_format_version'))
        remaining = limit - len(results)
        match_query = fts_query_text(query)
        if remaining > 0 and match_query:
            if metadata.get('fts_engine') == 'fts5':
                fts_sql = '''SELECT {columns},
                    snippet(documents_fts, 5, '[', ']', ' ... ', 32) AS snippet,
                    bm25(documents_fts, 12.0, 8.0, 6.0, 10.0, 4.0, 1.0) AS rank
                    FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ?{where}
                    ORDER BY d.authority_rank, rank LIMIT ?'''.format(columns=base_columns, where=where)
            else:
                fts_sql = '''SELECT {columns}, snippet(documents_fts, '[', ']', ' ... ', -1, 32) AS snippet, 0.0 AS rank
                    FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ?{where}
                    ORDER BY d.authority_rank, d.title LIMIT ?'''.format(columns=base_columns, where=where)
            rows = connection.execute(fts_sql, [match_query] + filter_params + [max(remaining * 4, remaining)]).fetchall()
            for row in rows:
                key = (row['source'], row['version'], row['source_url'])
                if key in seen:
                    continue
                seen.add(key)
                results.append(sqlite_result(row, 'fts', row['rank']))
                if len(results) >= limit:
                    break
        remaining = limit - len(results)
        if remaining > 0 and metadata.get('trigram') == '1' and len(query) >= 3:
            trigram_sql = '''SELECT {columns},
                snippet(documents_trigram, 5, '[', ']', ' ... ', 32) AS snippet,
                bm25(documents_trigram, 12.0, 8.0, 6.0, 10.0, 4.0, 1.0) AS rank
                FROM documents_trigram JOIN documents d ON d.id = documents_trigram.rowid
                WHERE documents_trigram MATCH ?{where}
                ORDER BY d.authority_rank, rank LIMIT ?'''.format(columns=base_columns, where=where)
            trigram_query = '"{}"'.format(query.replace('"', '""'))
            rows = connection.execute(trigram_sql, [trigram_query] + filter_params + [max(remaining * 4, remaining)]).fetchall()
            for row in rows:
                key = (row['source'], row['version'], row['source_url'])
                if key in seen:
                    continue
                seen.add(key)
                results.append(sqlite_result(row, 'fts_trigram', row['rank']))
                if len(results) >= limit:
                    break
        return results
    finally:
        connection.close()


def query_minecraft_json_jsonl(registry, query, kind, limit, source_filter=None):
    root = registry.get('minecraft_json_docs')
    if not root:
        return []
    pages = Path(root) / 'pages.jsonl'
    if not pages.exists():
        return []
    ranked = []
    query_lower = query.lower()
    with pages.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            source = str(record.get('source') or '')
            if source_filter and source != source_filter:
                continue
            if kind and kind != 'all':
                type_blob = ' '.join([
                    source,
                    str(record.get('version') or ''),
                    str(record.get('title') or ''),
                    ' '.join(record.get('headings') or []),
                    ' '.join(record.get('identifiers') or []),
                ])
                if not text_match(type_blob, kind):
                    continue
            blob = json.dumps(record, ensure_ascii=False)
            if not text_match(blob, query):
                continue
            identifiers = [str(value) for value in record.get('identifiers') or []]
            title = str(record.get('title') or '')
            headings = [str(value) for value in record.get('headings') or []]
            if any(query_lower == value.lower() for value in identifiers):
                rank = 0
            elif query_lower in title.lower():
                rank = 1
            elif any(query_lower in value.lower() for value in headings):
                rank = 2
            elif any(query_lower in value.lower() for value in identifiers):
                rank = 3
            else:
                rank = 4
            position = blob.lower().find(query_lower)
            result = {
                'source': source,
                'version': record.get('version'),
                'title': record.get('title'),
                'url': record.get('source_url'),
                'identifiers': ', '.join((record.get('identifiers') or [])[:20]),
                'text': blob[max(0, position - 300):position + len(query) + 900],
            }
            ranked.append((rank, title.lower(), result))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def query_minecraft_json(registry, query, kind, limit, source_filter=None):
    root = registry.get('minecraft_json_docs')
    if not root:
        return []
    try:
        results = query_minecraft_json_sqlite(root, query, kind, limit, source_filter)
        if results:
            return results
    except (sqlite3.DatabaseError, sqlite3.OperationalError, ValueError):
        pass
    return query_minecraft_json_jsonl(registry, query, kind, limit, source_filter)

def vanilla_indexes(registry):
    root = registry.get('vanilla_indexes')
    if not root:
        return []
    base = Path(root)
    if not base.exists():
        return []
    return sorted((path for path in base.glob('*/index.json') if path.is_file()), key=lambda p: p.parent.name, reverse=True)

def query_vanilla(registry, query, kind, limit):
    results = []
    for index_path in vanilla_indexes(registry):
        cmd = [sys.executable, str(SCRIPT_DIR / 'local_query_index.py'), '--index', str(index_path), query]
        if kind and kind not in {'all', 'demo', 'api', 'vanilla'}:
            cmd.extend(['--kind', kind])
        proc = run_command(cmd)
        text = (proc.stdout or proc.stderr).strip()
        if proc.returncode == 0 and text:
            results.append({'source': 'vanilla', 'version': index_path.parent.name, 'index': str(index_path), 'text': text[:2000]})
        if len(results) >= limit:
            break
    return results

def print_results(results):
    for i, rec in enumerate(results, 1):
        print('## Result {}: {}'.format(i, rec.get('source')))
        for key, value in rec.items():
            if key == 'source' or value in (None, ''):
                continue
            print('{}: {}'.format(key, value))
        print()

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', help='Identifier, name, path fragment, API, material, texture, controller, etc.')
    parser.add_argument('--kind', default='all', help='Optional kind filter: render_controller, material, texture, entity, item, component, ui, api, vanilla, custom, etc.')
    parser.add_argument('--registry', help='Path to knowledge_registry.json.')
    parser.add_argument('--root', help='Knowledge root containing knowledge_registry.json.')
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--api-kind', choices=['auto', 'interface', 'event'], default='auto', help='Search only interfaces or events when the user states the API type.')
    parser.add_argument('--api-only', action='store_true', help='Do not expand a zero-result API lookup into development guides or tutorials.')
    parser.add_argument('--include-non-api-docs', action='store_true', help='Search development-guide and tutorial indexes even when API results exist.')
    parser.add_argument('--source', choices=['all', 'custom', 'demo', 'api', 'vanilla', 'minecraft-json', 'microsoft', 'bedrock-dev', 'remote'], default='all')
    return parser.parse_args()

def main():
    args = parse_args()
    registry = load_registry(args)
    results = []
    if args.source in {'all', 'custom'}:
        results.extend(query_custom(registry, args.query, args.kind, args.limit))
    if len(results) < args.limit and args.source in {'all', 'vanilla'}:
        results.extend(query_vanilla(registry, args.query, args.kind, args.limit - len(results)))
    if len(results) < args.limit and args.source in {'all', 'demo'}:
        results.extend(query_demo(registry, args.query, args.kind, args.limit - len(results)))
    if len(results) < args.limit and args.source in {'all', 'api'}:
        results.extend(query_api(registry, args.query, args.kind, args.limit - len(results), args.api_kind, args.include_non_api_docs, args.api_only))
    if len(results) < args.limit and args.source in {'all', 'minecraft-json', 'microsoft', 'bedrock-dev'}:
        source_filter = None
        if args.source == 'microsoft':
            source_filter = 'microsoft'
        elif args.source == 'bedrock-dev':
            source_filter = 'bedrock_dev'
        results.extend(query_minecraft_json(registry, args.query, args.kind, args.limit - len(results), source_filter))
    if len(results) < args.limit and args.source in {'all', 'remote'}:
        results.extend(query_remote(registry, args.query, args.kind, args.limit - len(results)))
    print_results(results)
    if not results:
        print('No matches found. Check the selected source; use mc-bedrock-knowledge-setup only if its required index is missing.')
        return 1
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
