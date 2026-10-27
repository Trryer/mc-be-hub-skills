#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Download and index the current NetEase ModSDK API documentation."""
from __future__ import print_function

import argparse
import hashlib
import json
import re
import sys
from multiprocessing.dummy import Pool as ThreadPool

from compat import quote
from compat import Request, urlopen
from compat import urljoin, urlparse
from pathlib import Path


OWNER = 'EaseCation'
REPO = 'netease-modsdk-wiki'
BRANCH = 'main'
API_BASE = 'https://api.github.com/repos/{}/{}'.format(OWNER, REPO)
RAW_BASE = 'https://raw.githubusercontent.com/{}/{}/{}'.format(OWNER, REPO, BRANCH)
OFFICIAL_ROOT = 'https://mc.163.com'
OFFICIAL_PREFIXES = (
    '/dev/mcmanual/mc-dev/mcdocs/',
    '/dev/mcmanual/mc-dev/mcguide/',
    '/dev/mcmanual/mc-dev/mconline/',
)
OFFICIAL_SCOPE_PREFIXES = {
    'api': ('/dev/mcmanual/mc-dev/mcdocs/',),
    'guides': ('/dev/mcmanual/mc-dev/mcguide/',),
    'tutorials': ('/dev/mcmanual/mc-dev/mconline/',),
}
OFFICIAL_API_PREFIXES = (
    '/dev/mcmanual/mc-dev/mcdocs/1-ModAPI/',
    '/dev/mcmanual/mc-dev/mcdocs/1-ModAPI-beta/',
)
OFFICIAL_SEEDS = (
    OFFICIAL_ROOT + '/dev/mcmanual/mc-dev/mcdocs/1-ModAPI/接口/Api索引表.html?catalog=1',
    OFFICIAL_ROOT + '/dev/mcmanual/mc-dev/mcdocs/1-ModAPI-beta/事件/玩家.html?catalog=1',
    OFFICIAL_ROOT + '/dev/mcmanual/mc-dev/mcdocs/0-%E6%A6%82%E8%BF%B0/0-%E6%A6%82%E8%BF%B0.html?catalog=1',
    OFFICIAL_ROOT + '/dev/mcmanual/mc-dev/mcguide/12-%E5%85%A5%E9%97%A8%E6%95%99%E7%A8%8B/10-%E6%B3%A8%E5%86%8C%E6%88%90%E4%B8%BA%E5%BC%80%E5%8F%91%E8%80%85.html?catalog=1',
    OFFICIAL_ROOT + '/dev/mcmanual/mc-dev/mconline/5-%E6%B8%B8%E6%88%8F%E5%85%A5%E9%97%A8%E4%B8%8E%E5%9F%BA%E7%A1%80%E8%AE%B2%E8%A7%A3/19-%E8%AE%A4%E8%AF%86%E6%88%91%E7%9A%84%E4%B8%96%E7%95%8C/0-%E6%80%BB%E8%A7%88.html?catalog=1',
    OFFICIAL_ROOT + '/dev/list.html?catalog=1&hfrom=%E6%B8%B8%E6%88%8F%E5%85%A5%E9%97%A8%E4%B8%8E%E5%9F%BA%E7%A1%80%E8%AE%B2%E8%A7%A3&pageType=3',
    OFFICIAL_ROOT + '/dev/list.html?catalog=1&hfrom=%E8%A7%84%E8%8C%83%E5%BC%80%E5%8F%91&pageType=2',
)
ROOT = Path(__file__).resolve().parent
REFERENCES = Path.cwd() / 'mc_bedrock_api_references'
WIKI = REFERENCES / 'wiki'
OFFICIAL = REFERENCES / 'official'
DEFAULT_WORKERS = 12
PROGRESS_EVERY = 25
DOWNLOAD_EXACT = {'api-index.json', 'docs/mcdocs/readme.md', 'docs/mcdocs/context7.json'}
DOWNLOAD_PREFIXES = ('docs/',)
HREF_RE = re.compile(r'''href\s*=\s*["']([^"']+)["']''', re.I)
H2_RE = re.compile(r'<h2\b([^>]*)>(.*?)</h2\s*>', re.I | re.S)
TITLE_RE = re.compile(r'<title\b[^>]*>(.*?)</title\s*>', re.I | re.S)
ID_RE = re.compile(r'''\bid\s*=\s*["']([^"']+)["']''', re.I)
TAG_RE = re.compile(r'<[^>]+>')
SPACE_RE = re.compile(r'\s+')
MARKDOWN_API_HEADING_RE = re.compile(r'^##\s+([A-Za-z_][A-Za-z0-9_]*)\s*$', re.M)
MARKDOWN_LINK_RE = re.compile(r'\[([^\]]+)\]\([^\)]+\)')
MARKDOWN_SECTION_LABELS = (
    u'\u53c2\u6570',
    u'\u8fd4\u56de\u503c',
    u'\u5907\u6ce8',
    u'\u793a\u4f8b',
)


