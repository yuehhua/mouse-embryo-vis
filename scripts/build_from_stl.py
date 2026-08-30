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

import numpy as np
import trimesh

from ema_labels import parse_labels

FACTS_UNUSED = None  # facts live in the web app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out", default="docs/data")
    ap.add_argument("--max-faces", type=int, default=0,
                    help="decimate any organ above this many faces (0 = keep as-is)")
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
        mesh = trimesh.load(stl, process=False)
        if args.max_faces and len(mesh.faces) > args.max_faces:
            mesh = mesh.simplify_quadric_decimation(face_count=args.max_faces)
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
        print(f"  {emapa:12s} {lab.name:<32s} faces={len(mesh.faces):>7d}", flush=True)

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
