#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Generate NetEase Bedrock ModSDK starter packs and common files."""
import argparse
import json
import re
import uuid
from pathlib import Path
from compat import as_text, try_load_json

BEHAVIOR_SUFFIXES = ('_behavior', '_beh', 'behavior', 'beh')
RESOURCE_SUFFIXES = ('_resource', '_res', 'resource', 'res')

def safe_namespace(value):
    ns = re.sub('[^a-z0-9_]+', '_', value.strip().lower()).strip('_')
    if not ns:
        raise SystemExit('namespace cannot be empty')
    return ns

def split_identifier(namespace, local_id):
    if ':' in local_id:
        ns, ident = local_id.split(':', 1)
        if namespace and safe_namespace(namespace) != safe_namespace(ns):
            raise SystemExit('identifier namespace {!r} does not match --namespace {!r}'.format(ns, namespace))
        return (safe_namespace(ns), safe_namespace(ident))
    return (safe_namespace(namespace), safe_namespace(local_id))

def class_name(namespace, suffix):
    base = ''.join((part.capitalize() for part in namespace.split('_') if part))
    return '{}{}'.format(base, suffix)


def suffix_namespace(name, suffixes):
    for suffix in suffixes:
        if name.endswith(suffix) and len(name) > len(suffix):
            base = name[:-len(suffix)]
            return base[:-1] if base.endswith('_') else base
    return None


def find_pack_dir(root, namespace, suffixes, default_suffix):
    for child in sorted(root.iterdir(), key=lambda p: len(p.name)) if root.exists() else []:
        if child.is_dir() and suffix_namespace(child.name, suffixes) == namespace:
            return child
    return root / '{}{}'.format(namespace, default_suffix)

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace('\n', '\r\n'), encoding='utf-8')

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def manifest(name, description, pack_type):
    module_type = 'data' if pack_type == 'behavior' else 'resources'
    return {'format_version': 1, 'header': {'description': description, 'name': name, 'uuid': str(uuid.uuid4()), 'version': [0, 0, 1]}, 'modules': [{'description': description, 'type': module_type, 'uuid': str(uuid.uuid4()), 'version': [0, 0, 1]}]}

def create_pack(args):
    ns = safe_namespace(args.namespace)
    out = Path(args.out).resolve()
    beh = out / '{}_behavior'.format(ns)
    res = out / '{}_resource'.format(ns)
    script_dir = beh / '{}Scripts'.format(ns)
    beh_manifest = manifest(beh.name, '{} behavior pack'.format(ns), 'behavior')
    res_manifest = manifest(res.name, '{} resource pack'.format(ns), 'resource')
    write_json(beh / 'manifest.json', beh_manifest)
    write_json(res / 'manifest.json', res_manifest)
    write_json(out / 'world_behavior_packs.json', [{'pack_id': beh_manifest['header']['uuid'], 'version': [0, 0, 1]}])
    write_json(out / 'world_resource_packs.json', [{'pack_id': res_manifest['header']['uuid'], 'version': [0, 0, 1]}])
    write_text(script_dir / '__init__.py', '')
    write_text(script_dir / 'modConfig.py', mod_config(ns))
    write_text(script_dir / 'modMain.py', mod_main(ns, args.with_server, args.with_client))
    if args.with_server:
        write_text(script_dir / '{}ServerSystem.py'.format(ns), server_system(ns))
    if args.with_client:
        write_text(script_dir / '{}ClientSystem.py'.format(ns), client_system(ns, args.with_ui))
    if args.with_ui:
        add_ui(argparse.Namespace(project=str(out), namespace=ns, screen='main'))
    print('Created starter pack at {}'.format(out))

def mod_config(ns):
    return '# -*- coding: utf-8 -*-\n\nMOD_NAMESPACE = "{}"\nMOD_VERSION = "0.0.1"\nSERVER_SYSTEM = "{}"\nCLIENT_SYSTEM = "{}"\nUI_NAMESPACE = "{}_ui"\nUI_MAIN_SCREEN = "main"\n'.format(ns, class_name(ns, 'ServerSystem'), class_name(ns, 'ClientSystem'), ns)

