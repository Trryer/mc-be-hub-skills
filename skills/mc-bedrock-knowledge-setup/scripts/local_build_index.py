#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Build a searchable index for Minecraft Bedrock vanilla data directories."""
import argparse
import fnmatch
import json
import re
from collections import Counter, defaultdict
from compat import utcnow_iso
from pathlib import Path
SCHEMA_VERSION = '1.0.0'
REF_KEYS = {'animations': 'animation', 'animation': 'animation', 'animation_controllers': 'animation_controller', 'animation_controller': 'animation_controller', 'render_controllers': 'render_controller', 'render_controller': 'render_controller', 'geometry': 'geometry', 'materials': 'material', 'material': 'material', 'textures': 'texture', 'texture': 'texture', 'sounds': 'sound', 'sound': 'sound', 'table': 'loot_table', 'loot': 'loot_table', 'event': 'event', 'events': 'event', 'item': 'item', 'items': 'item', 'identifier': 'identifier', 'entity': 'entity', 'entities': 'entity', 'component_groups': 'component_group', 'spawn_egg': 'texture', 'icon': 'texture'}
PATH_REF_RE = re.compile('^(?:textures|sounds|models|geometry|materials|loot_tables|recipes|animations|animation_controllers|render_controllers|particles|ui|font)/')
ASSET_ID_RE = re.compile('^(?:minecraft:[\\w./:-]+|animation\\.[\\w.:-]+|controller\\.(?:animation|render)\\.[\\w.:-]+|geometry\\.[\\w.:-]+|material\\.[\\w.:-]+|particle\\.[\\w.:-]+)$')

def strip_jsonc(text):
    """Remove comments and trailing commas while preserving quoted strings."""
    out = []
    i = 0
    in_string = False
    quote = ''
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and nxt == '/':
            i += 2
            while i < len(text) and text[i] not in '\r\n':
                i += 1
            continue
        if ch == '/' and nxt == '*':
            i += 2
            while i + 1 < len(text) and (not (text[i] == '*' and text[i + 1] == '/')):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = ''.join(out)
    return re.sub(',\\s*([}\\]])', '\\1', cleaned)

def load_jsonc(path):
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(strip_jsonc(text))

def rel(path, root):
    return path.relative_to(root).as_posix()

def normalize_values(value):
    values = []
    if isinstance(value, str):
        if value:
            values.append(value)
    elif isinstance(value, dict):
        for key in ('name', 'path', 'texture', 'event', 'item', 'identifier'):
            if isinstance(value.get(key), str):
                values.append(value[key])
        for child in value.values():
            values.extend(normalize_values(child))
    elif isinstance(value, list):
        for item in value:
            values.extend(normalize_values(item))
    return values

def add_ref(refs, kind, value):
    for item in normalize_values(value):
        refs[kind].add(item)

def walk_refs(obj, refs, key_hint=None):
    if isinstance(obj, dict):
        for key, value in obj.items():
            ref_kind = REF_KEYS.get(key)
            if ref_kind:
                add_ref(refs, ref_kind, value)
            walk_refs(value, refs, key)
    elif isinstance(obj, list):
        for item in obj:
            walk_refs(item, refs, key_hint)
    elif isinstance(obj, str):
        if key_hint and key_hint in REF_KEYS:
            refs[REF_KEYS[key_hint]].add(obj)
        elif PATH_REF_RE.match(obj):
            refs[obj.split('/', 1)[0].rstrip('s')].add(obj)
        elif ASSET_ID_RE.match(obj):
            if obj.startswith('animation.'):
                refs['animation'].add(obj)
            elif obj.startswith('controller.animation.'):
                refs['animation_controller'].add(obj)
            elif obj.startswith('controller.render.'):
                refs['render_controller'].add(obj)
            elif obj.startswith('geometry.'):
                refs['geometry'].add(obj)
            elif obj.startswith('minecraft:'):
                refs['minecraft_identifier'].add(obj)