def fetch_bytes(url):
    request_url = quote(url, safe=':/?&=%')
    req = Request(request_url, headers={'User-Agent': 'mc-bedrock-fast-code-api-indexer/1.0'})
    response = urlopen(req, timeout=60)
    try:
        return response.read()
    finally:
        response.close()


def progress(message):
    print(message)
    sys.stdout.flush()


def fetch_json(url):
    return json.loads(fetch_bytes(url).decode('utf-8', 'replace'))


def repo_tree():
    url = '{}/git/trees/{}?recursive=1'.format(API_BASE, BRANCH)
    data = fetch_json(url)
    if data.get('truncated'):
        print('warning: GitHub tree response is truncated', file=sys.stderr)
    return data.get('tree', [])


def should_download(path):
    if path in DOWNLOAD_EXACT:
        return True
    return path.endswith('.md') and any((path.startswith(prefix) for prefix in DOWNLOAD_PREFIXES))


def raw_url(path):
    return '{}/{}'.format(RAW_BASE, quote(path, safe='/'))


def write_binary(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def download_one(path):
    data = fetch_bytes(raw_url(path))
    write_binary(WIKI / path, data)
    if path == 'api-index.json':
        write_binary(REFERENCES / 'api-index.mirror.raw.json', data)
    return path


def read_json_lenient(path):
    return json.loads(path.read_bytes().decode('utf-8', 'replace'))


def md_escape(value):
    if value is None:
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ').strip()
    return text.replace('|', '\\|')


def anchor(text):
    value = text.strip().lower()
    value = re.sub(r'[^\w\- ]+', '', value)
    value = re.sub(r'\s+', '-', value)
    return value or 'entry'


def local_doc_link(link):
    if not link:
        return ''
    clean = link.split('#', 1)[0].lstrip('/')
    if not clean:
        return ''
    return (Path('wiki') / clean).as_posix()


def summarize_params(values):
    if not values:
        return ''
    parts = []
    for item in values:
        if isinstance(item, dict):
            name = item.get('name') or item.get('param') or item.get('key') or ''
            value_type = item.get('type') or item.get('valueType') or ''
            desc = item.get('description') or item.get('desc') or item.get('remark') or ''
            combined = ': '.join((value for value in [name, value_type] if value))
            if desc:
                combined = '{} {}'.format(combined, desc).strip()
            if combined:
                parts.append(combined)
        elif item:
            parts.append(str(item))
    return '; '.join(parts[:6])


def markdown_to_plain(value):
    text = MARKDOWN_LINK_RE.sub(r'\1', value)
    text = TAG_RE.sub(' ', text)
    lines = []
    for line in text.splitlines():
        clean = line.strip().strip('|').strip()
        if not clean or clean.startswith('```'):
            continue
        clean = clean.replace('|', ' ').lstrip('-').strip()
        if clean and not re.match(r'^:?-{3,}', clean):
            lines.append(clean)
    return SPACE_RE.sub(' ', ' '.join(lines)).strip()[:1200]


def markdown_section_value(section, label):
    marker = re.compile(r'^-\s*{}\s*$'.format(re.escape(label)), re.M)
    match = marker.search(section)
    if not match:
        return ''
    start = match.end()
    end = len(section)
    for other_label in MARKDOWN_SECTION_LABELS:
        if other_label == label:
            continue
        other = re.compile(r'^-\s*{}\s*$'.format(re.escape(other_label)), re.M).search(section, start)
        if other and other.start() < end:
            end = other.start()
    return markdown_to_plain(section[start:end])


def markdown_api_details():
    details = {}
    root = WIKI / 'docs' / 'mcdocs'
    if not root.exists():
        return details
    for path in root.rglob('*.md'):
        text = path.read_text(encoding='utf-8', errors='replace')
        matches = list(MARKDOWN_API_HEADING_RE.finditer(text))
        for index, match in enumerate(matches):
            name = match.group(1)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = text[match.end():end]
            returns = markdown_section_value(section, u'\u8fd4\u56de\u503c')
            remark = markdown_section_value(section, u'\u5907\u6ce8')
            if returns or remark:
                details.setdefault(name, {'official_return': returns, 'official_note': remark})
    return details


def enrich_mirror_items(items):
    details = markdown_api_details()
    for item in items:
        name = item.get('method') or item.get('name') or ''
        detail = details.get(name)
        if detail:
            item.update(detail)
    return items


def row_for(item):
    name = md_escape(item.get('name'))
    method = md_escape(item.get('method'))
    item_type = md_escape(item.get('type'))
    side = md_escape(item.get('side'))
    description = md_escape(item.get('description'))
    params = md_escape(summarize_params(item.get('params')))
    returns = md_escape(item.get('official_return') or summarize_params(item.get('return')))
    note = md_escape(item.get('official_note') or item.get('remark'))[:1200]
    source = md_escape(item.get('source_url') or item.get('link') or '')
    doc = item.get('local_doc') or local_doc_link(item.get('link') or '')
    doc_cell = '[{}]({})'.format(source, doc) if doc else source
    display = method or name
    entry_anchor = anchor(display)
    return '| <a id="{}"></a>{} | {} | {} | {} | {} | {} | {} | {} | {} |'.format(entry_anchor, item_type, name, method, side, description, params, returns, note, doc_cell)


def write_index(path, title, items, intro):
    lines = ['# {}'.format(title), '', intro, '', 'Total entries: {}'.format(len(items)), '', '| Type | Name | Method | Side | Description | Params | Return | Notes | Source |', '|---|---|---|---|---|---|---|---|---|']
    lines.extend((row_for(item) for item in items))
    lines.append('')
    path.write_text('\n'.join(lines), encoding='utf-8')


def write_search_guide():
    text = '# NetEase ModSDK documentation search guide\n\nSearch `api-index.md`, `interfaces.md`, `events.md`, and `official-api-docs.md` first. Development guides and tutorials are separate optional indexes: `official-development-guides.md` and `official-tutorials.md`. Use them only when the request explicitly requires non-API documentation.\n'
    (REFERENCES / 'search-guide.md').write_text(text, encoding='utf-8')


def canonical_official_url(href, base, allowed_prefixes):
    if not href or href.startswith(('javascript:', 'mailto:', '#')):
        return ''
    parsed = urlparse(urljoin(base, href))
    if parsed.scheme not in ('http', 'https') or parsed.netloc != 'mc.163.com':
        return ''
    path = parsed.path
    if not path.endswith('.html') or not any(path.startswith(prefix) for prefix in allowed_prefixes):
        return ''
    return OFFICIAL_ROOT + path


def selected_prefixes(scopes):
    prefixes = []
    for scope in scopes:
        prefixes.extend(OFFICIAL_SCOPE_PREFIXES[scope])
    return tuple(prefixes)


def selected_seeds(scopes):
    prefixes = selected_prefixes(scopes)
    seeds = []
    for url in OFFICIAL_SEEDS:
        path = urlparse(url).path
        if any(path.startswith(prefix) for prefix in prefixes):
            seeds.append(url)
        elif 'guides' in scopes and 'pageType=2' in url:
            seeds.append(url)
        elif 'tutorials' in scopes and 'pageType=3' in url:
            seeds.append(url)
    return seeds


def official_relative_path(url):
    parsed = urlparse(url)
    path = parsed.path.lstrip('/')
    if parsed.path == '/dev/list.html':
        page_type = re.search(r'(?:^|&)pageType=([^&]+)', parsed.query)
        suffix = page_type.group(1) if page_type else 'unknown'
        return (Path('official') / 'dev' / 'lists' / 'page-type-{}.html'.format(suffix)).as_posix()
    relative = Path('official') / path
    if len(str(REFERENCES / relative)) > 220:
        digest = hashlib.sha1(url.encode('utf-8')).hexdigest()
        return (Path('official') / 'long-paths' / '{}.html'.format(digest)).as_posix()
    return relative.as_posix()


def strip_html(value):
    text = TAG_RE.sub(' ', value)
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return SPACE_RE.sub(' ', text).strip()


def section_description(section):
    match = re.search(r'描述\s*</(?:p|h\d)>\s*<(?:p|div)[^>]*>(.*?)</(?:p|div)>', section, re.I | re.S)
    if match:
        return strip_html(match.group(1))[:500]
    text = strip_html(section)
    return text[:500]


def section_side(section):
    text = strip_html(section[:1200])
    sides = []
    if '服务端' in text:
        sides.append('server')
    if '客户端' in text:
        sides.append('client')
    return '/'.join(sides)


def official_section(url):
    path = urlparse(url).path
    if path.startswith('/dev/mcmanual/mc-dev/mconline/'):
        return 'tutorial'
    if path.startswith('/dev/mcmanual/mc-dev/mcguide/'):
        return 'development_guide'
    if path.startswith('/dev/mcmanual/mc-dev/mcdocs/'):
        return 'api_documentation'
    if path == '/dev/list.html' and 'pageType=3' in url:
        return 'tutorial_listing'
    if path == '/dev/list.html' and 'pageType=2' in url:
        return 'development_guide_listing'
    return 'official_documentation'


def page_title(page):
    match = TITLE_RE.search(page)
    return strip_html(match.group(1)) if match else ''


def extract_official_entries(url, page):
    entries = []
    matches = list(H2_RE.finditer(page))
    for index, match in enumerate(matches):
        attrs = match.group(1)
        anchor_match = ID_RE.search(attrs)
        if not anchor_match:
            continue
        name = re.sub(r'^#\s*', '', strip_html(match.group(2)))
        if not name.endswith('Event'):
            continue
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        section = page[match.end():section_end]
        fragment = anchor_match.group(1)
        entries.append({
            'type': 'event',
            'name': name,
            'method': name,
            'side': section_side(section),
            'description': section_description(section),
            'source_url': '{}#{}'.format(url, fragment),
            'local_doc': official_relative_path(url),
        })
    return entries


def fetch_official_page(url):
    try:
        return url, fetch_bytes(url), ''
    except Exception as exc:
        return url, None, str(exc)


def crawl_official_docs(workers, scopes):
    allowed_prefixes = selected_prefixes(scopes)
    pending = selected_seeds(scopes)
    visited = set()
    entries = []
    documents = []
    errors = []
    downloaded = 0
    pool = ThreadPool(workers)
    try:
        while pending:
            batch = pending[:workers]
            del pending[:workers]
            batch = [url for url in batch if url not in visited]
            for url in batch:
                visited.add(url)
            for url, data, error in pool.map(fetch_official_page, batch):
                if error:
                    errors.append({'url': url, 'error': error})
                    continue
                downloaded += 1
                page = data.decode('utf-8', 'replace')
                output = REFERENCES / official_relative_path(url)
                write_binary(output, data)
                documents.append({
                    'section': official_section(url),
                    'title': page_title(page) or url,
                    'source_url': url,
                    'local_doc': official_relative_path(url),
                })
                if any(urlparse(url).path.startswith(prefix) for prefix in OFFICIAL_API_PREFIXES):
                    entries.extend(extract_official_entries(url, page))
                for href in HREF_RE.findall(page):
                    child = canonical_official_url(href, url, allowed_prefixes)
                    if child and child not in visited and child not in pending:
                        pending.append(child)
            if downloaded % PROGRESS_EVERY == 0 or not pending:
                progress('official progress: downloaded {} pages, discovered {} pages, extracted {} events'.format(downloaded, len(visited) + len(pending), len(entries)))
    finally:
        pool.close()
        pool.join()
    return entries, documents, visited, errors, downloaded


def entry_key(item):
    name = item.get('method') or item.get('name') or ''
    return (str(item.get('type') or '').lower(), str(name).lower())


def normalize_entry_type(item):
    normalized = dict(item)
    source = str(normalized.get('source_url') or normalized.get('link') or '')
    if '/接口/' in source:
        normalized['type'] = 'api'
    elif '/事件/' in source:
        normalized['type'] = 'event'
    return normalized


def merge_entries(official_items, mirror_items):
    merged = []
    seen = set()
    for raw_item in official_items + mirror_items:
        item = normalize_entry_type(raw_item)
        key = entry_key(item)
        if not key[1] or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def write_official_docs_index(path, documents):
    lines = [
        '# NetEase Official Documentation Index',
        '',
        'Current official pages crawled from the API documentation, development-guide, and tutorial navigation trees.',
        '',
        'Total pages: {}'.format(len(documents)),
        '',
        '| Section | Title | Source |',
        '|---|---|---|',
    ]
    for item in sorted(documents, key=lambda value: (value.get('section', ''), value.get('title', ''))):
        source = md_escape(item.get('source_url'))
        local_doc = item.get('local_doc')
        source_cell = '[{}]({})'.format(source, local_doc) if local_doc else source
        lines.append('| {} | {} | {} |'.format(md_escape(item.get('section')), md_escape(item.get('title')), source_cell))
    lines.append('')
    path.write_text('\n'.join(lines), encoding='utf-8')


def download_mirror_path(path):
    try:
        download_one(path)
        return path, ''
    except Exception as exc:
        return path, str(exc)


def download_mirror_docs(workers):
    print('fetching community mirror fallback ...')
    tree = repo_tree()
    paths = sorted((item['path'] for item in tree if item.get('type') == 'blob' and should_download(item.get('path', ''))))
    if not paths:
        raise RuntimeError('no matching files found in mirror tree')
    errors = []
    pool = ThreadPool(workers)
    try:
        for index, result in enumerate(pool.imap_unordered(download_mirror_path, paths), 1):
            path, error = result
            if error:
                errors.append((path, error))
            if index % PROGRESS_EVERY == 0 or index == len(paths):
                progress('mirror progress: downloaded {}/{} files'.format(index, len(paths)))
    finally:
        pool.close()
        pool.join()
    if errors:
        print('{} mirror files failed; continuing with available files'.format(len(errors)), file=sys.stderr)
    raw_path = REFERENCES / 'api-index.mirror.raw.json'
    if not raw_path.exists():
        raise RuntimeError('mirror api-index.json could not be downloaded')
    data = read_json_lenient(raw_path)
    if not isinstance(data, list):
        raise RuntimeError('mirror api-index.json did not contain a list')
    return data, len(paths), errors


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=None, help='External output directory. Defaults to ./mc_bedrock_api_references.')
    parser.add_argument('--scope', action='append', choices=['api', 'guides', 'tutorials', 'all'], help='Official documentation tree to update. Defaults to all; may be repeated for a targeted refresh.')
    parser.add_argument('--skip-mirror', action='store_true', help='Use only the current official site, without the community-mirror fallback.')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help='Concurrent official-page downloads (default: {}).'.format(DEFAULT_WORKERS))
    return parser.parse_args()


