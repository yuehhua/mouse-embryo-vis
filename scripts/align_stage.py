"""Rotate an already-built stage GLB onto the body frame of a reference stage GLB.

The web app only centers+scales each stage, so all stages must share one coordinate frame
or the slider spins/flips the embryo between stages. This is a pure rotation of the scene
graph — mesh quality is untouched.

Usage:
  python scripts/align_stage.py docs/data/ts23.glb scratch_build/ts26.glb out/ts23.glb
"""
from __future__ import annotations

import sys

import numpy as np
import trimesh

from convert_ema import align_frames, scene_world_vertices, stage_world_vertices


def main() -> int:
    src, ref, out = sys.argv[1], sys.argv[2], sys.argv[3]
    scene = trimesh.load(src, process=False)
    R, note = align_frames(scene_world_vertices(scene), stage_world_vertices(ref))
    T = np.eye(4)
    T[:3, :3] = R
    scene.apply_transform(T)
    scene.rezero()
    scene.export(out)
    print(f"{src} -> {out}: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