def mod_main(ns, with_server, with_client):
    lines = ['# -*- coding: utf-8 -*-', 'from mod.common.mod import Mod', 'import mod.server.extraServerApi as serverApi', 'import mod.client.extraClientApi as clientApi', 'from {}Scripts import modConfig'.format(ns), '', '@Mod.Binding(name=modConfig.MOD_NAMESPACE, version=modConfig.MOD_VERSION)', 'class {}(object):'.format(class_name(ns, 'Mod')), '    def __init__(self):', '        print "===== init %s =====" % modConfig.MOD_NAMESPACE', '']
    if with_server:
        lines += ['    @Mod.InitServer()', '    def ServerInit(self):', '        serverApi.RegisterSystem(modConfig.MOD_NAMESPACE, modConfig.SERVER_SYSTEM, "{}Scripts.{}ServerSystem.{}")'.format(ns, ns, class_name(ns, 'ServerSystem')), '', '    @Mod.DestroyServer()', '    def ServerDestroy(self):', '        pass', '']
    if with_client:
        lines += ['    @Mod.InitClient()', '    def ClientInit(self):', '        clientApi.RegisterSystem(modConfig.MOD_NAMESPACE, modConfig.CLIENT_SYSTEM, "{}Scripts.{}ClientSystem.{}")'.format(ns, ns, class_name(ns, 'ClientSystem')), '', '    @Mod.DestroyClient()', '    def ClientDestroy(self):', '        pass', '']
    return '\n'.join(lines)

def server_system(ns):
    return '# -*- coding: utf-8 -*-\nimport mod.server.extraServerApi as serverApi\nfrom {}Scripts import modConfig\n\nServerSystem = serverApi.GetServerSystemCls()\ncompFactory = serverApi.GetEngineCompFactory()\n\n\nclass {}(ServerSystem):\n    def __init__(self, namespace, systemName):\n        super({}, self).__init__(namespace, systemName)\n        self.ListenEvent()\n\n    def ListenEvent(self):\n        pass\n\n    def UnListenEvent(self):\n        pass\n\n    def Destroy(self):\n        self.UnListenEvent()\n'.format(ns, class_name(ns, 'ServerSystem'), class_name(ns, 'ServerSystem'))

def client_system(ns, with_ui):
    ui_methods = ''
    if with_ui:
        ui_methods = '\n    def OpenMainScreen(self):\n        # Register and open UI here when wiring the screen to gameplay.\n        pass\n'
    return '# -*- coding: utf-8 -*-\nimport mod.client.extraClientApi as clientApi\nfrom {}Scripts import modConfig\n\nClientSystem = clientApi.GetClientSystemCls()\n\n\nclass {}(ClientSystem):\n    def __init__(self, namespace, systemName):\n        super({}, self).__init__(namespace, systemName)\n{}\n    def Destroy(self):\n        pass\n'.format(ns, class_name(ns, 'ClientSystem'), class_name(ns, 'ClientSystem'), ui_methods)

def project_dirs(project, ns):
    root = Path(project).resolve()
    return (root, find_pack_dir(root, ns, BEHAVIOR_SUFFIXES, '_behavior'), find_pack_dir(root, ns, RESOURCE_SUFFIXES, '_resource'))

def add_ui(args):
    ns = safe_namespace(args.namespace)
    root, _beh, res = project_dirs(args.project, ns)
    screen = safe_namespace(args.screen)
    ui_file = '{}.json'.format(screen)
    ui_defs = res / 'ui' / '_ui_defs.json'
    existing = {'ui_defs': []}
    if ui_defs.exists():
        try:
            existing = try_load_json(ui_defs)
        except Exception:
            existing = {'ui_defs': []}
    if not isinstance(existing, dict):
        existing = {'ui_defs': []}
    entry = 'ui/{}'.format(ui_file)
    defs = existing.setdefault('ui_defs', [])
    if entry not in defs:
        defs.append(entry)
    write_json(ui_defs, existing)
    write_json(res / 'ui' / ui_file, {'namespace': '{}_ui'.format(ns), '{}_screen'.format(screen): {'type': 'screen', 'controls': [{'root_panel': {'type': 'panel', 'size': ['100%', '100%'], 'controls': []}}]}})
    print('Added UI screen {} under {}'.format(screen, root))

