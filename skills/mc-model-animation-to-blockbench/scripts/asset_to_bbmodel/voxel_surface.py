# -*- coding: utf-8 -*-
"""Shared geometry-only helpers; usable in Blender without Pillow.

Cuboids remain a lossy approximation of curves, never a skin-weight export.
Face origins/axes match Blockbench's THREE.BufferGeometry.setShape vertices.
"""
import numpy as np


# top-left, left-to-right axis, top-to-bottom axis, outward normal
FACE_FRAMES = {
    "east": ((1, 1, 1), (0, 0, -1), (0, -1, 0), (1, 0, 0)),
    "west": ((0, 1, 0), (0, 0, 1), (0, -1, 0), (-1, 0, 0)),
    "up": ((0, 1, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "down": ((0, 0, 1), (1, 0, 0), (0, 0, -1), (0, -1, 0)),
    "south": ((0, 1, 1), (1, 0, 0), (0, -1, 0), (0, 0, 1)),
    "north": ((1, 1, 0), (-1, 0, 0), (0, -1, 0), (0, 0, -1)),
}


def merge_occupancy(occupied):
    """Merge geometry regardless of colour/material; retain texture per texel."""
    cells = set(occupied)
    boxes = []
    for start in sorted(cells):
        if start not in cells:
            continue
        x, y, z = start
        nx = 1
        while (x + nx, y, z) in cells:
            nx += 1
        ny = 1
        while all((xx, y + ny, z) in cells for xx in range(x, x + nx)):
            ny += 1
        nz = 1
        while all((xx, yy, z + nz) in cells for xx in range(x, x + nx) for yy in range(y, y + ny)):
            nz += 1
        cells.difference_update((xx, yy, zz) for xx in range(x, x + nx)
                                for yy in range(y, y + ny) for zz in range(z, z + nz))
        boxes.append((start, (nx, ny, nz)))
    return boxes


def face_grid(start, size, face, density):
    """Return texel-centre positions in grid units and the outward normal."""
    corner, right, down, normal = (np.array(v, dtype=float) for v in FACE_FRAMES[face])
    size = np.array(size, dtype=float)
    width = int(np.abs(right * size).sum()) * density
    height = int(np.abs(down * size).sum()) * density
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height
    positions = (np.array(start) + corner * size + u[None, :, None] * (right * size)
                 + v[:, None, None] * (down * size))
    return positions, normal


def pack_rectangles(sizes, limit):
    """Deterministic one-page shelf packing; fail instead of extra MC textures."""
    if not sizes:
        raise ValueError("No visible surface patches")
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0], i))
    edge = 64
    while edge <= limit:
        locations = [None] * len(sizes)
        x = y = row = 0
        for i in order:
            w, h = (s + 2 for s in sizes[i])  # one pixel of edge extrusion
            if w > edge or h > edge:
                break
            if x + w > edge:
                x, y, row = 0, y + row, 0
            if y + h > edge:
                break
            locations[i] = (x + 1, y + 1)
            x += w
            row = max(row, h)
        else:
            return edge, locations
        edge *= 2
    raise ValueError("Surface atlas exceeds %d pixels; lower --voxel-texture-density/--voxel-resolution or raise --voxel-atlas-size" % limit)
