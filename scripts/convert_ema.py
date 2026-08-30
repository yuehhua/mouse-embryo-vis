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
from skimage import measure

from ema_labels import parse_labels


def extract_mesh(mask: np.ndarray, spacing, step: int, smooth: int,
                 max_faces: int) -> trimesh.Trimesh | None:
    """Marching cubes on a padded binary mask -> smoothed, face-capped trimesh (or None)."""
    padded = np.pad(mask, 1)  # closed surfaces at the volume border
    try:
        verts, faces, _normals, _vals = measure.marching_cubes(
            padded, level=0.5, spacing=spacing, step_size=step
        )
    except (RuntimeError, ValueError):
        return None
    if len(faces) == 0:
        return None
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if smooth > 0:
        # Taubin smoothing keeps volume better than plain Laplacian; pure-python, no deps.
        trimesh.smoothing.filter_taubin(mesh, iterations=smooth)
    if max_faces > 0 and len(mesh.faces) > max_faces:
        mesh = mesh.simplify_quadric_decimation(face_count=max_faces)
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

    scene = trimesh.Scene()
    manifest = []
    t0 = time.time()

    present = np.unique(vol)
    for idx in sorted(labels):
        if idx not in present:
            continue
        lab = labels[idx]
        emapa_num = int(lab.emapa.split(":")[1]) if lab.emapa else -1
        if only is not None and emapa_num not in only:
            continue

        mask_full = vol == idx
        n_vox = int(mask_full.sum())
        if n_vox < args.min_voxels:
            continue

        # crop to bounding box for speed
        coords = np.argwhere(mask_full)
        lo = coords.min(0)
        hi = coords.max(0) + 1
        sub = mask_full[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]

        mesh = extract_mesh(sub, spacing, args.step, args.smooth, args.max_faces)
        if mesh is None or len(mesh.faces) == 0:
            continue
        # shift back into the shared model frame (account for pad of 1)
        mesh.apply_translation((np.array(lo) - 1) * np.array(spacing))

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