def extract_components(section):
    components = set()
    if isinstance(section, dict):
        comps = section.get('components')
        if isinstance(comps, dict):
            components.update((k for k in comps if isinstance(k, str)))
        groups = section.get('component_groups')
        if isinstance(groups, dict):
            for group_name, group in groups.items():
                if isinstance(group_name, str):
                    components.add(group_name)
                if isinstance(group, dict):
                    components.update((k for k in group if isinstance(k, str) and k.startswith('minecraft:')))
    return components

def get_pack(path, data_root):
    parts = path.relative_to(data_root).parts
    if not parts:
        return ('data', 'data')
    if parts[0] == 'behavior_packs' and len(parts) > 1:
        return ('behavior_pack', parts[1])
    if parts[0] == 'resource_packs' and len(parts) > 1:
        return ('resource_pack', parts[1])
    if parts[0] == 'definitions':
        return ('definitions', 'definitions')
    return ('data', parts[0])

def infer_kind(path, data_root, data, local_key=None):
    relative = rel(path, data_root)
    parts = relative.split('/')
    folder = parts[2] if len(parts) > 2 and parts[0] in {'behavior_packs', 'resource_packs'} else parts[1] if parts[0] == 'definitions' and len(parts) > 1 else ''
    if isinstance(data, dict):
        if 'minecraft:entity' in data:
            return 'behavior_entity'
        if 'minecraft:client_entity' in data:
            return 'client_entity'
        if 'minecraft:item' in data:
            if parts[0] == 'behavior_packs':
                return 'behavior_item'
            return 'client_item'
        if 'minecraft:attachable' in data:
            return 'attachable'
        if 'animations' in data:
            return 'animation'
        if 'animation_controllers' in data:
            return 'animation_controller'
        if 'render_controllers' in data:
            return 'render_controller'
        if 'minecraft:geometry' in data or 'minecraft:geometry' in str(data.keys()):
            return 'geometry'
        if 'particle_effect' in data:
            return 'particle'
        if 'sound_definitions' in data:
            return 'sound_definition'
        if 'texture_data' in data:
            return 'texture_atlas'
        if 'minecraft:recipe_shaped' in data or 'minecraft:recipe_shapeless' in data or 'minecraft:recipe_furnace' in data or ('minecraft:recipe_brewing_mix' in data):
            return 'recipe'
        if 'minecraft:biome' in data:
            return 'biome'
        if 'minecraft:feature_rules' in data:
            return 'feature_rule'
        if any((k.startswith('minecraft:') and 'feature' in k for k in data)):
            return 'feature'
        if 'minecraft:spawn_rules' in data:
            return 'spawn_rule'
    folder_map = {'entities': 'behavior_entity', 'entity': 'client_entity', 'items': 'item', 'recipes': 'recipe', 'loot_tables': 'loot_table', 'trading': 'trading', 'biomes': 'biome', 'spawn_rules': 'spawn_rule', 'feature_rules': 'feature_rule', 'features': 'feature', 'behavior_trees': 'behavior_tree', 'cameras': 'camera', 'animations': 'animation', 'animation_controllers': 'animation_controller', 'render_controllers': 'render_controller', 'models': 'geometry', 'materials': 'material', 'particles': 'particle', 'textures': 'texture', 'sounds': 'sound', 'ui': 'ui', 'font': 'font', 'fogs': 'fog', 'lighting': 'lighting', 'attachables': 'attachable', 'persona': 'persona', 'spawn_groups': 'spawn_group', 'sdl_layouts': 'sdl_layout'}
    return folder_map.get(folder, 'generic_json')

def description_of(data, root_key):
    if isinstance(data, dict) and isinstance(data.get(root_key), dict):
        desc = data[root_key].get('description')
        if isinstance(desc, dict):
            return desc
    return {}