def main():
    global REFERENCES, WIKI, OFFICIAL
    args = parse_args()
    if args.out:
        REFERENCES = Path(args.out).resolve()
        WIKI = REFERENCES / 'wiki'
        OFFICIAL = REFERENCES / 'official'
    REFERENCES.mkdir(parents=True, exist_ok=True)
    if args.workers < 1:
        raise SystemExit('--workers must be at least 1')
    scopes = args.scope or ['all']
    if 'all' in scopes:
        scopes = ['api', 'guides', 'tutorials']
    else:
        scopes = list(dict.fromkeys(scopes))

    progress('crawling official {} docs with {} workers ...'.format(', '.join(scopes), args.workers))
    official_items, official_documents, official_pages, official_errors, official_downloaded = crawl_official_docs(args.workers, scopes)
    if 'api' in scopes and not official_items:
        raise RuntimeError('official crawl produced no API events; refusing to build a stale-only index')
    mirror_items = []
    mirror_files = 0
    mirror_errors = []
    if 'api' in scopes and not args.skip_mirror:
        mirror_items, mirror_files, mirror_errors = download_mirror_docs(args.workers)
        mirror_items = enrich_mirror_items(mirror_items)

    if 'api' in scopes:
        api_data = merge_entries(official_items, mirror_items)
        write_binary(REFERENCES / 'api-index.raw.json', json.dumps(api_data, ensure_ascii=False, indent=2).encode('utf-8'))
        events = [item for item in api_data if item.get('type') == 'event']
        interfaces = [item for item in api_data if item.get('type') != 'event']
        write_index(REFERENCES / 'api-index.md', 'NetEase ModSDK API Index', api_data, 'Generated from the current official NetEase docs, with a community mirror fallback for historical entries.')
        write_index(REFERENCES / 'events.md', 'NetEase ModSDK Events', events, 'Event entries from the current official NetEase docs plus historical fallback entries.')
        write_index(REFERENCES / 'interfaces.md', 'NetEase ModSDK Interfaces', interfaces, 'API/interface entries retained from the community-mirror fallback.')
    else:
        api_data = []
        events = []
        interfaces = []
    docs_by_scope = {
        'api': [item for item in official_documents if item.get('section') == 'api_documentation'],
        'guides': [item for item in official_documents if item.get('section', '').startswith('development_guide')],
        'tutorials': [item for item in official_documents if item.get('section', '').startswith('tutorial')],
    }
    doc_index_names = {'api': 'official-api-docs.md', 'guides': 'official-development-guides.md', 'tutorials': 'official-tutorials.md'}
    for scope in scopes:
        write_official_docs_index(REFERENCES / doc_index_names[scope], docs_by_scope[scope])
    if 'api' in scopes:
        api_docs = docs_by_scope['api']
        write_official_docs_index(REFERENCES / 'official-api-interfaces.md', [item for item in api_docs if '/接口/' in item.get('source_url', '')])
        write_official_docs_index(REFERENCES / 'official-api-events.md', [item for item in api_docs if '/事件/' in item.get('source_url', '')])
    write_search_guide()
    report = {
        'official_pages_downloaded': official_downloaded,
        'official_pages_failed': official_errors,
        'official_events': len(official_items),
        'official_documents': len(official_documents),
        'scopes': scopes,
        'mirror_files_attempted': mirror_files,
        'mirror_files_failed': [{'path': path, 'error': error} for path, error in mirror_errors],
        'merged_entries': len(api_data),
    }
    (REFERENCES / 'crawl-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('DONE: crawled {} official pages for {} ({} API entries, {} events)'.format(report['official_pages_downloaded'], ', '.join(scopes), len(api_data), len(events)))
    print('Output: {}'.format(REFERENCES))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
