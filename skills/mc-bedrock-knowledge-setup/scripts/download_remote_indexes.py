#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Download optional lightweight remote indexes for mc-bedrock-fast-code."""
import argparse
import json
from compat import Request, urlopen
import zipfile
import shutil
from compat import utcnow_iso
from pathlib import Path
DEFAULT_URL = 'https://github.com/Trryer/mc-be-hub-skills/releases/latest/download/mc-bedrock-fast-code-public-index.zip'

def download(url, out_file):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    local = Path(url).expanduser()
    if local.exists():
        shutil.copyfile(str(local), str(out_file))
        return
    req = Request(url, headers={'User-Agent': 'mc-bedrock-fast-code-index-downloader'})
    response = urlopen(req, timeout=120)
    try:
        out_file.write_bytes(response.read())
    finally:
        response.close()

def extract(zip_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path)) as zf:
        for info in zf.infolist():
            target = (out_dir / info.filename).resolve()
            if not str(target).startswith(str(out_dir.resolve())):
                raise RuntimeError('unsafe zip member: {}'.format(info.filename))
        zf.extractall(str(out_dir))

def update_registry(registry_path, root, remote_dir, url):
    data = {}
    if registry_path.exists():
        try:
            loaded = json.loads(registry_path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    data.setdefault('root', str(root))
    data['remote_public_indexes'] = str(remote_dir)
    data['remote_public_index_url'] = url
    data['updated_at'] = utcnow_iso()
    data.setdefault('runs', []).append({'kind': 'remote_public_indexes', 'url': url, 'out': str(remote_dir), 'generated_at': utcnow_iso()})
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path.home() / '.codex' / 'mc-bedrock-fast-code-data'), help='External knowledge root.')
    parser.add_argument('--registry', help='Registry JSON path. Defaults to <root>/knowledge_registry.json.')
    parser.add_argument('--url', default=DEFAULT_URL, help='Zip URL for lightweight public indexes.')
    parser.add_argument('--out', help='Output directory. Defaults to <root>/remote_public_indexes.')
    parser.add_argument('--zip', help='Downloaded zip path. Defaults to <root>/downloads/public-index.zip.')
    parser.add_argument('--no-extract', action='store_true', help='Only download the zip.')
    return parser.parse_args()

def main():
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    registry_path = Path(args.registry).expanduser().resolve() if args.registry else root / 'knowledge_registry.json'
    out_dir = Path(args.out).expanduser().resolve() if args.out else root / 'remote_public_indexes'
    zip_path = Path(args.zip).expanduser().resolve() if args.zip else root / 'downloads' / 'public-index.zip'
    download(args.url, zip_path)
    print('Downloaded: {}'.format(zip_path))
    if not args.no_extract:
        extract(zip_path, out_dir)
        print('Extracted: {}'.format(out_dir))
        update_registry(registry_path, root, out_dir, args.url)
        print('Registry: {}'.format(registry_path))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
