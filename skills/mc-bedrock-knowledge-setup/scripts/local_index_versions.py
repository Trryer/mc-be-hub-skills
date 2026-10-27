#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Discover MCStudio MinecraftPE_Netease versions and build indexes for each data folder."""
import argparse
import json
import os
import platform
import subprocess
from compat import run_command
import sys
from compat import utcnow_iso
from pathlib import Path

def default_search_roots():
    roots = []
    for env_name in ('USERPROFILE', 'PROGRAMDATA', 'LOCALAPPDATA', 'APPDATA'):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))
    for drive in ('C:/', 'D:/', 'E:/', 'F:/'):
        root = Path(drive)
        if root.exists():
            roots.append(root)
    unique = []
    seen = set()
    for root in roots:
        resolved = str(root.resolve()).lower()
        if resolved not in seen:
            unique.append(root)
            seen.add(resolved)
    return unique

def find_mc_roots(search_roots, exhaustive):
    matches = []
    wanted_tail = Path('MCStudioDownload') / 'game' / 'MinecraftPE_Netease'
    if platform.system().lower() != 'windows':
        return matches
    for root in search_roots:
        if not root.exists():
            continue
        direct = root / wanted_tail
        if direct.is_dir():
            matches.append(direct)
        if exhaustive:
            try:
                for candidate in root.rglob('MinecraftPE_Netease'):
                    if candidate.is_dir() and candidate.parent.name == 'game' and (candidate.parent.parent.name == 'MCStudioDownload'):
                        matches.append(candidate)
            except OSError:
                continue
    return sorted(set((path.resolve() for path in matches)), key=lambda p: str(p).lower())

def version_dirs_from_mc_root(mc_root):
    if not mc_root.is_dir():
        return []
    versions = []
    for child in mc_root.iterdir():
        if child.is_dir() and (child / 'data').is_dir():
            versions.append(child)
    if (mc_root / 'data').is_dir():
        versions.append(mc_root)
    return sorted(set((path.resolve() for path in versions)), key=lambda p: p.name.lower())

def run_builder(builder, version_dir, out_root, pretty):
    data_root = version_dir / 'data'
    out_dir = out_root / version_dir.name
    cmd = [sys.executable, str(builder), '--data-root', str(data_root), '--out', str(out_dir)]
    if pretty:
        cmd.append('--pretty')
    started = utcnow_iso()
    proc = run_command(cmd)
    return {'version_dir': str(version_dir), 'data_root': str(data_root), 'out_dir': str(out_dir), 'started_at': started, 'returncode': proc.returncode, 'stdout': proc.stdout.strip(), 'stderr': proc.stderr.strip()}

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mc-root', action='append', default=[], help='MinecraftPE_Netease root containing version folders. May be repeated.')
    parser.add_argument('--version-dir', action='append', default=[], help='Specific version directory containing data/. May be repeated.')
    parser.add_argument('--search-root', action='append', default=[], help='Root to search for */MCStudioDownload/game/MinecraftPE_Netease. Windows only.')
    parser.add_argument('--exhaustive-search', action='store_true', help='Recursively search roots. Can be slow on large drives.')
    parser.add_argument('--out-root', required=True, help='Output root. Each version gets its own subdirectory.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print each generated index.json.')
    parser.add_argument('--list-only', action='store_true', help='Only print discovered version directories.')
    return parser.parse_args()

def main():
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    builder = script_dir / 'local_build_index.py'
    out_root = Path(args.out_root).resolve()
    version_dirs = [Path(p).resolve() for p in args.version_dir]
    mc_roots = [Path(p).resolve() for p in args.mc_root]
    should_auto_discover = not args.version_dir and (not args.mc_root)
    if args.search_root or should_auto_discover:
        search_roots = [Path(p).resolve() for p in args.search_root] or default_search_roots()
        mc_roots.extend(find_mc_roots(search_roots, args.exhaustive_search))
    for mc_root in mc_roots:
        version_dirs.extend(version_dirs_from_mc_root(mc_root))
    version_dirs = sorted(set((v for v in version_dirs if (v / 'data').is_dir())), key=lambda p: str(p).lower())
    if not version_dirs:
        message = 'No MinecraftPE_Netease version directories with data/ were found. Pass --mc-root <.../MCStudioDownload/game/MinecraftPE_Netease> or --version-dir <version-folder>.'
        raise SystemExit(message)
    if args.list_only:
        for version in version_dirs:
            print(version)
        return
    out_root.mkdir(parents=True, exist_ok=True)
    results = [run_builder(builder, version, out_root, args.pretty) for version in version_dirs]
    manifest = {'generated_at': utcnow_iso(), 'versions': results}
    (out_root / 'versions_index_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    for result in results:
        status = 'OK' if result['returncode'] == 0 else 'FAIL'
        print('{} {} -> {}'.format(status, result['version_dir'], result['out_dir']))
        if result['stdout']:
            print(result['stdout'])
        if result['stderr']:
            print(result['stderr'], file=sys.stderr)
    if any((result['returncode'] != 0 for result in results)):
        raise SystemExit(1)
if __name__ == '__main__':
    main()