def add_item(args):
    ns, item_id = split_identifier(args.namespace, args.id)
    _root, beh, res = project_dirs(args.project, ns)
    identifier = '{}:{}'.format(ns, item_id)
    write_json(beh / 'netease_items_beh' / '{}.json'.format(item_id), {'format_version': '1.10', 'minecraft:item': {'description': {'identifier': identifier, 'category': 'Items'}, 'components': {'minecraft:max_stack_size': args.max_stack_size}}})
    write_json(res / 'netease_items_res' / '{}.json'.format(item_id), {'format_version': '1.10', 'minecraft:item': {'description': {'identifier': identifier, 'category': 'Items'}, 'components': {'minecraft:icon': '{}:{}'.format(ns, item_id)}}})
    update_texture_atlas(res / 'textures' / 'item_texture.json', ns, item_id, 'textures/items/{}'.format(item_id))
    append_lang(res / 'texts' / 'zh_CN.lang', 'item.{}.name'.format(identifier), args.display_name or item_id)
    print('Added item {}'.format(identifier))

def add_block(args):
    ns, block_id = split_identifier(args.namespace, args.id)
    _root, beh, res = project_dirs(args.project, ns)
    identifier = '{}:{}'.format(ns, block_id)
    write_json(beh / 'netease_blocks' / '{}.json'.format(block_id), {'format_version': '1.10', 'minecraft:block': {'description': {'identifier': identifier}, 'components': {'minecraft:block_light_absorption': 0, 'minecraft:destroy_time': 1.0, 'netease:render_layer': {'value': 'opaque'}}}})
    update_blocks_json(res / 'blocks.json', identifier, block_id)
    update_texture_atlas(res / 'textures' / 'terrain_texture.json', ns, block_id, 'textures/blocks/{}'.format(block_id))
    append_lang(res / 'texts' / 'zh_CN.lang', 'tile.{}.name'.format(identifier), args.display_name or block_id)
    print('Added block {}'.format(identifier))

def add_entity(args):
    ns, ent_id = split_identifier(args.namespace, args.id)
    _root, beh, res = project_dirs(args.project, ns)
    identifier = '{}:{}'.format(ns, ent_id)
    write_json(beh / 'entities' / '{}.json'.format(ent_id), {'format_version': '1.10.0', 'minecraft:entity': {'description': {'identifier': identifier, 'is_spawnable': True, 'is_summonable': True}, 'components': {'minecraft:type_family': {'family': [ent_id]}, 'minecraft:health': {'value': 20, 'max': 20}, 'minecraft:movement': {'value': 0.25}, 'minecraft:navigation.walk': {'can_path_over_water': True, 'avoid_water': True}, 'minecraft:behavior.float': {'priority': 0}, 'minecraft:behavior.random_stroll': {'priority': 6, 'speed_multiplier': 0.8}, 'minecraft:physics': {}, 'minecraft:collision_box': {'width': 0.6, 'height': 1.8}}, 'events': {}}})
    write_json(res / 'entity' / '{}.entity.json'.format(ent_id), {'format_version': '1.8.0', 'minecraft:client_entity': {'description': {'identifier': identifier, 'spawn_egg': {'base_color': '#6BA7D6', 'overlay_color': '#FFFFFF'}, 'render_controllers': ['controller.render.{}'.format(ent_id)], 'geometry': {'default': 'geometry.{}'.format(ent_id)}, 'textures': {'default': 'textures/entity/{}/{}'.format(ent_id, ent_id)}, 'materials': {'default': 'entity_alphatest'}}}})
    write_json(res / 'render_controllers' / '{}.render_controllers.json'.format(ent_id), {'format_version': '1.8.0', 'render_controllers': {'controller.render.{}'.format(ent_id): {'geometry': 'Geometry.default', 'materials': [{'*': 'Material.default'}], 'textures': ['Texture.default']}}})
    if args.base:
        note = res / 'entity' / '{}.base_note.txt'.format(ent_id)
        write_text(note, 'Requested base vanilla entity: {}\nQuery local vanilla index before copying components.\n'.format(args.base))
    append_lang(res / 'texts' / 'zh_CN.lang', 'entity.{}.name'.format(identifier), args.display_name or ent_id)
    print('Added entity {}'.format(identifier))

