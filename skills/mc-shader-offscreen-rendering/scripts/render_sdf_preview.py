"""Preview MC-style uv/EXTRA_VECTOR1 SDF fragments with desktop OpenGL.

Python 3 dependencies: moderngl, numpy, Pillow. Run --help for arguments.
Only fragmentVersionCentroidUV.h is replaced; no MC renderer or texture binding
is simulated. GPU query timings exclude readback/encoding and are not MC FPS.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import moderngl
import numpy as np
from PIL import Image, ImageDraw


def load_fragment(path):
    raw = path.read_bytes()
    source = raw.decode('utf-8-sig')

    def replace_include(match):
        if match.group(1) != 'fragmentVersionCentroidUV.h':
            raise ValueError('Unsupported engine include: ' + match.group(1))
        return ''

    source = re.sub(r'^\s*#include\s+["<]([^">]+)[">][^\n]*',
                    replace_include, source, flags=re.M)
    if re.search(r'^\s*#(?:version|include)\b', source, flags=re.M):
        raise ValueError('Expected multiversion MC fragment without a #version directive')
    return source, hashlib.sha256(raw).hexdigest()


def make_program(ctx, source, version, defines):
    source = ''.join('#define ' + name + '\n' for name in defines) + source
    if version == '100':
        vertex = ('#version 100\nattribute vec2 position; varying vec2 uv;'
                  'void main(){uv=position*.5+.5;gl_Position=vec4(position,0.,1.);}')
        fragment = '#version 100\nvarying highp vec2 uv;\n' + source
    else:
        header = ('#version 300 es\nprecision highp float;\n'
                  if version == '300 es' else '#version 330\n')
        vertex = (header + 'in vec2 position; out vec2 uv;'
                  'void main(){uv=position*.5+.5;gl_Position=vec4(position,0.,1.);}')
        fragment = (header + 'in vec2 uv; out vec4 previewColor;\n'
                    + re.sub(r'\bgl_FragColor\b', 'previewColor', source))
    return ctx.program(vertex_shader=vertex, fragment_shader=fragment)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shader', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, default=540)
    parser.add_argument('--duration', type=float, default=5.0)
    parser.add_argument('--times', type=float, nargs='+',
                        help='Keyframe times in seconds (default: six samples)')
    parser.add_argument('--exposure', type=float, default=1.15)
    parser.add_argument('--define', action='append', default=[],
                        help='Boolean preview macro, repeat as needed')
    parser.add_argument('--gpu-samples', type=int, default=5)
    parser.add_argument('--gif', action='store_true')
    parser.add_argument('--fps', type=int, default=30)
    args = parser.parse_args()
    if min(args.width, args.height, args.gpu_samples, args.fps) <= 0:
        parser.error('dimensions, gpu-samples and fps must be positive')
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error('duration must be positive and finite')
    if not math.isfinite(args.exposure) or args.exposure < 0:
        parser.error('exposure must be finite and nonnegative')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) for name in args.define):
        parser.error('--define accepts a macro name without a value')
    if args.times is None:
        args.times = [args.duration * fraction for fraction in (0., .18, .29, .54, .65, .99)]
    if any(not math.isfinite(t) or t < 0 or t > args.duration for t in args.times):
        parser.error('keyframe times must be finite and within 0..duration')
    if args.gif:
        target_ticks = round(args.duration * 100)
        samples = max(1, round(args.duration * args.fps))
        if args.fps > 100 or target_ticks < 1 or samples > target_ticks:
            parser.error('GIF requires 1..100 fps and at least one 10ms tick per sample')
        if abs(target_ticks / 100 - args.duration) > 1e-7:
            parser.error('GIF duration must be a multiple of 10ms')
    return args


def save_contact(images, times, path):
    columns = min(3, len(images))
    rows = math.ceil(len(images) / columns)
    thumb_width = 480
    thumb_height = max(1, round(thumb_width * images[0].height / images[0].width))
    contact = Image.new('RGB', (columns * thumb_width, rows * (thumb_height + 24)), '#080c14')
    draw = ImageDraw.Draw(contact)
    for index, (seconds, frame) in enumerate(zip(times, images)):
        x, y = (index % columns) * thumb_width, (index // columns) * (thumb_height + 24)
        contact.paste(frame.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS), (x, y + 24))
        draw.text((x + 10, y + 5), '%.3f s' % seconds, fill='white')
    contact.save(path)


def main():
    args = arguments()
    source, digest = load_fragment(args.shader)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        'status': 'RUNNING',
        'shader': str(args.shader.resolve()),
        'shader_sha256': digest,
        'resolution': [args.width, args.height],
        'duration_seconds': args.duration,
        'exposure': args.exposure,
        'preview_defines': args.define,
        'compile': {},
        'minecraft_runtime_tested': False,
        'timing_scope': 'standalone OpenGL GPU draw only; not Minecraft FPS',
        'gpu_ms_by_time': {},
        'frames': [],
    }
    ctx = None
    try:
        ctx = moderngl.create_standalone_context(require=330)
        report['renderer'] = ctx.info.get('GL_RENDERER')
        report['gl_version'] = ctx.info.get('GL_VERSION')
        for version in ('100', '300 es', '330'):
            try:
                program = make_program(ctx, source, version, args.define)
                program.release()
                report['compile'][version] = 'PASS on this desktop driver'
            except Exception as error:
                report['compile'][version] = str(error)
        if any(not value.startswith('PASS') for value in report['compile'].values()):
            raise RuntimeError('Compilation failed; see validation.json')

        program = make_program(ctx, source, '330', args.define)
        uniforms = {name for name in program if isinstance(program[name], moderngl.Uniform)}
        if uniforms != {'EXTRA_VECTOR1'}:
            raise ValueError('Expected only active uniform EXTRA_VECTOR1, got: ' + repr(sorted(uniforms)))
        quad = np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], dtype='f4')
        vbo = ctx.buffer(quad.tobytes())
        vao = ctx.simple_vertex_array(program, vbo, 'position')
        fbo = ctx.simple_framebuffer((args.width, args.height), components=4)
        fbo.use()
        ctx.viewport = (0, 0, args.width, args.height)
        ctx.disable(moderngl.DEPTH_TEST | moderngl.BLEND)

        def draw(seconds):
            program['EXTRA_VECTOR1'].value = (float(seconds), float(args.width),
                                               float(args.height), args.exposure)
            vao.render(mode=moderngl.TRIANGLES, vertices=6)

        def capture(seconds):
            draw(seconds)
            pixels = fbo.read(components=3, alignment=1)
            return Image.frombytes('RGB', (args.width, args.height), pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        images = []
        for index, seconds in enumerate(args.times):
            frame = capture(seconds)
            images.append(frame)
            filename = 'frame_%02d_%05dms.png' % (index, round(seconds * 1000))
            frame.save(args.out / filename)
            pixels = np.asarray(frame)
            report['frames'].append({'seconds': seconds, 'file': filename,
                                     'dynamic_range_rgb': int(pixels.max()) - int(pixels.min())})
            for _ in range(2):
                draw(seconds)
            ctx.finish()
            timings = []
            for _ in range(args.gpu_samples):
                with ctx.query(time=True) as query:
                    draw(seconds)
                ctx.finish()
                timings.append(query.elapsed / 1_000_000)
            report['gpu_ms_by_time'][str(seconds)] = {
                'samples': len(timings), 'median': round(float(np.median(timings)), 4),
                'min': round(min(timings), 4), 'max': round(max(timings), 4),
            }
        save_contact(images, args.times, args.out / 'contact.png')

        if args.gif:
            count = max(1, round(args.duration * args.fps))
            ticks = round(args.duration * 100)
            frames = []
            for index in range(count):
                frame = capture(index * args.duration / count)
                frame.thumbnail((640, 640), Image.Resampling.LANCZOS)
                frames.append(frame.quantize(colors=192))
            durations = [10 * (round((i + 1) * ticks / count) - round(i * ticks / count))
                         for i in range(count)]
            gif_path = args.out / 'orbit.gif'
            frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                           duration=durations, loop=0, disposal=2, optimize=False)
            with Image.open(gif_path) as encoded:
                encoded_ms = 0
                for index in range(encoded.n_frames):
                    encoded.seek(index)
                    encoded_ms += encoded.info['duration']
                report['gif'] = {'file': gif_path.name, 'samples': count,
                                 'frames': encoded.n_frames, 'duration_ms': encoded_ms,
                                 'encoded_resolution': list(encoded.size)}
            if encoded_ms != ticks * 10:
                raise RuntimeError('Encoded GIF duration differs from requested duration')
        report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = str(error)
        raise
    finally:
        if ctx is not None:
            ctx.release()
        (args.out / 'validation.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
