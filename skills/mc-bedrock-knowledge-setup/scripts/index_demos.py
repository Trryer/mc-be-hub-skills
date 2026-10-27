#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Index NetEase Minecraft Bedrock official demo packs without copying assets."""
import argparse
import json
import os
from collections import Counter, defaultdict
from compat import utcnow_iso, try_load_json
from pathlib import Path
TEXT_SUFFIXES = {'.json', '.mcgui', '.py', '.md', '.lang', '.material', '.txt'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.tga'}
MODEL_SUFFIXES = {'.bbmodel', '.blend', '.fbx', '.max'}
CATEGORY_RULES = [('ui', lambda p: 'ui' in p.parts or p.suffix == '.mcgui'), ('script', lambda p: p.suffix == '.py' or any((part.endswith('Scripts') or part == 'script' for part in p.parts))), ('manifest', lambda p: p.name in {'manifest.json', 'pack_manifest.json', 'studio.json'}), ('entity_behavior', lambda p: 'entities' in p.parts and p.suffix == '.json'), ('entity_resource', lambda p: 'entity' in p.parts and p.suffix == '.json'), ('item_behavior', lambda p: 'netease_items_beh' in p.parts), ('item_resource', lambda p: 'netease_items_res' in p.parts), ('block_behavior', lambda p: 'netease_blocks' in p.parts), ('block_resource', lambda p: p.name == 'blocks.json' or 'netease_block' in p.parts), ('animation', lambda p: 'animations' in p.parts or 'animation' in p.name), ('animation_controller', lambda p: 'animation_controllers' in p.parts), ('render_controller', lambda p: 'render_controllers' in p.parts), ('model', lambda p: 'models' in p.parts or p.suffix.lower() in MODEL_SUFFIXES), ('texture', lambda p: 'textures' in p.parts or p.suffix.lower() in IMAGE_SUFFIXES), ('particle', lambda p: 'particles' in p.parts), ('sound', lambda p: 'sounds' in p.parts or p.suffix == '.ogg'), ('material_shader', lambda p: 'materials' in p.parts or 'shaders' in p.parts or p.suffix == '.material'), ('world_pack_link', lambda p: p.name.startswith('world_') and p.name.endswith('_packs.json'))]

def read_text_sample(path, limit=600):
    try:
        return path.read_bytes()[:limit].decode('utf-8', 'replace')
    except OSError:
        return ''

def load_json(path):
    return try_load_json(path)

def category_for(rel):
    for name, pred in CATEGORY_RULES:
        if pred(rel):
            return name
    return 'asset' if rel.suffix.lower() in IMAGE_SUFFIXES | MODEL_SUFFIXES else 'other'

def infer_demo_name(source, file_path):
    rel = file_path.relative_to(source)
    return rel.parts[0] if len(rel.parts) > 1 else source.name

def summarize_json(path, data):
    summary = {}
    if isinstance(data, dict):
        summary['top_keys'] = sorted((str(k) for k in data.keys()))[:20]
        desc = None
        for key in ('minecraft:entity', 'minecraft:client_entity', 'minecraft:item', 'minecraft:block'):
            node = data.get(key)
            if isinstance(node, dict):
                desc = node.get('description')
                summary['minecraft_type'] = key
                break
        if isinstance(desc, dict):
            identifier = desc.get('identifier')
            if identifier:
                summary['identifier'] = identifier
            for key in ('category', 'is_spawnable', 'is_summonable'):
                if key in desc:
                    summary[key] = desc[key]
        if 'format_version' in data:
            summary['format_version'] = data['format_version']
        if 'ui_defs' in data:
            summary['ui_defs_count'] = len(data.get('ui_defs') or [])
    return summary

def scan_source(source):
    records = []
    counters = Counter()
    by_demo = defaultdict(Counter)
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        cat = category_for(rel)
        demo = infer_demo_name(source, path)
        counters[cat] += 1
        by_demo[demo][cat] += 1
        rec = {'source_root': str(source), 'demo': demo, 'path': rel.as_posix(), 'category': cat, 'suffix': path.suffix.lower(), 'size': path.stat().st_size}
        if path.suffix.lower() in TEXT_SUFFIXES:
            rec['sample'] = read_text_sample(path)
        if path.suffix.lower() == '.json':
            data = load_json(path)
            if data is not None:
                rec['json'] = summarize_json(path, data)
        records.append(rec)
    summary = {'source_root': str(source), 'total_files': len(records), 'categories': dict(sorted(counters.items())), 'demos': {name: dict(sorted(counter.items())) for name, counter in sorted(by_demo.items())}}
    return (records, summary)

def write_markdown(out, summaries, records):
    lines = ['# MC Bedrock Demo Index', '', 'Generated at: {}'.format(utcnow_iso()), '']
    for summary in summaries:
        lines.append('## {}'.format(summary['source_root']))
        lines.append('')
        lines.append('Total files: {}'.format(summary['total_files']))
        lines.append('')
        lines.append('| Category | Count |')
        lines.append('|---|---:|')
        for cat, count in summary['categories'].items():
            lines.append('| {} | {} |'.format(cat, count))
        lines.append('')
    lines.append('## Useful Examples')
    lines.append('')
    lines.append('| Category | Demo | Path | Identifier |')
    lines.append('|---|---|---|---|')
    priority = {'entity_behavior', 'entity_resource', 'item_behavior', 'item_resource', 'block_behavior', 'block_resource', 'ui', 'script', 'animation_controller', 'render_controller'}
    for rec in records:
        if rec['category'] not in priority:
            continue
        meta = rec.get('json') if isinstance(rec.get('json'), dict) else {}
        identifier = meta.get('identifier', '') if isinstance(meta, dict) else ''
        lines.append('| {} | {} | {} | {} |'.format(rec['category'], rec['demo'], rec['path'], identifier))
    lines.append('')
    (out / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', required=True, help='Demo root such as 6-1DemoMod. May be repeated.')
    parser.add_argument('--out', required=True, help='External output directory for the generated demo index.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print index JSON.')
    return parser.parse_args()

def main():
    args = parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    all_records = []
    summaries = []
    for raw in args.source:
        source = Path(raw).resolve()
        if not source.is_dir():
            raise SystemExit('source is not a directory: {}'.format(source))
        records, summary = scan_source(source)
        all_records.extend(records)
        summaries.append(summary)
    index = {'generated_at': utcnow_iso(), 'sources': summaries, 'records': all_records}
    indent = 2 if args.pretty else None
    (out / 'demo_index.json').write_text(json.dumps(index, ensure_ascii=False, indent=indent), encoding='utf-8')
    write_markdown(out, summaries, all_records)
    print('Wrote {} demo records to {}'.format(len(all_records), out))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
