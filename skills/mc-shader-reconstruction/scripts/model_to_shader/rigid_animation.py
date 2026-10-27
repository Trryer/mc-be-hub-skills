"""Encode sampled model-space rigid transforms into a data atlas and GLSL helpers.

This offline stage accepts an explicit NPZ interchange; it does not import FBX,
perform smooth skinning, bake geometry, deploy packs, or choose clip looping.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image


def quaternions(matrices):
    """Column-vector rotation matrices -> xyzw, preserving temporal hemisphere."""
    result = np.empty(matrices.shape[:-2] + (4,), dtype=float)
    for index in np.ndindex(matrices.shape[:-2]):
        r = matrices[index]
        trace = np.trace(r)
        if trace > 0:
            s = np.sqrt(trace + 1) * 2
            q = [(r[2, 1]-r[1, 2])/s, (r[0, 2]-r[2, 0])/s,
                 (r[1, 0]-r[0, 1])/s, s/4]
        else:
            i = int(np.argmax(np.diag(r)))
            j, k = (i+1) % 3, (i+2) % 3
            s = np.sqrt(1 + r[i, i] - r[j, j] - r[k, k]) * 2
            q = [0., 0., 0., 0.]
            q[i], q[j], q[k] = s/4, (r[j, i]+r[i, j])/s, (r[k, i]+r[i, k])/s
            q[3] = (r[k, j]-r[j, k])/s
        result[index] = q / np.linalg.norm(q)
    for frame in range(1, len(result)):
        flip = np.sum(result[frame-1] * result[frame], axis=-1) < 0
        result[frame, flip] *= -1
    return result


def encode(times, transforms, translation_range=None, max_atlas=4096, max_mib=64):
    times, transforms = np.asarray(times, dtype=float), np.asarray(transforms, dtype=float)
    if times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all():
        raise ValueError('times must contain at least two finite samples')
    steps = np.diff(times)
    if np.any(steps <= 0) or not np.allclose(steps, steps[0], rtol=1e-5, atol=1e-9):
        raise ValueError('times must be increasing and uniformly sampled; resample source curves first')
    if transforms.ndim != 4 or transforms.shape[0] != len(times) or transforms.shape[2:] != (4, 4) or transforms.shape[1] < 1:
        raise ValueError('transforms must have shape (samples, parts, 4, 4)')
    if not np.isfinite(transforms).all():
        raise ValueError('transforms contain non-finite data')
    if max_atlas < 1 or not np.isfinite(max_mib) or max_mib <= 0:
        raise ValueError('Atlas dimensions and memory budget must be positive')
    if not np.allclose(transforms[:, :, 3], [0, 0, 0, 1], atol=1e-7, rtol=0):
        raise ValueError('transforms must be affine column-vector matrices')
    rotation = transforms[:, :, :3, :3]
    error = np.max(np.abs(np.swapaxes(rotation, -1, -2) @ rotation - np.eye(3)))
    if error > 1e-5 or np.any(np.abs(np.linalg.det(rotation)-1) > 1e-5):
        raise ValueError('Rigid tracks require rotation+translation; bake or separately handle scale, reflection, shear and deformation')
    samples, parts = transforms.shape[:2]
    width, height = 1 << (samples-1).bit_length(), parts*4
    gpu_bytes = width*height*4
    if max(width, height) > max_atlas or gpu_bytes > max_mib*1024**2:
        raise ValueError(f'Animation atlas {width}x{height}, {gpu_bytes/1024**2:.3f} MiB exceeds budget')
    q = quaternions(rotation)
    translation = transforms[:, :, :3, 3]
    extent = float(np.abs(translation).max())
    limit = max(extent*1.001, 1e-6) if translation_range is None else float(translation_range)
    if not np.isfinite(limit) or limit <= 0 or extent > limit:
        raise ValueError(f'translation-range must be positive and cover displacement {extent}; no clipping permitted')
    values = np.concatenate([q, translation/limit, np.zeros((samples, parts, 1))], axis=-1)
    encoded = np.rint((np.clip(values, -1, 1)*.5+.5)*65535).astype('u2')
    pairs = encoded.reshape(samples, parts, 4, 2).transpose(1, 2, 0, 3).reshape(height, samples, 2)
    pixels = np.zeros((height, width, 4), dtype='u1')
    pixels[:, :samples, 0::2] = pairs >> 8
    pixels[:, :samples, 1::2] = pairs & 255
    pixels[:, samples:] = pixels[:, samples-1:samples]
    decoded_q, decoded_t = decode(pixels, samples, parts, limit)
    # Sign-invariant chord distance is stable near zero angular error.
    chord = np.minimum(np.linalg.norm(q-decoded_q, axis=-1), np.linalg.norm(q+decoded_q, axis=-1))
    angular_error = np.degrees(4*np.arcsin(np.clip(chord/2, 0, 1)))
    adjacent = np.abs(np.sum(q[:-1]*q[1:], axis=-1))
    max_step = float(np.degrees(2*np.arccos(np.clip(adjacent, 0, 1))).max())
    endpoints = np.abs(np.sum(q[0]*q[-1], axis=-1))
    report = dict(schema='rigid-animation-v1', samples=samples, parts=parts,
                  source_start_seconds=float(times[0]), duration_seconds=float(times[-1]-times[0]),
                  sample_hz=float(1/steps[0]), atlas=[width, height], gpu_bytes_rgba8=gpu_bytes,
                  translation_range=limit, rigid_matrix_error=float(error),
                  angular_quantization_error_degrees=float(angular_error.max()),
                  translation_quantization_error=float(np.abs(decoded_t-translation).max()),
                  max_adjacent_rotation_degrees=max_step,
                  endpoint_rotation_degrees=np.degrees(2*np.arccos(np.clip(endpoints, 0, 1))).tolist(),
                  endpoint_translation_delta=np.linalg.norm(translation[-1]-translation[0], axis=-1).tolist(),
                  playback='caller supplies clip time: once, hold, loop or ping-pong',
                  warnings=['Large adjacent rotation: increase source sampling and check intermediate poses'] if max_step >= 90 else [])
    return pixels, report


def decode(pixels, samples, parts, translation_range):
    """CPU reference for byte pairing and texel row conventions."""
    pixels = np.asarray(pixels, dtype='u2')
    pairs = np.stack([pixels[:, :, 0]*256+pixels[:, :, 1], pixels[:, :, 2]*256+pixels[:, :, 3]], axis=-1)
    values = (pairs[:, :samples].reshape(parts, 4, samples, 2).transpose(2, 0, 1, 3).reshape(samples, parts, 8)/65535*2-1)
    q = values[:, :, :4]
    q /= np.linalg.norm(q, axis=-1, keepdims=True)
    return q, values[:, :, 4:7]*translation_range


def glsl(report):
    """GLSL 100 helpers; profile header supplies texture2D compatibility."""
    width, height = report['atlas']
    return '''// Model-space rigid tracks; data texture: linear RGBA8, clamp, no mipmaps.
// Nearest texel reads; time interpolation is performed explicitly below.
vec2 msaPair(sampler2D data, float bone, float row, float frame) {
    vec4 v=texture2D(data, vec2((frame+0.5)/@WIDTH@, (bone*4.0+row+0.5)/@HEIGHT@));
    return vec2(dot(v.rg,vec2(65280.0,255.0)),dot(v.ba,vec2(65280.0,255.0)))/65535.0*2.0-1.0;
}
void msaPose(sampler2D data, float bone, float clipSeconds, out vec4 q, out vec3 t) {
    float frame=clamp(clipSeconds/@DURATION@,0.0,1.0)*@LAST@;
    float a=floor(frame),b=min(a+1.0,@LAST@),f=fract(frame);
    vec4 q0=vec4(msaPair(data,bone,0.0,a),msaPair(data,bone,1.0,a));
    vec4 q1=vec4(msaPair(data,bone,0.0,b),msaPair(data,bone,1.0,b));
    if(dot(q0,q1)<0.0) q1=-q1;
    q=normalize(mix(q0,q1,f));
    vec3 t0=vec3(msaPair(data,bone,2.0,a),msaPair(data,bone,3.0,a).x);
    vec3 t1=vec3(msaPair(data,bone,2.0,b),msaPair(data,bone,3.0,b).x);
    t=mix(t0,t1,f)*@RANGE@;
}
vec3 msaRotate(vec4 q, vec3 p) {
    return p+2.0*cross(q.xyz,cross(q.xyz,p)+q.w*p);
}
'''.replace('@WIDTH@', f'{float(width):.1f}').replace('@HEIGHT@', f'{float(height):.1f}').replace('@DURATION@', format(report['duration_seconds'], '.17e')).replace('@LAST@', f'{float(report["samples"]-1):.1f}').replace('@RANGE@', format(report['translation_range'], '.17e'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='NPZ: times[K], transforms[K,B,4,4], uniformly sampled, model-space rigid matrices')
    parser.add_argument('output', type=Path, help='New or empty directory')
    parser.add_argument('--translation-range', type=float, help='Explicit symmetric range; default covers measured displacement')
    parser.add_argument('--max-atlas', type=int, default=4096)
    parser.add_argument('--max-mib', type=float, default=64)
    args = parser.parse_args(argv)
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error('Output must be a new or empty directory')
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(status='ERROR')
    try:
        if args.input.suffix.lower() != '.npz':
            raise ValueError('Input must be an NPZ motion interchange')
        with np.load(args.input, allow_pickle=False) as source:
            pixels, report = encode(source['times'], source['transforms'], args.translation_range,
                                    args.max_atlas, args.max_mib)
        Image.fromarray(pixels).save(args.output/'animation.png')
        (args.output/'animation.glsl').write_text(glsl(report), encoding='utf8')
        report.update(status='ENCODED', minecraft_runtime_tested=False)
    except (OSError, ValueError, KeyError) as error:
        report.update(status='ERROR', error=str(error))
        print('ERROR:', error, file=sys.stderr)
    (args.output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf8')
    return 0 if report['status']=='ENCODED' else 1


if __name__=='__main__':
    raise SystemExit(main())