def make_record(data_root, path, data, kind, pack_type, pack_name, name=None, identifier=None, payload=None):
    relative = rel(path, data_root)
    payload = data if payload is None else payload
    refs = defaultdict(set)
    walk_refs(payload, refs)
    components = extract_components(payload)
    tags = set()
    parts = relative.split('/')
    tags.update(parts[:min(len(parts), 4)])
    if kind:
        tags.add(kind)
    if pack_name:
        tags.add(pack_name)
    if isinstance(payload, dict):
        desc = payload.get('description') if isinstance(payload.get('description'), dict) else None
        if desc:
            for key in ('category', 'spawn_category'):
                if isinstance(desc.get(key), str):
                    tags.add(desc[key])
    clean_refs = {k: sorted(v) for k, v in sorted(refs.items()) if v}
    local = name or identifier or path.stem
    record_id = '{}:{}/{}:{}#{}'.format(kind, pack_type, pack_name, relative, local)
    return {'id': record_id, 'kind': kind, 'pack_type': pack_type, 'pack_name': pack_name, 'relative_path': relative, 'format_version': data.get('format_version') if isinstance(data, dict) else None, 'identifier': identifier, 'name': name or path.stem, 'components': sorted(components), 'references': clean_refs, 'tags': sorted((t for t in tags if t))}

def split_records(data_root, path, data):
    pack_type, pack_name = get_pack(path, data_root)
    records = []
    if not isinstance(data, dict):
        return [make_record(data_root, path, data, 'generic_json', pack_type, pack_name)]
    for root_key, kind in (('minecraft:entity', 'behavior_entity'), ('minecraft:client_entity', 'client_entity'), ('minecraft:item', 'behavior_item' if pack_type == 'behavior_pack' else 'client_item'), ('minecraft:attachable', 'attachable')):
        if root_key in data:
            desc = description_of(data, root_key)
            records.append(make_record(data_root, path, data, kind, pack_type, pack_name, identifier=desc.get('identifier') if isinstance(desc.get('identifier'), str) else None, name=desc.get('identifier') if isinstance(desc.get('identifier'), str) else None, payload=data[root_key]))
            return records
    multi_maps = {'animations': 'animation', 'animation_controllers': 'animation_controller', 'render_controllers': 'render_controller', 'sound_definitions': 'sound_definition', 'texture_data': 'texture_atlas'}
    for key, kind in multi_maps.items():
        if isinstance(data.get(key), dict):
            for local_name, payload in data[key].items():
                records.append(make_record(data_root, path, data, kind, pack_type, pack_name, name=str(local_name), payload={local_name: payload}))
            return records
    if 'minecraft:geometry' in data and isinstance(data['minecraft:geometry'], list):
        for item in data['minecraft:geometry']:
            desc = item.get('description') if isinstance(item, dict) else None
            identifier = desc.get('identifier') if isinstance(desc, dict) and isinstance(desc.get('identifier'), str) else None
            records.append(make_record(data_root, path, data, 'geometry', pack_type, pack_name, identifier=identifier, name=identifier, payload=item))
        return records or [make_record(data_root, path, data, 'geometry', pack_type, pack_name)]
    old_geometry_keys = [key for key in data if isinstance(key, str) and key.startswith('geometry.')]
    if old_geometry_keys:
        for key in old_geometry_keys:
            records.append(make_record(data_root, path, data, 'geometry', pack_type, pack_name, identifier=key, name=key, payload={key: data[key]}))
        return records
    kind = infer_kind(path, data_root, data)
    identifier = None
    name = None
    for root_key in data:
        if root_key.startswith('minecraft:') and isinstance(data[root_key], dict):
            desc = data[root_key].get('description')
            if isinstance(desc, dict) and isinstance(desc.get('identifier'), str):
                identifier = desc['identifier']
                name = identifier
                break
    records.append(make_record(data_root, path, data, kind, pack_type, pack_name, identifier=identifier, name=name))
    return records

def should_include_pack(pack_name, includes, excludes):
    included = any((fnmatch.fnmatch(pack_name, pattern) for pattern in includes))
    excluded = any((pattern and fnmatch.fnmatch(pack_name, pattern) for pattern in excludes))
    return included and (not excluded)

