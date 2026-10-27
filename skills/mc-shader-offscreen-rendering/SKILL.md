---
name: mc-shader-offscreen-rendering
description: Render and compare full-screen Minecraft-style fragment shaders offscreen with desktop OpenGL. Use for repeatable keyframes, animation previews, shader source checks, and GPU timing; game runtime and device performance still require in-game validation.
---

# MC Shader Offscreen Rendering

Use an isolated Python 3 environment to render a supported Minecraft-style fullscreen fragment shader into PNG keyframes, contact sheets, optional GIFs, and a GPU timing report. This checks the desktop preview path and helps compare changes; it does not emulate the Minecraft renderer or establish in-game FPS.

## Workflow

1. Identify the exact deployed fragment shader, its EXTRA_VECTOR1 layout, active macros, and supported includes. Compare a nested development copy with the deployed file when both exist.
2. Read [the preview contract](references/preview-and-validation.md) before using the bundled script. It documents accepted GLSL inputs, outputs, and limitations.
3. Create a Python 3 environment and install [requirements](references/requirements-preview.txt). Keep these dependencies outside the ModSDK behavior pack.
4. Run [scripts/render_sdf_preview.py](scripts/render_sdf_preview.py) at relevant fixed times and resolutions. Record source SHA256, GPU/driver, compiler wrapper, and parameters with the generated report.
5. Compare identical shader inputs, resolutions, uniforms, textures, times, and GPU conditions. Apply the acceptance checks in the preview contract: inspect the generated images and continuous preview, correct failures and rerun affected checks. Report GPU query time separately from image readback/encoding and from Minecraft runtime measurements.

## Boundaries

The bundled preview tool supports MC-style fullscreen fragments that use fragmentVersionCentroidUV.h, uv, EXTRA_VECTOR1 = (seconds, width, height, exposure), and gl_FragColor. It removes only that known include and supplies a minimal desktop GLSL wrapper. Other engine includes, active uniforms, texture bindings, world-depth reconstruction, or nonmatching parameter layouts require a purpose-built preview harness.

Always validate final visual behavior, GPU compatibility, and FPS in the target Minecraft runtime. Desktop OpenGL output or timing cannot prove those results.
