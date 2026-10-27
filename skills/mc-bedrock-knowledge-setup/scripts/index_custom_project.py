#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Build a private local style/content index from a user-authorized ModSDK project."""

import argparse
import json
import os
from compat import try_load_json, utcnow_iso
from pathlib import Path

TEXT_SUFFIXES = set(['.py', '.json', '.lang', '.mcgui', '.material', '.txt', '.md'])


def read_sample(path, limit=1200):
    try:
        return path.read_bytes()[:limit].decode('utf-8', 'replace')
    except Exception:
        return ''


def summarize_json(data):
    summary = {}
    if not isinstance(data, dict):
        return summary
    summary['top_keys'] = sorted([str(k) for k in data.keys()])[:20]
    for key in ('minecraft:entity', 'minecraft:client_entity', 'minecraft:item', 'minecraft:block'):
        node = data.get(key)
        if isinstance(node, dict):
            desc = node.get('description')
            summary['minecraft_type'] = key
            if isinstance(desc, dict) and desc.get('identifier'):
                summary['identifier'] = desc.get('identifier')
            break
    if 'format_version' in data:
        summary['format_version'] = data.get('format_version')
    return summary


def parse_lang(path):
    entries = []
    text = read_sample(path, limit=200000)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        entries.append({'key': key.strip(), 'value': value.strip()})
    return entries[:2000]


def category(path):
    parts = set(path.parts)
    suffix = path.suffix.lower()
    if path.name == 'zh_CN.lang':
        return 'lang_zh_cn'
    if suffix == '.lang':
        return 'lang'
    if suffix == '.py':
        return 'script'
    if 'ui' in parts or suffix == '.mcgui':
        return 'ui'
    if 'entities' in parts:
        return 'entity_behavior'
    if 'entity' in parts:
        return 'entity_resource'
    if 'netease_items_beh' in parts:
        return 'item_behavior'
    if 'netease_items_res' in parts:
        return 'item_resource'
    if 'netease_blocks' in parts:
        return 'block_behavior'
    if path.name == 'blocks.json' or 'netease_block' in parts:
        return 'block_resource'
    if 'animation_controllers' in parts:
        return 'animation_controller'
    if 'render_controllers' in parts:
        return 'render_controller'
    return suffix.lstrip('.') or 'file'


def scan_project(project):
    records = []
    for path in sorted(project.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(project)
        rec = {
            'path': rel.as_posix(),
            'category': category(rel),
            'suffix': path.suffix.lower(),
            'sample': read_sample(path),
        }
        if path.suffix.lower() == '.json':
            data = try_load_json(path)
            if data is not None:
                rec['json'] = summarize_json(data)
        if path.name == 'zh_CN.lang':
            rec['lang_entries'] = parse_lang(path)
        records.append(rec)
    return records


def update_registry(registry_path, root, index_path, project, repo, name):
    data = {}
    if registry_path.exists():
        loaded = try_load_json(registry_path)
        if isinstance(loaded, dict):
            data = loaded
    data.setdefault('root', str(root))
    entry = {
        'name': name,
        'project': str(project),
        'repo': repo or '',
        'index': str(index_path),
        'priority': 'custom_local',
        'updated_at': utcnow_iso(),
    }
    indexes = [item for item in data.get('custom_project_indexes', []) if item.get('name') != name]
    indexes.insert(0, entry)
    data['custom_project_indexes'] = indexes
    data['updated_at'] = utcnow_iso()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='User-authorized project/mod directory.')
    parser.add_argument('--root', default=str(Path.home() / '.codex' / 'mc-bedrock-fast-code-data'), help='External knowledge root.')
    parser.add_argument('--registry', help='Registry JSON path. Defaults to <root>/knowledge_registry.json.')
    parser.add_argument('--out', help='Output directory. Defaults to <root>/custom_project_indexes/<name>.')
    parser.add_argument('--name', help='Stable local index name. Defaults to project folder name.')
    parser.add_argument('--repo', help='Optional repository URL/path to remember for future skill updates.')
    parser.add_argument('--pretty', action='store_true')
    return parser.parse_args()


def main():
    args = parse_args()
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise SystemExit('project is not a directory: {}'.format(project))
    root = Path(args.root).expanduser().resolve()
    name = args.name or project.name
    out = Path(args.out).expanduser().resolve() if args.out else root / 'custom_project_indexes' / name
    registry_path = Path(args.registry).expanduser().resolve() if args.registry else root / 'knowledge_registry.json'
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / 'custom_index.json'
    index = {
        'kind': 'custom_project_index',
        'privacy': 'local_only',
        'name': name,
        'project': str(project),
        'repo': args.repo or '',
        'generated_at': utcnow_iso(),
        'records': scan_project(project),
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2 if args.pretty else None) + '\n', encoding='utf-8')
    update_registry(registry_path, root, index_path, project, args.repo, name)
    print('Wrote custom local index: {}'.format(index_path))
    print('Registry: {}'.format(registry_path))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
