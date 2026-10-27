"""Generate reusable model-space functions and an MC fullscreen adapter."""
from pathlib import Path
from common import write_json,digest

def vector(v):
    return 'vec%d(%s)'%(len(v),','.join('%.12f'%x for x in v))

def generate(out,meta,name):
    out = Path(out)
    code = (Path(__file__).parent/'model.glsl.in').read_text(encoding='utf-8')
    values = dict(GRID=vector(meta['dimensions']),ORIGIN=vector(meta['origin']),
                  PITCH='%.12f'%meta['pitch'],ATLAS=vector(meta['atlas']),TILE=vector(meta['tile']),
                  COLUMNS='%.1f'%meta['columns'],RANGE='%.12f'%meta['distance_range'],STEPS=str(meta['steps']))
    for key,value in values.items():
        code = code.replace('@'+key+'@',value)
    if '@' in code:
        raise ValueError('Unresolved model template token')
    (out/'model.glsl').write_text(code,encoding='utf-8')
    center = meta['model_bounds'][1][1]*.5
    prefix = '''// __multiversion__
#include "fragmentVersionCentroidUV.h"
#ifndef LAYOUT_BINDING
#define LAYOUT_BINDING(x)
#endif
#ifdef GL_ES
precision highp float;
precision highp int;
#endif
LAYOUT_BINDING(3) uniform sampler2D TEXTURE_3;
LAYOUT_BINDING(4) uniform sampler2D TEXTURE_4;
uniform vec4 EXTRA_VECTOR1; // seconds,width,height,degreesPerSecond
'''
    main = '''
void main(){
    float aspect=EXTRA_VECTOR1.y/max(EXTRA_VECTOR1.z,1.0);
    vec3 target=vec3(0,@CENTER@,0);
    vec3 origin=target+vec3(2.4,1.5,3.0)*max(1.0,1.1/aspect);
    vec3 forward=normalize(target-origin),right=normalize(cross(forward,vec3(0,1,0)));
    vec3 up=cross(right,forward);
    vec2 screen=uv*2.0-1.0;
    vec3 direction=normalize(forward+.31529879*(right*screen.x*aspect+up*screen.y));
    float angle=radians(mod(EXTRA_VECTOR1.x*EXTRA_VECTOR1.w,360.0));
    vec2 spin=vec2(cos(angle),sin(angle));
    vec3 ro=msSpin(origin,vec2(spin.x,-spin.y)),rd=msSpin(direction,vec2(spin.x,-spin.y));
    vec3 color=mix(vec3(.018,.025,.042),vec3(.065,.085,.12),uv.y);
#ifdef MODEL_VALIDATE_MASK
    color=vec3(0);
#endif
    float travel;
    if(msTrace(ro,rd,1000000.0,travel)){
#ifdef MODEL_VALIDATE_MASK
        color=vec3(1);
#else
        vec3 point=ro+rd*travel;
        color=msShade(msSample(TEXTURE_4,point).rgb,normalize(msSpin(msNormal(point),spin)),direction);
#endif
    }
    gl_FragColor=vec4(color,1);
}
'''.replace('@CENTER@','%.12f'%center)
    (out/(name+'.fragment')).write_text(prefix+code+main,encoding='utf-8')
    (out/(name+'.vertex')).write_text('''// __multiversion__
#include "vertexVersionCentroidUV.h"
#include "uniformWorldConstants.h"
attribute POS4 POSITION;
attribute vec2 TEXCOORD_0;
void main(){gl_Position=vec4(POSITION.xyz,1.0);uv=TEXCOORD_0;}
''',encoding='utf-8')
    write_json(out/'integration.json',dict(name=name,fragment=name+'.fragment',vertex=name+'.vertex',
        params=[dict(name='P0',uniform='EXTRA_VECTOR1',value=[0,1920,1080,20],meaning=['seconds','width','height','degreesPerSecond'])],
        depth_enable=True,texture_bindings=[dict(file='textures/field.png',sampler='TEXTURE_3',slot=3),
                                           dict(file='textures/material.png',sampler='TEXTURE_4',slot=4)],
        texture_filter='Bilinear',texture_wrap='Clamp',mipmaps=False,model_space='Y up; longest edge=2; bottom y=0',
        model_functions=dict(trace='msTrace(localOrigin,localUnitDirection,maxDistance,outTravel)',
                             normal='msNormal(localPoint)',color='msSample(TEXTURE_4,localPoint).rgb'),
        source_sha256=digest(out/(name+'.fragment')),
        deployment='Merge into project-specific static pass/material and lifecycle after verifying its texture/matrix contract'))
