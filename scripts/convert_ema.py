"""Convert an eMouseAtlas indexed anatomy volume (NIfTI) into per-organ meshes
packed as one GLB per stage, plus a JSON manifest for the web app.

Pipeline per label:
  crop to bounding box -> marching_cubes (step_size controls triangle budget)
  -> trimesh -> optional Laplacian smoothing -> assign the label's RGB colour.

Stable organ id = the EMAPA ontology id, so the same organ lines up across stages.

Usage:
  python scripts/convert_ema.py \
      --nii  data/ema/raw/TS26_EMA102/TS26_EMA102_anatomy.nii \
      --labels data/ema/raw/TS26_EMA102/TS26_EMA102_anatomy.txt \
      --stage TS26 --out data/ema/processed \
      [--only 16688,16846,18321]   # EMAPA numbers, for a quick test subset
      [--min-voxels 200] [--step 2] [--smooth 5]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from scipy.ndimage import distance_transform_edt, find_objects, zoom
from skimage import measure

from ema_labels import parse_labels


def detect_section_axis(body: np.ndarray) -> int:
    """Guess the histological section-stacking axis of a reconstructed volume.

    Serial-section reconstructions terrace along the stacking axis: the boundary is
    re-drawn per section, so that axis carries far more surface 'step' faces per unit
    length than the two in-plane axes. Count boundary faces per direction and pick the max.
    """
    b = body.astype(np.int8)
    scores = [np.abs(np.diff(b, axis=a)).sum() / body.shape[a] for a in range(3)]
    return int(np.argmax(scores))


def shape_interpolate(mask: np.ndarray, axis: int, factor: int):
    """Shape-based (Raya & Udupa 1990) cubic-spline interpolation between sections.

    Labels are categorical, so we cannot spline the label IDs. Instead we turn the binary
    mask into a *signed distance field* (positive inside, negative outside), cubic-spline
    upsample that smooth field along the section axis, then re-threshold at 0. This
    interpolates the organ *boundary* smoothly between sections, removing the terracing.

    Returns (upsampled_mask, spacing) where spacing keeps physical proportions.
    """
    if factor <= 1 or mask.shape[axis] < 2:
        return mask, (1.0, 1.0, 1.0)
    sdf = (distance_transform_edt(mask) - distance_transform_edt(~mask)).astype(np.float32)
    factors = [1.0, 1.0, 1.0]
    factors[axis] = factor
    # order=3 == cubic spline; only the section axis is upsampled, keeping arrays small
    sdf_up = zoom(sdf, factors, order=3, mode="nearest")
    spacing = [1.0, 1.0, 1.0]
    spacing[axis] = 1.0 / factor                            # so 1 upsampled voxel = 1/factor
    return sdf_up >= 0.0, tuple(spacing)


def extract_mesh(mask: np.ndarray, spacing, step: int, smooth: int,
                 max_faces: int) -> trimesh.Trimesh | None:
    """Marching cubes on a padded binary mask -> smoothed, face-capped trimesh (or None).

    Returns the mesh in crop-local coordinates (origin at the crop corner, in original
    voxel units regardless of interpolation spacing), ready to translate by the crop `lo`.
    """
    padded = np.pad(mask, 1)  # closed surfaces at the volume border
    try:
        verts, faces, _normals, _vals = measure.marching_cubes(
            padded, level=0.5, spacing=spacing, step_size=step
        )
    except (RuntimeError, ValueError):
        return None
    if len(faces) == 0:
        return None
    verts = verts - np.asarray(spacing)   # undo the 1-voxel pad, in physical units
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    # Decimate FIRST (cheap), then smooth the light mesh — smoothing a 200k-face raw
    # marching-cubes mesh is far too slow, and the result is visually the same.
    if max_faces > 0 and len(mesh.faces) > max_faces:
        mesh = mesh.simplify_quadric_decimation(face_count=max_faces)
    if smooth > 0:
        # Taubin smoothing keeps volume better than plain Laplacian; pure-python, no deps.
        trimesh.smoothing.filter_taubin(mesh, iterations=smooth)
    return mesh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nii", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out", default="data/ema/processed")
    ap.add_argument("--only", default="", help="comma-separated EMAPA numbers to include")
    ap.add_argument("--min-voxels", type=int, default=200,
                    help="skip components smaller than this many voxels")
    ap.add_argument("--step", type=int, default=2, help="marching_cubes step_size (>=1)")
    ap.add_argument("--smooth", type=int, default=5, help="Taubin smoothing iterations")
    ap.add_argument("--max-faces", type=int, default=20000,
                    help="decimate any organ above this many faces (0 = no cap)")
    ap.add_argument("--interp-factor", type=int, default=0,
                    help="shape-based cubic-spline upsampling between sections (0/1 = off)")
    ap.add_argument("--interp-axis", type=int, default=-1,
                    help="section-stacking axis (-1 = auto-detect)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = parse_labels(args.labels)
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None

    print(f"loading {args.nii} ...", flush=True)
    img = nib.load(args.nii)
    vol = np.asarray(img.dataobj)  # keep native dtype; avoids float blow-up
    zooms = img.header.get_zooms()[:3]
    spacing = tuple(float(z) for z in zooms) if all(zooms) else (1.0, 1.0, 1.0)
    print(f"volume shape={vol.shape} dtype={vol.dtype} spacing={spacing}", flush=True)

    section_axis = -1
    if args.interp_factor > 1:
        section_axis = args.interp_axis if args.interp_axis >= 0 else detect_section_axis(vol > 0)
        print(f"shape-based interpolation: axis={section_axis} factor={args.interp_factor}", flush=True)

    scene = trimesh.Scene()
    manifest = []
    t0 = time.time()

    # one pass gives every label's bounding box, avoiding a full-volume scan per organ
    bboxes = find_objects(vol)
    for idx in sorted(labels):
        sl = bboxes[idx - 1] if 0 < idx <= len(bboxes) else None
        if sl is None:
            continue
        lab = labels[idx]
        emapa_num = int(lab.emapa.split(":")[1]) if lab.emapa else -1
        if only is not None and emapa_num not in only:
            continue

        # crop to the label's bounding box, then build the binary mask on the small region
        sub = vol[sl] == idx
        n_vox = int(sub.sum())
        if n_vox < args.min_voxels:
            continue
        lo = np.array([s.start for s in sl])

        if section_axis >= 0:
            # interpolate boundary between sections, then mesh at step=1 for the fine detail
            sub, spc = shape_interpolate(sub, section_axis, args.interp_factor)
            mesh = extract_mesh(sub, spc, 1, args.smooth, args.max_faces)
        else:
            mesh = extract_mesh(sub, spacing, args.step, args.smooth, args.max_faces)
        if mesh is None or len(mesh.faces) == 0:
            continue
        # shift the crop back into the shared model frame (original voxel units)
        mesh.apply_translation(np.asarray(lo, dtype=float))

        r, g, b = lab.rgb
        mesh.visual.face_colors = [r, g, b, 255]
        node_name = f"{lab.emapa.replace(':', '')}"
        scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)

        manifest.append({
            "organ_id": lab.emapa,
            "display_name": lab.name,
            "mesh_node": node_name,
            "rgb": [r, g, b],
            "voxels": n_vox,
            "faces": int(len(mesh.faces)),
        })
        print(f"  [{len(manifest):3d}] {lab.emapa:12s} {lab.name:<38s} "
              f"vox={n_vox:>8d} faces={len(mesh.faces):>6d}", flush=True)

    if not manifest:
        print("no meshes produced", flush=True)
        return 1

    # center + normalize the whole scene so the app camera is stage-agnostic
    scene.rezero()

    glb_path = out_dir / f"{args.stage.lower()}.glb"
    json_path = out_dir / f"{args.stage.lower()}.json"
    glb_path.write_bytes(scene.export(file_type="glb"))
    total_faces = sum(m["faces"] for m in manifest)
    json_path.write_text(json.dumps(
        {"stage": args.stage, "n_organs": len(manifest),
         "total_faces": total_faces, "organs": manifest},
        indent=2))

    dt = time.time() - t0
    print(f"\nwrote {glb_path} ({glb_path.stat().st_size/1e6:.1f} MB), "
          f"{len(manifest)} organs, {total_faces} faces in {dt:.1f}s", flush=True)
    print(f"wrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
