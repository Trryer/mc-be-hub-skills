#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Sanity-check common NetEase Bedrock ModSDK pack references."""
import argparse
import json
from pathlib import Path
from compat import try_load_json
from pack_discovery import discover_packs

def load_json(path, errors):
    try:
        return try_load_json(path)
    except Exception as exc:
        errors.append('JSON parse error: {}: {}'.format(path, exc))
        return None


def select_packs(discovery, pack_type, errors=None):
    return [Path(pack['path']) for pack in discovery['packs'][pack_type]]

def exists_by_value(base, folders, value):
    clean = value
    for prefix in ('Texture.', 'Material.', 'Geometry.'):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    clean = clean.replace('.', '_').replace(':', '_')
    for folder in folders:
        root = base / folder
        if not root.exists():
            continue
        for path in root.rglob('*.json'):
            if clean.lower() in path.stem.lower():
                return True
    return False

def collect_defined_keys(obj, container_key):
    keys = set()
    if isinstance(obj, dict):
        node = obj.get(container_key)
        if isinstance(node, dict):
            keys.update((str(k) for k in node.keys()))
        for value in obj.values():
            keys.update(collect_defined_keys(value, container_key))
    elif isinstance(obj, list):
        for value in obj:
            keys.update(collect_defined_keys(value, container_key))
    return keys

def lint_client_entities(resources, behaviors, errors, warnings):
    render_keys = set()
    material_keys = set()
    animation_controller_keys = set()
    for res in resources:
        for path in (res / 'render_controllers').glob('*.json') if (res / 'render_controllers').exists() else []:
            data = load_json(path, errors)
            if data is not None:
                render_keys.update(collect_defined_keys(data, 'render_controllers'))
        for path in (res / 'materials').glob('*.json') if (res / 'materials').exists() else []:
            data = load_json(path, errors)
            if data is not None:
                material_keys.update(collect_defined_keys(data, 'materials'))
        for path in (res / 'animation_controllers').glob('*.json') if (res / 'animation_controllers').exists() else []:
            data = load_json(path, errors)
            if data is not None:
                animation_controller_keys.update(collect_defined_keys(data, 'animation_controllers'))
    client_names = set()
    for res in resources:
        entity_paths = list((res / 'entity').glob('*.json')) if (res / 'entity').exists() else []
        client_names.update(path.stem.replace('.entity', '') for path in entity_paths)
        for path in entity_paths:
            data = load_json(path, errors)
            if not isinstance(data, dict):
                continue
            desc = (data.get('minecraft:client_entity') or {}).get('description') or {}
            identifier = desc.get('identifier', path.stem)
            for key in desc.get('render_controllers', []) or []:
                if isinstance(key, dict):
                    key = next(iter(key.values()), '')
                if key and key not in render_keys:
                    warnings.append('Client entity {} references render controller {}, but no matching key was found under any resource pack render_controllers folder.'.format(identifier, key))
            for key in (desc.get('materials') or {}).values():
                if key and key not in material_keys and (not str(key).startswith('entity_')):
                    warnings.append('Client entity {} references material {}, but no matching custom material key was found.'.format(identifier, key))
            for key in desc.get('animation_controllers') or []:
                if isinstance(key, dict):
                    key = next(iter(key.values()), '')
                if key and key not in animation_controller_keys:
                    warnings.append('Client entity {} references animation controller {}, but no matching key was found.'.format(identifier, key))
            for key in (desc.get('geometry') or {}).values():
                if key and not any(exists_by_value(root, ['models', 'models/entity', 'models/netease_block'], str(key)) for root in resources):
                    warnings.append('Client entity {} references geometry {}; check that the model file exists.'.format(identifier, key))
            for key in (desc.get('textures') or {}).values():
                if not any((root / (str(key) + '.png')).exists() for root in resources):
                    warnings.append('Client entity {} references texture {}, but it was not found in any resource pack.'.format(identifier, key))
    for beh in behaviors:
        for path in (beh / 'entities').glob('*.json') if (beh / 'entities').exists() else []:
            data = load_json(path, errors)
            if not isinstance(data, dict):
                continue
            desc = (data.get('minecraft:entity') or {}).get('description') or {}
            identifier = str(desc.get('identifier', path.stem)).split(':')[-1]
            if identifier not in client_names:
                warnings.append('Behavior entity {} has no matching resource/entity client file.'.format(desc.get('identifier', path.stem)))

def lint_ui(res, errors, warnings):
    ui_dir = res / 'ui'
    if not ui_dir.exists():
        return
    defs_path = ui_dir / '_ui_defs.json'
    if not defs_path.exists():
        warnings.append('resource/ui exists but _ui_defs.json is missing.')
        return
    data = load_json(defs_path, errors)
    if not isinstance(data, dict):
        return
    entries = data.get('ui_defs') or []
    for entry in entries:
        rel = str(entry)
        if not (res / rel).exists():
            warnings.append('_ui_defs.json references missing UI file: {}'.format(rel))

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--namespace', help='Deprecated compatibility option; pack folders are discovered from manifests.')
    return parser.parse_args()

def main():
    args = parse_args()
    project = Path(args.project).resolve()
    errors = []
    warnings = []
    discovery = discover_packs(project, max_depth=2)
    for manifest in discovery['manifests']:
        if manifest['is_pack_manifest'] or manifest['errors'] == ['manifest is not valid JSON/JSONC']:
            for message in manifest['errors']:
                errors.append('{}: {}'.format(manifest['path'], message))
    behaviors = select_packs(discovery, 'behavior', errors)
    resources = select_packs(discovery, 'resource', errors)
    if not behaviors and not resources:
        errors.append('No valid pack manifest was found within two directory levels.')
    for res in resources:
        lint_ui(res, errors, warnings)
    lint_client_entities(resources, behaviors, errors, warnings)
    for item in errors:
        print('ERROR: {}'.format(item))
    for item in warnings:
        print('WARN: {}'.format(item))
    if not errors and (not warnings):
        print('OK: no common reference problems found.')
    return 1 if errors else 0
if __name__ == '__main__':
    raise SystemExit(main())
