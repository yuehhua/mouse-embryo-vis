"""Reconstruct a continuous organ surface from an eMouseAtlas per-section STL.

Each EMAP organ STL is a *stack of disconnected slice-meshes* — one closed mesh per
histological section, with gaps between sections. Subdividing that only densifies within
each slice. To make one solid organ we must interpolate the shape *between* sections.

Method (shape-based, curvature-minimising):
  1. voxelise the STL solid,
  2. group content into per-section 2D masks (the slice cross-sections),
  3. for every (x,y) column, fit a natural cubic spline through the sections' signed
     distance values along the section axis and evaluate it at every z — a cubic spline is
     the 1-D biharmonic (minimum-curvature) interpolant, so the in-between sections bulge
     naturally instead of stepping,
  4. threshold at 0 and marching-cubes -> one continuous mesh.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy.interpolate import CubicSpline
from scipy.ndimage import distance_transform_edt
from skimage import measure


def detect_slice_axis(mesh: trimesh.Trimesh) -> int:
    """Section axis = the axis the slice components are thin along (their min extent)."""
    comps = mesh.split(only_watertight=False)
    if len(comps) < 3:
        return 2
    thin = np.array([(c.bounds[1] - c.bounds[0]).argmin() for c in comps])
    return int(np.bincount(thin, minlength=3).argmax())


def reconstruct(mesh: trimesh.Trimesh, pitch: float = 1.0):
    """STL of stacked slices -> continuous binary volume + its world transform."""
    axis = detect_slice_axis(mesh)
    vg = mesh.voxelized(pitch=pitch).fill()
    vol = np.asarray(vg.matrix, dtype=bool)
    origin, scale = vg.translation, vg.scale           # voxel(i,j,k) -> world
    vol = np.moveaxis(vol, axis, -1)                    # section axis last

    has = vol.any(axis=(0, 1))
    zs = np.where(has)[0]
    if len(zs) < 2:
        return None, None, None, None
    # group consecutive content slices into bands (one section each)
    bands, start, prev = [], zs[0], zs[0]
    for z in zs[1:]:
        if z <= prev + 1:
            prev = z
        else:
            bands.append((start, prev)); start = z; prev = z
    bands.append((start, prev))
    if len(bands) < 4:                    # too few sections for a cubic spline -> keep STL
        return None, None, None, None

    key_z = np.array([(a + b) / 2.0 for a, b in bands])
    # signed distance of each section's 2D mask on the shared grid
    key_sdf = np.stack([
        (distance_transform_edt(m2) - distance_transform_edt(~m2)).astype(np.float32)
        for m2 in (vol[:, :, a:b + 1].any(axis=2) for a, b in bands)
    ], axis=-1)

    # natural cubic spline of the SDF across sections == 1-D biharmonic interpolation
    cs = CubicSpline(key_z, key_sdf, axis=-1, bc_type="natural")
    full_z = np.arange(int(key_z[0]), int(key_z[-1]) + 1)
    full_sdf = cs(full_z)
    mask = full_sdf >= 0.0
    return mask, axis, origin, scale


def slice_component_count(mesh: trimesh.Trimesh) -> int:
    """How many disconnected components are thin along the section axis (i.e. slice-meshes)."""
    comps = mesh.split(only_watertight=False)
    if len(comps) < 2:
        return len(comps)
    ax = detect_slice_axis(mesh)
    return int(sum((c.bounds[1] - c.bounds[0]).argmin() == ax for c in comps))


def reconstruct_from_mesh(src: trimesh.Trimesh, pitch: float = 1.0,
                          smooth_lam: float = 0.0) -> trimesh.Trimesh | None:
    mask, axis, origin, scale = reconstruct(src, pitch)
    if mask is None:
        return src
    mask = np.moveaxis(mask, -1, axis)
    padded = np.pad(mask, 1)
    verts, faces, _n, _v = measure.marching_cubes(padded, level=0.5)
    verts = (verts - 1) * scale + origin
    mesh = trimesh.Trimesh(verts, faces, process=True)
    if smooth_lam > 0:
        from convert_ema import biharmonic_fair
        mesh = biharmonic_fair(mesh, smooth_lam)
    return mesh


def reconstruct_mesh(stl_path, pitch: float = 1.0, smooth_lam: float = 0.0) -> trimesh.Trimesh | None:
    src = trimesh.load(stl_path, process=True)
    mask, axis, origin, scale = reconstruct(src, pitch)
    if mask is None:
        return src
    mask = np.moveaxis(mask, -1, axis)                 # restore original axis order
    padded = np.pad(mask, 1)
    verts, faces, _n, _v = measure.marching_cubes(padded, level=0.5)
    verts = (verts - 1) * scale + origin               # voxel -> world (matches STL frame)
    mesh = trimesh.Trimesh(verts, faces, process=True)
    if smooth_lam > 0:
        from convert_ema import biharmonic_fair
        mesh = biharmonic_fair(mesh, smooth_lam)
    return mesh


if __name__ == "__main__":
    import sys
    m = reconstruct_mesh(sys.argv[1], pitch=float(sys.argv[2]) if len(sys.argv) > 2 else 1.0)
    out = sys.argv[3] if len(sys.argv) > 3 else "recon.glb"
    m.export(out)
    print(f"{out}: faces={len(m.faces)} bodies={m.body_count}")