def add_animation(args):
    ns = safe_namespace(args.namespace)
    anim_id = safe_namespace(args.id)
    _root, _beh, res = project_dirs(args.project, ns)
    key = 'animation.{}.{}'.format(ns, anim_id)
    write_json(res / 'animations' / '{}.animation.json'.format(anim_id), {'format_version': '1.8.0', 'animations': {key: {'loop': True, 'animation_length': 1.0, 'bones': {}}}})
    print('Added animation {}'.format(key))

def add_animation_controller(args):
    ns = safe_namespace(args.namespace)
    ctrl_id = safe_namespace(args.id)
    _root, beh, res = project_dirs(args.project, ns)
    base = beh if args.side == 'behavior' else res
    key = 'controller.animation.{}.{}'.format(ns, ctrl_id)
    write_json(base / 'animation_controllers' / '{}.animation_controllers.json'.format(ctrl_id), {'format_version': '1.8.0', 'animation_controllers': {key: {'initial_state': 'default', 'states': {'default': {'animations': [], 'transitions': []}}}}})
    print('Added {} animation controller {}'.format(args.side, key))

def add_render_controller(args):
    ns = safe_namespace(args.namespace)
    ctrl_id = safe_namespace(args.id)
    _root, _beh, res = project_dirs(args.project, ns)
    key = 'controller.render.{}.{}'.format(ns, ctrl_id)
    write_json(res / 'render_controllers' / '{}.render_controllers.json'.format(ctrl_id), {'format_version': '1.8.0', 'render_controllers': {key: {'geometry': 'Geometry.default', 'materials': [{'*': 'Material.default'}], 'textures': ['Texture.default']}}})
    print('Added render controller {}'.format(key))

def add_material(args):
    ns = safe_namespace(args.namespace)
    mat_id = safe_namespace(args.id)
    _root, _beh, res = project_dirs(args.project, ns)
    write_json(res / 'materials' / 'common.json', {'materials': {'version.{}.{}'.format(ns, mat_id): {'materials': {'default': mat_id}}, mat_id: {'+defines': ['USE_TEXTURE'], 'vertexShader': 'shaders/entity.vertex', 'fragmentShader': 'shaders/entity.fragment'}}})
    print('Added material {}'.format(mat_id))

def add_particle(args):
    ns, particle_id = split_identifier(args.namespace, args.id)
    _root, _beh, res = project_dirs(args.project, ns)
    identifier = '{}:{}'.format(ns, particle_id)
    write_json(res / 'particles' / '{}.json'.format(particle_id), {'format_version': '1.10.0', 'particle_effect': {'description': {'identifier': identifier, 'basic_render_parameters': {'material': 'particles_alpha', 'texture': 'textures/particle/{}'.format(particle_id)}}, 'components': {'minecraft:emitter_rate_instant': {'num_particles': 1}, 'minecraft:emitter_lifetime_once': {'active_time': 1}, 'minecraft:particle_lifetime_expression': {'max_lifetime': 1}, 'minecraft:particle_appearance_billboard': {'size': [0.25, 0.25], 'facing_camera_mode': 'rotate_xyz', 'uv': {'texture_width': 16, 'texture_height': 16, 'uv': [0, 0], 'uv_size': [16, 16]}}}}})
    print('Added particle {}'.format(identifier))