def collect_pack_meta(data_root, includes, excludes):
    packs = {}
    for pack_root, pack_type in ((data_root / 'behavior_packs', 'behavior_pack'), (data_root / 'resource_packs', 'resource_pack')):
        if not pack_root.exists():
            continue
        for pack in sorted((p for p in pack_root.iterdir() if p.is_dir())):
            if not should_include_pack(pack.name, includes, excludes):
                continue
            manifest = pack / 'manifest.json'
            meta = {'pack_type': pack_type, 'pack_name': pack.name, 'relative_path': rel(pack, data_root), 'manifest': None}
            if manifest.exists():
                try:
                    doc = load_jsonc(manifest)
                    header = doc.get('header', {}) if isinstance(doc, dict) else {}
                    meta['manifest'] = {'name': header.get('name'), 'description': header.get('description'), 'uuid': header.get('uuid'), 'version': header.get('version'), 'min_engine_version': header.get('min_engine_version')}
                except Exception as exc:
                    meta['manifest_error'] = str(exc)
            packs['{}/{}'.format(pack_type, pack.name)] = meta
    if (data_root / 'definitions').exists():
        packs['definitions/definitions'] = {'pack_type': 'definitions', 'pack_name': 'definitions', 'relative_path': 'definitions', 'manifest': None}
    return packs

def build_reverse(records):
    reverse = {'by_identifier': defaultdict(set), 'by_component': defaultdict(set), 'by_reference': defaultdict(set), 'by_path': defaultdict(set), 'by_name': defaultdict(set)}
    for record in records:
        rid = record['id']
        if record.get('identifier'):
            reverse['by_identifier'][record['identifier']].add(rid)
        if record.get('name'):
            reverse['by_name'][record['name']].add(rid)
        reverse['by_path'][record['relative_path']].add(rid)
        for component in record.get('components', []):
            reverse['by_component'][component].add(rid)
        for values in record.get('references', {}).values():
            for value in values:
                reverse['by_reference'][value].add(rid)
    return {section: {key: sorted(vals) for key, vals in sorted(mapping.items())} for section, mapping in reverse.items()}

def markdown_table(headers, rows):
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(('---' for _ in headers)) + ' |']
    for row in rows:
        lines.append('| ' + ' | '.join((str(cell).replace('|', '\\|') for cell in row)) + ' |')
    return '\n'.join(lines) + '\n'

def write_markdown(out, index):
    records = index['records']
    stats = index['stats']
    summary_rows = [[k, v] for k, v in sorted(stats['by_kind'].items())]
    pack_rows = [[k, v] for k, v in sorted(stats['by_pack'].items())]
    (out / 'summary.md').write_text('# Bedrock Vanilla Index Summary\n\n- Data root: `{}`\n- Generated at: `{}`\n- JSON files scanned: `{}`\n- Records: `{}`\n- Parse errors: `{}`\n\n## Records by Kind\n\n'.format(index['data_root'], index['generated_at'], stats['json_files_scanned'], stats['records'], stats['errors']) + markdown_table(['Kind', 'Count'], summary_rows) + '\n## Records by Pack\n\n' + markdown_table(['Pack', 'Count'], pack_rows), encoding='utf-8')

    def filtered(kinds):
        return [r for r in records if r['kind'] in kinds]
    entity_rows = [[r.get('identifier') or r.get('name'), r['kind'], r['pack_name'], r['relative_path'], ', '.join(r.get('components', [])[:8])] for r in filtered({'behavior_entity', 'client_entity'})]
    (out / 'entities.md').write_text('# Entities\n\n' + markdown_table(['Identifier/Name', 'Kind', 'Pack', 'Path', 'Components'], entity_rows), encoding='utf-8')
    item_rows = [[r.get('identifier') or r.get('name'), r['kind'], r['pack_name'], r['relative_path'], ', '.join(r.get('components', [])[:8])] for r in filtered({'behavior_item', 'client_item', 'item'})]
    (out / 'items.md').write_text('# Items\n\n' + markdown_table(['Identifier/Name', 'Kind', 'Pack', 'Path', 'Components'], item_rows), encoding='utf-8')
    animation_rows = [[r.get('name'), r['kind'], r['pack_name'], r['relative_path']] for r in filtered({'animation', 'animation_controller'})]
    (out / 'animations.md').write_text('# Animations\n\n' + markdown_table(['Name', 'Kind', 'Pack', 'Path'], animation_rows), encoding='utf-8')
    rendering_rows = [[r.get('name') or r.get('identifier'), r['kind'], r['pack_name'], r['relative_path']] for r in filtered({'render_controller', 'geometry', 'material', 'texture_atlas', 'particle', 'client_entity', 'attachable'})]
    (out / 'rendering.md').write_text('# Rendering\n\n' + markdown_table(['Name', 'Kind', 'Pack', 'Path'], rendering_rows), encoding='utf-8')
    component_rows = []
    by_component = index['reverse_index']['by_component']
    for component, ids in sorted(by_component.items()):
        component_rows.append([component, len(ids), '; '.join(ids[:5])])
    (out / 'components.md').write_text('# Components\n\n' + markdown_table(['Component', 'Uses', 'Sample Records'], component_rows), encoding='utf-8')

