"""Generate independent assets and exercise the public CLI, success and failure."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image
from common import write_json,digest

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--blender',required=True,type=Path)
    p.add_argument('--fbx-python',required=True,type=Path)
    p.add_argument('--work',required=True,type=Path,help='New/empty directory')
    p.add_argument('--headers',type=Path)
    p.add_argument('--glslang',type=Path)
    args = p.parse_args()
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        p.error('--work must be new/empty')
    work.mkdir(parents=True,exist_ok=True)
    fixtures = work/'fixtures'
    with (work/'fixture_generation.log').open('w',encoding='utf-8') as log:
        subprocess.run([str(args.blender),'--background','--factory-startup','--python-exit-code','1',
                        '--python',str(HERE/'make_regression_assets.py'),'--',str(fixtures)],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    common = ['--blender',str(args.blender),'--fbx-python',str(args.fbx_python)]
    for flag in ('headers','glslang'):
        if getattr(args,flag):
            common += ['--'+flag,str(getattr(args,flag))]
    rows = []
    def run(name,source='fixture.glb',extra=(),code=0,status='AUTOMATED_PASS',error=None):
        folder = work/name
        with (work/(name+'.log')).open('w',encoding='utf-8') as log:
            result = subprocess.run([sys.executable,'-B',str(HERE/'convert.py'),str(fixtures/source),str(folder),
                                     *common,*map(str,extra)],stdout=log,stderr=subprocess.STDOUT,timeout=300)
        report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
        assert result.returncode==code,(name,result.returncode,report)
        assert report['status']==status,(name,report)
        assert not report['minecraft_runtime_tested']
        assert report['visual_review']=='PENDING'
        if error:
            assert error.lower() in report['error'].lower(),(name,report['error'])
        rows.append(dict(name=name,status=report['status'],exit_code=result.returncode))
        print('PASS',name,flush=True)
        return report
    for ext in ('glb','gltf','obj','fbx'):
        run(ext,'fixture.'+ext)
    run('ufbx','fixture.fbx',extra=['--reader','ufbx'])
    run('factor','factor.gltf')
    run('animated_reject','animated.fbx',code=1,status='ERROR',error='animation')
    run('ufbx_animated_reject','animated.fbx',extra=['--reader','ufbx'],code=1,status='ERROR',error='animation')
    run('snapshot_blender','animated.glb',extra=['--pose-frame','11'])
    run('snapshot_ufbx','animated.fbx',extra=['--reader','ufbx','--pose-frame','10'])
    # Blender's importer offsets FBX keys to frame 1; ufbx time is clip-relative.
    run('snapshot_fbx_blender','animated.fbx',extra=['--pose-frame','12'])
    for angle in (0,90,180,270):
        first = np.asarray(Image.open(work/'snapshot_fbx_blender/validation'/('source_%03d.png'%angle)),dtype=float)
        second = np.asarray(Image.open(work/'snapshot_ufbx/validation'/('source_%03d.png'%angle)),dtype=float)
        mask = np.asarray(Image.open(work/'snapshot_fbx_blender/validation'/('source_mask_%03d.png'%angle)))[...,0]>127
        assert np.abs(first[mask]-second[mask]).mean()/255<.005,'Evaluated skin normals/pose differ across readers'
    run('snapshot_ufbx_start','animated.fbx',extra=['--reader','ufbx','--pose-frame','0','--inspect-only'],status='INSPECTED')
    with np.load(work/'snapshot_ufbx/intermediate/mesh.npz') as a, np.load(work/'snapshot_ufbx_start/intermediate/mesh.npz') as b:
        assert not np.allclose(a['vertices'],b['vertices']), 'Snapshot did not deform geometry'
    base = json.loads((work/'glb/intermediate/scene.json').read_text())
    for ext in ('gltf','obj','fbx','ufbx'):
        other = json.loads((work/ext/'intermediate/scene.json').read_text())
        assert np.allclose(base['model_bounds'],other['model_bounds'],atol=2e-4),(ext,'axis/transform mismatch')
        assert len(other['materials'])==2,(ext,'material loss')
        assert sum(m['image'] is not None for m in other['materials'])==1,(ext,'texture loss')
        assert other['triangles']==base['triangles'],(ext,'geometry loss')
        for angle in (0,90,180,270):
            first = np.asarray(Image.open(work/'glb/validation'/('source_%03d.png'%angle)),dtype=float)
            second = np.asarray(Image.open(work/ext/'validation'/('source_%03d.png'%angle)),dtype=float)
            mask = np.asarray(Image.open(work/'glb/validation'/('source_mask_%03d.png'%angle)))[...,0]>127
            assert np.abs(first[mask]-second[mask]).mean()/255<.005,(ext,'import color/UV/transform mismatch')
    assert 'texture_factor_linear' in next(m for m in json.loads((work/'factor/intermediate/scene.json').read_text())['materials'] if m['name']=='texture_uv')
    mapping = fixtures/'material_map.json'
    write_json(mapping,{'texture_uv':'albedo.png'})
    run('material_map','fixture.glb',extra=['--material-map',mapping,'--inspect-only'],status='INSPECTED')
    run('albedo_override','fixture.fbx',extra=['--albedo',fixtures/'albedo.png','--inspect-only'],status='INSPECTED')
    run('bad_map','fixture.glb',extra=['--material-map',fixtures/'bad_map.json'],code=1,status='ERROR',error='No such file')
    write_json(fixtures/'unknown_map.json',{'not_a_source_material':'albedo.png'})
    run('unknown_map','fixture.glb',extra=['--material-map',fixtures/'unknown_map.json'],code=1,status='ERROR',error='Unknown')
    run('missing_albedo',extra=['--albedo',fixtures/'absent.png'],code=1,status='ERROR',error='Missing image')
    run('missing_texture','missing_texture.gltf',code=1,status='ERROR',error='texture')
    run('alpha','alpha.gltf',code=1,status='ERROR',error='Transparent')
    run('no_uv','no_uv.obj',code=1,status='ERROR',error='no UV')
    run('broken','broken.glb',code=1,status='ERROR',error='Import failed')
    run('invalid_resolution',extra=['--resolution','0'],code=1,status='ERROR',error='numeric')
    run('budget',extra=['--max-mib','.001'],code=1,status='ERROR',error='budget exceeded')
    run('gate_fail',extra=['--min-iou','.99999','--max-mae','0'],code=3,status='VALIDATION_FAILED')
    run('unvalidated',extra=['--no-validate'],status='BUILT_UNVALIDATED')
    before = digest(work/'glb/report.json')
    result = subprocess.run([sys.executable,'-B',str(HERE/'convert.py'),str(fixtures/'fixture.glb'),str(work/'glb')],capture_output=True)
    assert result.returncode==2 and digest(work/'glb/report.json')==before,'Output overwritten'
    rows.append(dict(name='overwrite_refused',exit_code=2,status='PASS'))
    write_json(work/'regression.json',dict(status='PASS',cases=rows,
               scope='CLI/adapter/bake/compile/desktop comparison; human visual review and Minecraft are separate'))
    print('All',len(rows),'CLI cases passed; see',work/'regression.json')

if __name__=='__main__':
    main()