def update_texture_atlas(path, ns, key, texture):
    atlas_name = 'atlas.terrain' if path.name == 'terrain_texture.json' else 'atlas.items'
    data = {'resource_pack_name': ns, 'texture_name': atlas_name, 'texture_data': {}}
    if path.exists():
        try:
            data = try_load_json(path)
        except Exception:
            pass
    if not isinstance(data, dict):
        data = {'resource_pack_name': ns, 'texture_name': atlas_name, 'texture_data': {}}
    data.setdefault('texture_data', {})['{}:{}'.format(ns, key)] = {'textures': texture}
    write_json(path, data)

def update_blocks_json(path, identifier, texture_key):
    data = {}
    if path.exists():
        try:
            data = try_load_json(path)
        except Exception:
            pass
    if not isinstance(data, dict):
        data = {}
    data[identifier] = {'textures': texture_key, 'sound': 'stone'}
    write_json(path, data)

def append_lang(path, key, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = '{}={}\n'.format(key, value)
    if path.exists() and key in path.read_text(encoding='utf-8', errors='ignore'):
        return
    with path.open('a', encoding='utf-8') as fh:
        fh.write(as_text(line))

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd')
    sub.required = True
    p = sub.add_parser('create-pack')
    p.add_argument('--namespace', required=True, help='Required namespace, e.g. demo_mod.')
    p.add_argument('--out', required=True, help='Required output project path.')
    p.add_argument('--with-client', action='store_true', default=True)
    p.add_argument('--with-server', action='store_true', default=True)
    p.add_argument('--with-ui', action='store_true')
    p.set_defaults(func=create_pack)
    p = sub.add_parser('add-ui')
    p.add_argument('--project', required=True, help='Required existing project path.')
    p.add_argument('--namespace', required=True, help='Required namespace, e.g. demo_mod.')
    p.add_argument('--screen', default='main', help='Required UI screen id; defaults to main when the user asked for a generic starter UI.')
    p.set_defaults(func=add_ui)
    p = sub.add_parser('add-item')
    p.add_argument('--project', required=True, help='Required existing project path.')
    p.add_argument('--namespace', required=True, help='Required namespace part of <namespace>:<item_id>.')
    p.add_argument('--id', required=True, help='Required local item id part of <namespace>:<item_id>.')
    p.add_argument('--display-name')
    p.add_argument('--max-stack-size', type=int, default=64)
    p.set_defaults(func=add_item)
    p = sub.add_parser('add-block')
    p.add_argument('--project', required=True, help='Required existing project path.')
    p.add_argument('--namespace', required=True, help='Required namespace part of <namespace>:<block_id>.')
    p.add_argument('--id', required=True, help='Required local block id part of <namespace>:<block_id>.')
    p.add_argument('--display-name')
    p.set_defaults(func=add_block)
    p = sub.add_parser('add-entity')
    p.add_argument('--project', required=True, help='Required existing project path.')
    p.add_argument('--namespace', required=True, help='Required namespace part of <namespace>:<entity_id>.')
    p.add_argument('--id', required=True, help='Required local entity id part of <namespace>:<entity_id>.')
    p.add_argument('--display-name')
    p.add_argument('--base', help='Optional vanilla entity identifier to query from local indexes before refinement.')
    p.set_defaults(func=add_entity)
    p = sub.add_parser('add-animation')
    p.add_argument('--project', required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--id', required=True)
    p.set_defaults(func=add_animation)
    p = sub.add_parser('add-animation-controller')
    p.add_argument('--project', required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--id', required=True)
    p.add_argument('--side', choices=['resource', 'behavior'], default='resource')
    p.set_defaults(func=add_animation_controller)
    p = sub.add_parser('add-render-controller')
    p.add_argument('--project', required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--id', required=True)
    p.set_defaults(func=add_render_controller)
    p = sub.add_parser('add-material')
    p.add_argument('--project', required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--id', required=True)
    p.set_defaults(func=add_material)
    p = sub.add_parser('add-particle')
    p.add_argument('--project', required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--id', required=True)
    p.set_defaults(func=add_particle)
    return parser

def main():
    args = build_parser().parse_args()
    args.func(args)
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
