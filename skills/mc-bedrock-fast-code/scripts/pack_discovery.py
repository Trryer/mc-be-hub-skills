#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Discover behavior and resource packs from their fixed manifest files."""

import uuid
from pathlib import Path
from compat import try_load_json


MANIFEST_NAMES = ('pack_manifest.json', 'manifest.json')
PACK_TYPES = {'data': 'behavior', 'resources': 'resource'}


def iter_manifest_paths(project, max_depth=2):
    """Yield fixed-name manifests whose containing directory is at most max_depth deep."""
    project = Path(project)
    pending = [(project, 0)]
    while pending:
        directory, depth = pending.pop(0)
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for child in children:
            if child.is_file() and child.name in MANIFEST_NAMES:
                yield child
            elif child.is_dir() and depth < max_depth:
                pending.append((child, depth + 1))


def inspect_manifest(path, project):
    path = Path(path)
    project = Path(project)
    relative_path = str(path.relative_to(project))
    result = {
        'path': relative_path,
        'folder': path.parent.name,
        'manifest_name': path.name,
        'is_pack_manifest': False,
        'valid': False,
        'pack_types': [],
        'module_types': [],
        'errors': [],
    }
    data = try_load_json(path)
    if not isinstance(data, dict):
        result['errors'].append('manifest is not valid JSON/JSONC')
        return result

    header = data.get('header')
    result['is_pack_manifest'] = isinstance(header, dict) or isinstance(data.get('modules'), list)
    header_name = header.get('name') if isinstance(header, dict) else None
    header_uuid = header.get('uuid') if isinstance(header, dict) else None
    result['header_name'] = header_name
    result['header_uuid'] = header_uuid
    if header_name != path.parent.name:
        result['errors'].append(
            'header.name {!r} does not match folder name {!r}'.format(header_name, path.parent.name)
        )
    try:
        result['normalized_uuid'] = str(uuid.UUID(str(header_uuid))).lower()
    except (ValueError, AttributeError, TypeError):
        result['normalized_uuid'] = None
        result['errors'].append('header.uuid {!r} is missing or invalid'.format(header_uuid))

    modules = data.get('modules')
    if not isinstance(modules, list) or not modules:
        result['errors'].append('modules must be a non-empty array')
    else:
        module_types = []
        for module in modules:
            module_type = module.get('type') if isinstance(module, dict) else None
            if module_type not in module_types:
                module_types.append(module_type)
        result['module_types'] = module_types
        unknown = [value for value in module_types if value not in PACK_TYPES]
        if unknown:
            result['errors'].append(
                'unsupported modules[].type: {}'.format(', '.join((repr(value) for value in unknown)))
            )
        result['pack_types'] = sorted(set(PACK_TYPES[value] for value in module_types if value in PACK_TYPES))
        if len(result['pack_types']) != 1:
            result['errors'].append('manifest must identify exactly one pack type: data or resources')

    result['valid'] = not result['errors']
    return result


def discover_packs(project, max_depth=2):
    project = Path(project)
    manifests = [inspect_manifest(path, project) for path in iter_manifest_paths(project, max_depth=max_depth)]
    uuid_folders = {}
    for manifest in manifests:
        if manifest['valid']:
            uuid_folders.setdefault(manifest['normalized_uuid'], set()).add(manifest['folder'])
    duplicate_uuids = dict((value, folders) for value, folders in uuid_folders.items() if len(folders) > 1)
    for manifest in manifests:
        folders = duplicate_uuids.get(manifest.get('normalized_uuid'))
        if folders:
            manifest['errors'].append(
                'header.uuid {} is duplicated across pack folders: {}'.format(
                    manifest['normalized_uuid'], ', '.join(sorted(folders))
                )
            )
            manifest['valid'] = False
    packs = {'behavior': [], 'resource': []}
    seen_paths = {'behavior': set(), 'resource': set()}
    for manifest in manifests:
        if not manifest['valid']:
            continue
        pack_type = manifest['pack_types'][0]
        pack_path = (project / manifest['path']).parent.resolve()
        if pack_path in seen_paths[pack_type]:
            continue
        seen_paths[pack_type].add(pack_path)
        packs[pack_type].append({
            'folder': manifest['folder'],
            'path': str(pack_path),
            'manifest': manifest['path'],
            'manifest_name': manifest['manifest_name'],
            'header_name': manifest['header_name'],
            'header_uuid': manifest['normalized_uuid'],
            'module_type': manifest['module_types'][0],
        })
    return {'manifests': manifests, 'packs': packs, 'max_depth': max_depth}