def build_index(args):
    data_root = Path(args.data_root).resolve()
    if not data_root.exists() or not data_root.is_dir():
        raise SystemExit('data root is not a directory: {}'.format(data_root))
    includes = args.include_pack_pattern or ['*']
    excludes = args.exclude_pack_pattern or []
    records = []
    errors = []
    json_files = sorted(data_root.rglob('*.json'))
    for path in json_files:
        pack_type, pack_name = get_pack(path, data_root)
        if pack_type in {'behavior_pack', 'resource_pack'} and (not should_include_pack(pack_name, includes, excludes)):
            continue
        try:
            data = load_jsonc(path)
            records.extend(split_records(data_root, path, data))
        except Exception as exc:
            error = {'path': rel(path, data_root), 'error': '{}: {}'.format(type(exc).__name__, exc)}
            errors.append(error)
            if args.fail_on_invalid_json:
                raise
    records.sort(key=lambda r: (r['kind'], r['pack_type'], r['pack_name'], r['relative_path'], r.get('name') or ''))
    reverse = build_reverse(records)
    by_kind = Counter((r['kind'] for r in records))
    by_pack = Counter(('{}/{}'.format(r['pack_type'], r['pack_name']) for r in records))
    stats = {'json_files_scanned': len(json_files), 'records': len(records), 'errors': len(errors), 'by_kind': dict(sorted(by_kind.items())), 'by_pack': dict(sorted(by_pack.items())), 'components': len(reverse['by_component']), 'references': len(reverse['by_reference']), 'identifiers': len(reverse['by_identifier'])}
    return {'schema_version': SCHEMA_VERSION, 'generated_at': utcnow_iso(), 'data_root': str(data_root), 'stats': stats, 'packs': collect_pack_meta(data_root, includes, excludes), 'records': records, 'reverse_index': reverse, 'errors': errors}

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, help='Minecraft Bedrock data directory.')
    parser.add_argument('--out', required=True, help='Output directory for index files.')
    parser.add_argument('--include-pack-pattern', action='append', default=['*'], help='Pack name glob to include. May be repeated.')
    parser.add_argument('--exclude-pack-pattern', action='append', default=[], help='Pack name glob to exclude. May be repeated.')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print index JSON.')
    parser.add_argument('--fail-on-invalid-json', action='store_true', help='Abort on parse errors instead of recording errors.json.')
    return parser.parse_args()

def main():
    args = parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    index = build_index(args)
    indent = 2 if args.pretty else None
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=indent, sort_keys=False), encoding='utf-8')
    (out / 'errors.json').write_text(json.dumps(index['errors'], ensure_ascii=False, indent=2), encoding='utf-8')
    write_markdown(out, index)
    print('Wrote {} records from {} JSON files to {}'.format(index['stats']['records'], index['stats']['json_files_scanned'], out))
    if index['errors']:
        print('Recorded {} parse/index errors in {}'.format(len(index['errors']), out / 'errors.json'))
if __name__ == '__main__':
    main()
