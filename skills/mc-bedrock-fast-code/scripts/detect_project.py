#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Detect NetEase Bedrock/MCStudio project features and prepared knowledge indexes."""
import argparse
import json
import re
from pathlib import Path
from pack_discovery import discover_packs

CODE_PATTERNS = {'mod_binding': 'from\\s+mod\\.common\\.mod\\s+import\\s+Mod', 'client_api': 'import\\s+mod\\.client\\.extraClientApi\\s+as\\s+clientApi', 'server_api': 'import\\s+mod\\.server\\.extraServerApi\\s+as\\s+serverApi', 'register_system': 'RegisterSystem\\s*\\(', 'listen_event': 'ListenForEvent\\s*\\(', 'engine_comp_factory': '(GetEngineCompFactory|CreateEngineCompFactory)\\s*\\(', 'client_server_message': '(BroadcastToServer|NotifyToClient)\\s*\\('}

def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None

def find_registry(explicit, root):
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if root:
        candidates.append(Path(root).expanduser() / 'knowledge_registry.json')
    candidates.append(Path.home() / '.codex' / 'mc-bedrock-fast-code-data' / 'knowledge_registry.json')
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None

def detect_project(project):
    signals = []
    pack_discovery = discover_packs(project, max_depth=2)
    for child in project.iterdir() if project.exists() else []:
        name = child.name
        if name == 'studio.json':
            signals.append({'kind': 'studio.json', 'path': name})
        elif child.is_dir() and name.endswith('Scripts'):
            signals.append({'kind': 'scripts_dir', 'path': name})
        elif child.is_dir() and name.startswith('netease_'):
            signals.append({'kind': 'netease_dir', 'path': name})
    for pack_type in ('behavior', 'resource'):
        for pack in pack_discovery['packs'][pack_type]:
            signals.append({'kind': '{}_pack_dir'.format(pack_type), 'path': str(Path(pack['path']).relative_to(project)), 'manifest': pack['manifest']})
    for manifest in pack_discovery['manifests']:
        if manifest['is_pack_manifest'] and not manifest['valid']:
            signals.append({'kind': 'invalid_pack_manifest', 'path': manifest['path'], 'errors': manifest['errors']})
    py_files = list(project.rglob('*.py'))[:500]
    for path in py_files:
        rel = path.relative_to(project)
        if (project / 'SKILL.md').exists() and rel.parts and (rel.parts[0] == 'scripts'):
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for kind, pattern in CODE_PATTERNS.items():
            if re.search(pattern, text):
                signals.append({'kind': kind, 'path': str(rel)})
    pack_names = sorted(set(pack['folder'] for kind in ('behavior', 'resource') for pack in pack_discovery['packs'][kind]))
    return {
        'project': str(project),
        'is_netease_bedrock_project': bool(signals),
        'signals': signals[:80],
        'pack_names': pack_names,
        'packs': pack_discovery['packs'],
        'manifest_errors': [manifest for manifest in pack_discovery['manifests'] if not manifest['valid']],
    }

def detect_knowledge(registry_path):
    if registry_path is None:
        return {'registry_found': False, 'missing': ['knowledge_registry.json', 'api_references', 'demo_index', 'vanilla_indexes']}
    registry = load_json(registry_path)
    if not isinstance(registry, dict):
        return {'registry_found': True, 'registry': str(registry_path), 'valid': False, 'missing': ['valid registry JSON']}
    checks = {'api_references': Path(registry.get('api_references', '')) / 'api-index.md' if registry.get('api_references') else None, 'demo_index': Path(registry.get('demo_index', '')) / 'demo_index.json' if registry.get('demo_index') else None, 'vanilla_indexes': Path(registry.get('vanilla_indexes', '')) if registry.get('vanilla_indexes') else None, 'remote_public_indexes': Path(registry.get('remote_public_indexes', '')) if registry.get('remote_public_indexes') else None}
    missing = []
    present = []
    for key, path in checks.items():
        ok = False
        if path is not None:
            ok = path.exists()
            if key == 'vanilla_indexes':
                ok = path.exists() and any(path.glob('*/index.json'))
            elif key == 'remote_public_indexes':
                ok = path.exists() and any(path.rglob('*.json'))
        if ok:
            present.append(key)
        else:
            missing.append(key)
    return {'registry_found': True, 'registry': str(registry_path), 'valid': True, 'present': present, 'missing': missing, 'root': registry.get('root')}

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='.', help='Workspace/project directory to inspect.')
    parser.add_argument('--registry', help='Path to knowledge_registry.json.')
    parser.add_argument('--root', help='Knowledge root containing knowledge_registry.json.')
    parser.add_argument('--check-knowledge', action='store_true', help='Explicitly inspect the default knowledge registry in addition to the project.')
    parser.add_argument('--json', action='store_true', help='Print JSON only.')
    return parser.parse_args()

def main():
    args = parse_args()
    project = Path(args.project).resolve()
    check_knowledge = bool(args.check_knowledge or args.registry or args.root)
    registry_path = find_registry(args.registry, args.root) if check_knowledge else None
    knowledge = detect_knowledge(registry_path) if check_knowledge else {'checked': False}
    result = {'project_detection': detect_project(project), 'knowledge': knowledge}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        pd = result['project_detection']
        kd = result['knowledge']
        print('Project: {}'.format(pd['project']))
        print('NetEase Bedrock project: {}'.format(pd['is_netease_bedrock_project']))
        print('Pack names: {}'.format(', '.join(pd['pack_names']) if pd['pack_names'] else '(none detected)'))
        print('Signals: {}'.format(len(pd['signals'])))
        for signal in pd['signals'][:20]:
            print('- {}: {}'.format(signal['kind'], signal['path']))
        print('Knowledge checked: {}'.format(check_knowledge))
        if check_knowledge:
            print('Registry found: {}'.format(kd['registry_found']))
            if kd.get('registry'):
                print('Registry: {}'.format(kd['registry']))
            print('Knowledge present: {}'.format(', '.join(kd.get('present', [])) if kd.get('present') else '(none)'))
            print('Knowledge missing: {}'.format(', '.join(kd.get('missing', [])) if kd.get('missing') else '(none)'))
    missing = result['knowledge'].get('missing') or []
    return 2 if check_knowledge and result['project_detection']['is_netease_bedrock_project'] and missing else 0
if __name__ == '__main__':
    raise SystemExit(main())
