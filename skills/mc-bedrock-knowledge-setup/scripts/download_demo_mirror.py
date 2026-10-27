#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Download NetEase Minecraft/MCStudio official public demo packages."""
import argparse
import shutil
from compat import Request, urlopen
import zipfile
from pathlib import Path
from compat import urlparse
OFFICIAL_PAGE = 'https://mc.163.com/dev/mcmanual/mc-dev/mcguide/20-%E7%8E%A9%E6%B3%95%E5%BC%80%E5%8F%91/13-%E6%A8%A1%E7%BB%84SDK%E7%BC%96%E7%A8%8B/60-Demo%E7%A4%BA%E4%BE%8B.html'
DEFAULT_URL = 'https://g79.gdl.netease.com/3.8Demo.zip'
PRIVATE_MIRROR_URL = 'https://github.com/Trryer/mc-bedrock-fast-code-private-assets/releases/latest/download/netease-mc-3.8-public-demo-local-mirror.zip'

def download(url, out_file):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    local = Path(url).expanduser()
    if local.exists():
        shutil.copyfile(str(local), str(out_file))
        return
    req = Request(url, headers={'User-Agent': 'mc-bedrock-fast-code-demo-downloader'})
    response = urlopen(req, timeout=300)
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

def default_zip_name(url):
    parsed = urlparse(url)
    if parsed.scheme and parsed.path:
        return Path(parsed.path).name or '3.8Demo.zip'
    return Path(url).name or '3.8Demo.zip'

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=DEFAULT_URL, help='Official demo zip URL or local zip path. Defaults to NetEase official 3.8Demo.zip.')
    parser.add_argument('--private-mirror', action='store_true', help='Use the private GitHub backup mirror instead of the official URL. Requires repository access.')
    parser.add_argument('--out', default='./mc-bedrock-official-public-demos', help='Output folder for extracted demos.')
    parser.add_argument('--zip', default=None, help='Downloaded zip path. Defaults to <out>/<source zip name>.')
    parser.add_argument('--no-extract', action='store_true', help='Only download the zip.')
    return parser.parse_args()

def main():
    args = parse_args()
    url = PRIVATE_MIRROR_URL if args.private_mirror else args.url
    out_dir = Path(args.out).expanduser().resolve()
    zip_path = Path(args.zip).expanduser().resolve() if args.zip else out_dir / default_zip_name(url)
    print('Source note: NetEase Minecraft/MCStudio official public demo material.')
    print('Official page: {}'.format(OFFICIAL_PAGE))
    print('Download URL: {}'.format(url))
    if args.private_mirror:
        print('Private mirror note: this is only a personal backup of the official public package and may require GitHub access.')
    print('Use the demo materials only under their original official terms.')
    download(url, zip_path)
    print('Downloaded: {}'.format(zip_path))
    if not args.no_extract:
        extract(zip_path, out_dir)
        print('Extracted: {}'.format(out_dir))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
