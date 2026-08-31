"""Build a stage GLB + manifest from eMouseAtlas per-organ STL surfaces.

The Surfaces.zip in each model bundle ships professionally-surfaced, high-resolution
per-organ meshes as `EMAPA<id>_<name>.stl`, all in one shared coordinate frame. These are
far better than marching cubes over the down-sampled anatomy volume — especially for thin
organs — so we use them directly: load, colour from the label file, pack into one GLB.

Usage:
  python scripts/build_from_stl.py \
      --stl-dir data/ema/raw/TS26_EMA102/stl_all \
      --labels  data/ema/raw/TS26_EMA102/TS26_EMA102_anatomy.txt \
      --stage TS26 --out docs/data [--max-faces 50000]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import igl
import numpy as np
import trimesh

from convert_ema import biharmonic_fair
from ema_labels import parse_labels
from resection import reconstruct_from_mesh, slice_component_count


def densify_biharmonic(mesh: trimesh.Trimesh, upsample: int, lam: float) -> trimesh.Trimesh:
    """Densify a surface (igl.upsample subdivision) then curvature-minimise it with
    biharmonic fairing (igl cotangent Laplacian). On the clean high-res EMAP STL surfaces
    this smooths residual section stepping without shattering (unlike the thin, fragmented
    marching-cubes meshes from the down-sampled anatomy volume)."""
    if upsample > 0:
        V, F = igl.upsample(np.asarray(mesh.vertices, dtype=np.float64),
                            np.asarray(mesh.faces, dtype=np.int64), upsample)
        mesh = trimesh.Trimesh(V, F, process=False)
    if lam > 0:
        mesh = biharmonic_fair(mesh, lam)
    return mesh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out", default="docs/data")
    ap.add_argument("--max-faces", type=int, default=0,
                    help="decimate any organ above this many faces (0 = keep as-is)")
    ap.add_argument("--densify", type=int, default=0,
                    help="igl.upsample subdivision iterations before biharmonic fairing")
    ap.add_argument("--lam", type=float, default=0.0,
                    help="biharmonic fairing strength (0 = off)")
    ap.add_argument("--resection", action="store_true",
                    help="reconstruct sliced organs into continuous meshes (section interp)")
    ap.add_argument("--resection-min-slices", type=int, default=8,
                    help="reconstruct organs with at least this many slice-components")
    ap.add_argument("--pitch", type=float, default=1.0, help="voxelisation pitch for resection")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = parse_labels(args.labels)
    by_emapa = {l.emapa: l for l in labels.values() if l.emapa}

    scene = trimesh.Scene()
    manifest = []
    for stl in sorted(Path(args.stl_dir).glob("EMAPA*.stl")):
        m = re.match(r"EMAPA(\d+)_", stl.name)
        if not m:
            continue
        emapa = f"EMAPA:{m.group(1)}"
        lab = by_emapa.get(emapa)
        if lab is None:
            continue
        mesh = trimesh.load(stl, process=True)
        note = "STL"
        if args.resection and slice_component_count(mesh) >= args.resection_min_slices:
            # organ is a stack of disconnected slice-meshes -> interpolate between sections
            # (fair AFTER decimation, never on the full ~1M-face reconstruction)
            mesh = reconstruct_from_mesh(mesh, args.pitch, 0.0)
            note = "resection"
        elif args.densify:
            mesh = densify_biharmonic(mesh, args.densify, 0.0)
        if args.max_faces and len(mesh.faces) > args.max_faces:
            mesh = mesh.simplify_quadric_decimation(face_count=args.max_faces)
        if args.lam > 0:
            mesh = biharmonic_fair(mesh, args.lam)   # light fairing on the decimated mesh
        r, g, b = lab.rgb
        mesh.visual.face_colors = [r, g, b, 255]
        node = f"EMAPA{m.group(1)}"
        scene.add_geometry(mesh, node_name=node, geom_name=node)
        manifest.append({
            "organ_id": emapa,
            "display_name": lab.name,
            "mesh_node": node,
            "rgb": [r, g, b],
            "faces": int(len(mesh.faces)),
        })
        print(f"  {emapa:12s} {lab.name:<32s} faces={len(mesh.faces):>7d}  [{note}]", flush=True)

    if not manifest:
        print("no STL surfaces matched labels")
        return 1

    scene.rezero()   # centre; the web app scales each stage to a common view height
    glb = out_dir / f"{args.stage.lower()}.glb"
    js = out_dir / f"{args.stage.lower()}.json"
    glb.write_bytes(scene.export(file_type="glb"))
    total = sum(o["faces"] for o in manifest)
    js.write_text(json.dumps(
        {"stage": args.stage, "n_organs": len(manifest), "total_faces": total,
         "source": "eMouseAtlas Surfaces.zip STL", "organs": manifest}, indent=2))
    print(f"\nwrote {glb} ({glb.stat().st_size/1e6:.1f} MB), {len(manifest)} organs, "
          f"{total} faces\nwrote {js}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
