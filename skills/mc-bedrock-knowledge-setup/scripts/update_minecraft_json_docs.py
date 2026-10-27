#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Download and index Microsoft Creator and bedrock.dev JSON documentation."""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from multiprocessing.dummy import Pool as ThreadPool

try:
    from html.parser import HTMLParser
    from urllib import robotparser
except ImportError:  # pragma: no cover - Python 2 path
    from HTMLParser import HTMLParser
    import robotparser

from compat import Request, quote, urljoin, urlopen, urlparse, utcnow_iso
from pathlib import Path


USER_AGENT = 'mc-bedrock-fast-code-json-indexer/1.0'
MICROSOFT_ROOT = 'https://learn.microsoft.com'
MICROSOFT_TOC = MICROSOFT_ROOT + '/{locale}/minecraft/creator/toc.json?view=minecraft-bedrock-{view}'
BEDROCK_ROOT = 'https://bedrock.dev'
BEDROCK_SITEMAP = BEDROCK_ROOT + '/sitemap.xml'
SOURCE_METADATA = {
    'microsoft': {
        'authority': 'official',
        'home': 'https://learn.microsoft.com/minecraft/creator/',
        'source_repository': 'https://github.com/MicrosoftDocs/minecraft-creator',
        'repository_license': 'CC-BY-4.0',
    },
    'bedrock_dev': {
        'authority': 'community',
        'home': 'https://bedrock.dev/',
        'source_repository': 'https://github.com/destruc7i0n/bedrock-dot-dev',
        'repository_license': 'GPL-3.0',
    },
}
DEFAULT_WORKERS = 8
PROGRESS_EVERY = 20
IDENTIFIER_RE = re.compile(r'\b(?:minecraft|query|variable|temp|context)[:.][A-Za-z0-9_.:-]+', re.I)
FORMAT_VERSION_RE = re.compile(r'\bformat_version\b|\b\d+\.\d+\.\d+\b', re.I)
SPACE_RE = re.compile(r'\s+')


