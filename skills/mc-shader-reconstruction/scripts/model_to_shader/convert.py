"""Local generic static-model -> SDF atlases + MC GLSL. Never edits a pack."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
from common import PRESETS,write_json,digest

HERE = Path(__file__).resolve().parent

def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('output',type=Path,help='New/empty directory; existing outputs are never overwritten')
    p.add_argument('--blender',help='Blender 4.5 executable or BLENDER_PATH')
    p.add_argument('--fbx-python',help='Python 3.11 with numpy, Pillow, ufbx==0.0.5')
    p.add_argument('--reader',choices=('auto','blender','ufbx'),default='auto')
    p.add_argument('--quality',choices=PRESETS,default='low')
    p.add_argument('--resolution',type=int,help='Longest grid edge; overrides quality sampling only')
    p.add_argument('--steps',type=int)
    p.add_argument('--name',default='converted_model')
    p.add_argument('--albedo',type=Path,help='Explicit RGB override for all materials; original UVs retained')
    p.add_argument('--material-map',type=Path,help='JSON object: source material name -> image path; relative to JSON')
    p.add_argument('--pose-frame',type=float,help='Explicit static snapshot; does not export animation')
    p.add_argument('--pose-fps',type=float,default=30.,help='FBX snapshot frame to seconds')
    p.add_argument('--clip',help='FBX snapshot clip name')
    p.add_argument('--obj-up',choices=('X','Y','Z'),default='Y')
    p.add_argument('--obj-forward',choices=('X','Y','Z','NEGATIVE_X','NEGATIVE_Y','NEGATIVE_Z'),default='NEGATIVE_Z')
    p.add_argument('--threads',type=int,default=6)
    p.add_argument('--max-atlas',type=int,default=8192)
    p.add_argument('--max-mib',type=float,default=256.,help='Decoded field+material atlas budget, not total tool RAM')
    p.add_argument('--shell-cells',type=float,default=.3)
    p.add_argument('--inspect-only',action='store_true')
    p.add_argument('--no-validate',action='store_true',help='Build assets but label result unvalidated')
    p.add_argument('--min-iou',type=float)
    p.add_argument('--max-mae',type=float)
    p.add_argument('--headers',type=Path,help='Optional actual engine GLSL include directory')
    p.add_argument('--glslang',type=Path,help='Optional glslang executable for strict compile')
    p.add_argument('--timeout',type=int,default=1800)
    return p.parse_args(argv)

def find_blender(value):
    value = value or os.environ.get('BLENDER_PATH') or shutil.which('blender')
    if not value or not Path(value).is_file():
        raise ValueError('Set --blender or BLENDER_PATH to an installed Blender 4.5 executable')
    return str(Path(value).resolve())

def main(argv=None):
    args = arguments(argv)
    out = args.output.resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        print('Refusing nonempty output: '+str(out),file=sys.stderr)
        return 2
    out.mkdir(parents=True,exist_ok=True)
    report = dict(status='RUNNING',stage='arguments',minecraft_runtime_tested=False,visual_review='PENDING')
    try:
        args.input = args.input.resolve()
        if args.input.suffix.lower() not in ('.fbx','.glb','.gltf','.obj') or not args.input.is_file():
            raise ValueError('Input must be an existing FBX, GLB, glTF 2.0 or OBJ')
        if not re.fullmatch('[a-z][a-z0-9_]*',args.name):
            raise ValueError('--name must be lowercase ASCII identifier, starting with a letter')
        if args.obj_forward.removeprefix('NEGATIVE_')==args.obj_up:
            raise ValueError('OBJ forward and up axes must differ')
        defaults = PRESETS[args.quality]
        resolution = defaults[0] if args.resolution is None else args.resolution
        steps = defaults[1] if args.steps is None else args.steps
        min_iou = defaults[2] if args.min_iou is None else args.min_iou
        max_mae = defaults[3] if args.max_mae is None else args.max_mae
        numeric = (args.pose_fps,args.max_mib,args.shell_cells,min_iou,max_mae)
        if not all(math.isfinite(v) for v in numeric) or not (32<=resolution<=768 and 32<=steps<=1024
            and args.pose_fps>0 and args.max_mib>0 and 0<=args.shell_cells<=1 and 0<min_iou<=1
            and 0<=max_mae<=1 and args.threads>=1 and args.timeout>=1 and 64<=args.max_atlas<=16384):
            raise ValueError('Invalid numeric argument/range')
        if args.pose_frame is not None and (not math.isfinite(args.pose_frame) or args.pose_frame<0):
            raise ValueError('--pose-frame must be finite and nonnegative')
        mapping = {}
        if args.material_map:
            mapping = json.loads(args.material_map.read_text(encoding='utf-8-sig'))
            if not isinstance(mapping,dict) or any(not isinstance(v,str) for v in mapping.values()):
                raise ValueError('--material-map must map material names to image filenames')
            mapping = {k:str((args.material_map.resolve().parent/v).resolve()) for k,v in mapping.items()}
        for image in list(mapping.values())+([str(args.albedo)] if args.albedo else []):
            if not Path(image).is_file():
                raise ValueError('Missing image: '+image)
        work = out/'intermediate'
        work.mkdir()
        cfg = dict(input=str(args.input),work=str(work),albedo=str(args.albedo.resolve()) if args.albedo else None,
                   material_map=mapping,pose_frame=args.pose_frame,pose_fps=args.pose_fps,clip=args.clip,
                   obj_up=args.obj_up,obj_forward=args.obj_forward)
        write_json(out/'import_config.json',cfg)
        fbx = args.input.suffix.lower()=='.fbx'
        with args.input.open('rb') as stream:
            binary = stream.read(23).startswith(b'Kaydara FBX Binary') if fbx else False
        use_ufbx = fbx and (args.reader=='ufbx' or (args.reader=='auto' and not binary))
        if args.reader=='ufbx' and not fbx:
            raise ValueError('ufbx reader accepts FBX only')
        report.update(stage='import',source=dict(file=str(args.input),sha256=digest(args.input)),
                      quality=args.quality,settings=dict(resolution=resolution,steps=steps,shell_cells=args.shell_cells,
                      max_mib=args.max_mib,min_iou=min_iou,max_mae=max_mae))
        if use_ufbx:
            python = args.fbx_python or sys.executable
            command = [python,'-E','-B',str(HERE/'import_ufbx.py'),str(out/'import_config.json')]
        else:
            if args.clip:
                raise ValueError('--clip selection currently belongs to the ufbx adapter; use an explicitly selected source pose for Blender')
            command = [find_blender(args.blender),'--background','--factory-startup','--python-exit-code','1',
                       '--python',str(HERE/'import_blender.py'),'--',str(out/'import_config.json')]
        with (out/'import.log').open('w',encoding='utf-8') as stream:
            result = subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=args.timeout)
        if result.returncode or not (work/'scene.json').exists():
            error_file = work/'import_error.json'
            detail = json.loads(error_file.read_text(encoding='utf-8'))['error'] if error_file.exists() else 'See import.log'
            raise RuntimeError('Import failed (exit %s): %s'%(result.returncode,detail))
        from common import load_scene
        _,info,_ = load_scene(work)
        report['import'] = info
        if args.inspect_only:
            report['status']='INSPECTED'
            write_json(out/'report.json',report)
            return 0
        report['stage']='bake'
        from bake import bake
        meta = bake(work,out,resolution,steps,args.threads,args.max_mib,args.max_atlas,args.shell_cells)
        from generate import generate
        generate(out,meta,args.name)
        report.update(stage='validation',field=meta,status='BUILT_UNVALIDATED')
        if not args.no_validate:
            from validate import validate
            validation = validate(out,args.name,min_iou,max_mae,args.headers,args.glslang)
            report.update(validation=validation,status=validation['status'])
        write_json(out/'report.json',report)
        print(report['status']+'; human visual review and Minecraft validation remain separate',flush=True)
        return 3 if report['status']=='VALIDATION_FAILED' else 0
    except Exception as error:
        report.update(status='ERROR',error=str(error),traceback=traceback.format_exc())
        write_json(out/'report.json',report)
        print('%s: %s'%(report['stage'],error),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