def fetch_bytes(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            req = Request(quote(url, safe=':/?&=%'), headers={'User-Agent': USER_AGENT, 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'})
            response = urlopen(req, timeout=90)
            try:
                return response.read()
            finally:
                response.close()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def fetch_text(url):
    return fetch_bytes(url).decode('utf-8', 'replace')


def progress(message):
    print(message)
    sys.stdout.flush()


def robots_parser(root):
    parser = robotparser.RobotFileParser()
    parser.set_url(root + '/robots.txt')
    try:
        parser.parse(fetch_text(parser.url).splitlines())
    except Exception as exc:
        print('warning: could not read {}: {}'.format(parser.url, exc), file=sys.stderr)
        parser.parse([])
    return parser


def flatten_toc(items, base_url):
    found = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        href = item.get('href')
        if href and not href.startswith(('http:', 'https:', '#')):
            url = urljoin(base_url, href)
            parsed = urlparse(url)
            if parsed.netloc == 'learn.microsoft.com' and '/minecraft/creator/' in parsed.path.lower():
                found.append(url.split('#', 1)[0])
        found.extend(flatten_toc(item.get('children') or item.get('items'), base_url))
    return found


def microsoft_urls(locale, views):
    urls = []
    for view in views:
        toc_url = MICROSOFT_TOC.format(locale=locale, view=view)
        data = json.loads(fetch_text(toc_url))
        base = MICROSOFT_ROOT + '/{}/minecraft/creator/'.format(locale)
        for url in flatten_toc(data.get('items'), base):
            separator = '&' if '?' in url else '?'
            urls.append('{}{}view=minecraft-bedrock-{}'.format(url, separator, view))
    return sorted(set(urls))


def bedrock_urls(versions):
    xml = fetch_text(BEDROCK_SITEMAP)
    urls = re.findall(r'<loc>\s*(.*?)\s*</loc>', xml, re.I)
    allowed = tuple('/docs/{}/'.format(value) for value in versions)
    return sorted(set(url for url in urls if urlparse(url).path.startswith(allowed)))


class ContentParser(HTMLParser):
    def __init__(self):
        try:
            HTMLParser.__init__(self, convert_charrefs=True)
        except TypeError:  # pragma: no cover - Python 2 path
            HTMLParser.__init__(self)
        self.capture_depth = 0
        self.skip_depth = 0
        self.title_depth = 0
        self.heading_depth = 0
        self.code_depth = 0
        self.title = []
        self.description = ''
        self.canonical = ''
        self.text = []
        self.headings = []
        self.current_heading = []
        self.code_blocks = []
        self.current_code = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'svg', 'nav', 'footer'):
            self.skip_depth += 1
        if tag == 'title':
            self.title_depth += 1
        if tag in ('main', 'article'):
            self.capture_depth += 1
        if tag == 'meta' and attrs.get('name') == 'description':
            self.description = attrs.get('content', '')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs.get('href', '')
        if tag in ('h1', 'h2', 'h3', 'h4') and self.capture_depth:
            self.heading_depth += 1
            self.current_heading = []
        if tag in ('pre', 'code') and self.capture_depth:
            self.code_depth += 1
            if self.code_depth == 1:
                self.current_code = []
        if tag in ('p', 'div', 'li', 'tr', 'br', 'pre', 'h1', 'h2', 'h3', 'h4') and self.capture_depth:
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag == 'title' and self.title_depth:
            self.title_depth -= 1
        if tag in ('h1', 'h2', 'h3', 'h4') and self.heading_depth:
            heading = SPACE_RE.sub(' ', ''.join(self.current_heading)).strip()
            if heading:
                self.headings.append(heading)
            self.heading_depth -= 1
            self.current_heading = []
        if tag in ('pre', 'code') and self.code_depth:
            self.code_depth -= 1
            if not self.code_depth:
                code = ''.join(self.current_code).strip()
                if code:
                    self.code_blocks.append(code)
                self.current_code = []
        if tag in ('main', 'article') and self.capture_depth:
            self.capture_depth -= 1
        if tag in ('script', 'style', 'svg', 'nav', 'footer') and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.title_depth:
            self.title.append(data)
        if self.capture_depth and not self.skip_depth:
            self.text.append(data)
            if self.heading_depth:
                self.current_heading.append(data)
            if self.code_depth:
                self.current_code.append(data)


def parse_page(source, version, url, html):
    parser = ContentParser()
    parser.feed(html)
    content = '\n'.join(SPACE_RE.sub(' ', line).strip() for line in ''.join(parser.text).splitlines() if line.strip())
    if not content:
        content = SPACE_RE.sub(' ', re.sub(r'<[^>]+>', ' ', html)).strip()
    identifiers = sorted(set(IDENTIFIER_RE.findall(content)), key=lambda value: value.lower())
    versions = sorted(set(FORMAT_VERSION_RE.findall(content)))
    return {
        'source': source,
        'version': version,
        'title': SPACE_RE.sub(' ', ''.join(parser.title)).strip() or (parser.headings[0] if parser.headings else url),
        'description': parser.description,
        'source_url': url,
        'canonical_url': parser.canonical or url,
        'headings': parser.headings,
        'identifiers': identifiers,
        'format_versions': versions,
        'code_blocks': parser.code_blocks,
        'content': content,
    }


def cache_name(url):
    return hashlib.sha1(url.encode('utf-8')).hexdigest() + '.html'


def download_one(task):
    source, version, url, raw_dir, refresh = task
    path = raw_dir / source / version / cache_name(url)
    try:
        if path.exists() and not refresh:
            data = path.read_bytes()
            cached = True
        else:
            data = fetch_bytes(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            cached = False
        record = parse_page(source, version, url, data.decode('utf-8', 'replace'))
        record['local_html'] = str(path)
        record['cached'] = cached
        return record, ''
    except Exception as exc:
        return None, '{}: {}'.format(url, exc)


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), 'wb') as handle:
        for record in records:
            line = json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n'
            handle.write(line.encode('utf-8'))


def read_jsonl(path):
    if not path.exists():
        return []
    records = []
    with path.open('r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def build_index(records, out):
    compact = []
    for record in records:
        compact.append({
            'source': record['source'],
            'version': record['version'],
            'title': record['title'],
            'description': record['description'],
            'source_url': record['source_url'],
            'headings': record['headings'],
            'identifiers': record['identifiers'],
            'format_versions': record['format_versions'],
        })
    index = {
        'schema_version': 1,
        'generated_at': utcnow_iso(),
        'record_count': len(records),
        'sources': sorted(set(record['source'] for record in records)),
        'source_metadata': SOURCE_METADATA,
        'records': compact,
        'pages': 'pages.jsonl',
    }
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_jsonl(out / 'pages.jsonl', records)
    sqlite_info = build_sqlite_index(records, out / 'search.sqlite3')
    index['sqlite'] = sqlite_info
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return index


def authority_rank(source, version):
    if source == 'microsoft' and version == 'stable':
        return 0
    if source == 'microsoft':
        return 1
    if source == 'bedrock_dev' and version == 'stable':
        return 2
    return 3


def replace_file(source, destination):
    try:
        os.replace(str(source), str(destination))
    except AttributeError:  # pragma: no cover - Python 2 path
        if destination.exists():
            os.remove(str(destination))
        os.rename(str(source), str(destination))


def build_sqlite_index(records, path):
    temporary = Path(str(path) + '.tmp')
    if temporary.exists():
        os.remove(str(temporary))
    connection = sqlite3.connect(str(temporary))
    fts_engine = 'fts5'
    trigram = False
    try:
        connection.executescript('''
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                version TEXT NOT NULL,
                authority_rank INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                source_url TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                headings TEXT NOT NULL,
                identifiers TEXT NOT NULL,
                code_blocks TEXT NOT NULL,
                content TEXT NOT NULL,
                search_types TEXT NOT NULL
            );
            CREATE TABLE exact_identifiers (
                identifier_norm TEXT NOT NULL,
                identifier TEXT NOT NULL,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                PRIMARY KEY (identifier_norm, document_id)
            );
            CREATE INDEX exact_identifiers_document ON exact_identifiers(document_id);
            CREATE TABLE format_versions (
                version_norm TEXT NOT NULL,
                version TEXT NOT NULL,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                PRIMARY KEY (version_norm, document_id)
            );
            CREATE INDEX format_versions_document ON format_versions(document_id);
        ''')
        try:
            connection.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(title, description, headings, identifiers, code_blocks, content, content='documents', content_rowid='id', tokenize='unicode61 remove_diacritics 2')")
        except sqlite3.OperationalError:
            fts_engine = 'fts4'
            connection.execute("CREATE VIRTUAL TABLE documents_fts USING fts4(title, description, headings, identifiers, code_blocks, content, content='documents', tokenize=unicode61)")
        if fts_engine == 'fts5':
            try:
                connection.execute("CREATE VIRTUAL TABLE documents_trigram USING fts5(title, description, headings, identifiers, code_blocks, content, content='documents', content_rowid='id', tokenize='trigram')")
                trigram = True
            except sqlite3.OperationalError:
                trigram = False
        document_sql = '''INSERT INTO documents
            (id, source, version, authority_rank, title, description, source_url, canonical_url, headings, identifiers, code_blocks, content, search_types)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        for document_id, record in enumerate(records, 1):
            headings = '\n'.join(record.get('headings') or [])
            identifiers = '\n'.join(record.get('identifiers') or [])
            code_blocks = '\n\n'.join(record.get('code_blocks') or [])
            search_types = ' '.join((record.get('source') or '', record.get('version') or '', record.get('title') or '', headings, identifiers))
            values = (
                document_id,
                record.get('source') or '',
                record.get('version') or '',
                authority_rank(record.get('source'), record.get('version')),
                record.get('title') or '',
                record.get('description') or '',
                record.get('source_url') or '',
                record.get('canonical_url') or record.get('source_url') or '',
                headings,
                identifiers,
                code_blocks,
                record.get('content') or '',
                search_types,
            )
            connection.execute(document_sql, values)
            for identifier in sorted(set(record.get('identifiers') or []), key=lambda value: value.lower()):
                connection.execute('INSERT OR IGNORE INTO exact_identifiers VALUES (?, ?, ?)', (identifier.lower(), identifier, document_id))
            for version in sorted(set(record.get('format_versions') or [])):
                connection.execute('INSERT OR IGNORE INTO format_versions VALUES (?, ?, ?)', (version.lower(), version, document_id))
        connection.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")
        if trigram:
            connection.execute("INSERT INTO documents_trigram(documents_trigram) VALUES('rebuild')")
        metadata = {
            'schema_version': '1',
            'generated_at': utcnow_iso(),
            'document_count': str(len(records)),
            'fts_engine': fts_engine,
            'trigram': '1' if trigram else '0',
        }
        connection.executemany('INSERT INTO metadata VALUES (?, ?)', sorted(metadata.items()))
        connection.execute('PRAGMA user_version=1')
        connection.commit()
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise RuntimeError('SQLite integrity check failed: {}'.format(integrity))
    finally:
        connection.close()
    replace_file(temporary, path)
    return {
        'path': path.name,
        'schema_version': 1,
        'fts_engine': fts_engine,
        'trigram': trigram,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='External output directory.')
    parser.add_argument('--source', action='append', choices=['microsoft', 'bedrock-dev', 'all'], help='Source to update. Defaults to all; may be repeated.')
    parser.add_argument('--locale', default='zh-cn', help='Microsoft Learn locale (default: zh-cn).')
    parser.add_argument('--microsoft-view', action='append', choices=['stable', 'preview'], help='Creator documentation view. Defaults to stable.')
    parser.add_argument('--bedrock-version', action='append', choices=['stable', 'beta'], help='bedrock.dev tree. Defaults to stable and beta.')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help='Concurrent downloads (default: {}).'.format(DEFAULT_WORKERS))
    parser.add_argument('--max-pages', type=int, help='Limit each source for smoke tests.')
    parser.add_argument('--refresh', action='store_true', help='Redownload pages already present in the raw-page cache.')
    parser.add_argument('--rebuild-index-only', action='store_true', help='Rebuild index.json and SQLite from the existing pages.jsonl without crawling.')
    return parser.parse_args()


def main():
    args = parse_args()
    out = Path(args.out).expanduser().resolve()
    raw_dir = out / 'raw'
    if args.rebuild_index_only:
        records = read_jsonl(out / 'pages.jsonl')
        if not records:
            print('No existing pages.jsonl records were found at {}.'.format(out), file=sys.stderr)
            return 2
        index = build_index(records, out)
        progress('minecraft-json index rebuilt: {} records at {}'.format(index['record_count'], out / 'search.sqlite3'))
        return 0
    sources = set(args.source or ['all'])
    if 'all' in sources:
        sources = {'microsoft', 'bedrock-dev'}
    tasks = []
    robots = {
        'microsoft': robots_parser(MICROSOFT_ROOT),
        'bedrock-dev': robots_parser(BEDROCK_ROOT),
    }
    if 'microsoft' in sources:
        views = args.microsoft_view or ['stable']
        urls = microsoft_urls(args.locale, views)
        if args.max_pages:
            urls = urls[:args.max_pages]
        for url in urls:
            view = re.search(r'minecraft-bedrock-(stable|preview)', url).group(1)
            if robots['microsoft'].can_fetch(USER_AGENT, url):
                tasks.append(('microsoft', view, url, raw_dir, args.refresh))
    if 'bedrock-dev' in sources:
        versions = args.bedrock_version or ['stable', 'beta']
        urls = bedrock_urls(versions)
        grouped = {}
        for url in urls:
            version = urlparse(url).path.split('/')[2]
            grouped.setdefault(version, []).append(url)
        for version in versions:
            selected = grouped.get(version, [])
            if args.max_pages:
                selected = selected[:args.max_pages]
            for url in selected:
                if robots['bedrock-dev'].can_fetch(USER_AGENT, url):
                    tasks.append(('bedrock_dev', version, url, raw_dir, args.refresh))
    if not tasks:
        print('No crawlable documentation URLs were discovered.', file=sys.stderr)
        return 2
    progress('minecraft-json: discovered {} pages; allow the process enough time to finish'.format(len(tasks)))
    records = []
    errors = []
    pool = ThreadPool(max(1, args.workers))
    try:
        for index, result in enumerate(pool.imap_unordered(download_one, tasks), 1):
            record, error = result
            if record:
                records.append(record)
            if error:
                errors.append(error)
            if index % PROGRESS_EVERY == 0 or index == len(tasks):
                progress('minecraft-json progress: {}/{} pages, {} succeeded, {} failed'.format(index, len(tasks), len(records), len(errors)))
    finally:
        pool.close()
        pool.join()
    updated_trees = set((task[0].replace('-', '_'), task[1]) for task in tasks)
    previous = read_jsonl(out / 'pages.jsonl')
    records.extend(record for record in previous if (record.get('source'), record.get('version')) not in updated_trees)
    records.sort(key=lambda item: (item['source'], item['version'], item['title'].lower()))
    index = build_index(records, out)
    (out / 'errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    progress('minecraft-json index: {} records at {}'.format(index['record_count'], out / 'index.json'))
    if errors:
        print('warning: {} pages failed; rerun to reuse successful cached pages and retry failures'.format(len(errors)), file=sys.stderr)
    return 0 if records else 1


if __name__ == '__main__':
    raise SystemExit(main())
