# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An interactive "guess the organ" 3D web game for college students, built on **eMouseAtlas
(EMA / EMAP)** mouse-embryo anatomy data. A translucent embryo body is shown in Three.js;
one organ glows and the player picks its name. Live: <https://yuehhua.github.io/mouse-embryo-vis/>
(GitHub Pages, served from the `docs/` folder on `main`).

## Critical environment constraint

**`/home` is 100% full — never install to, write to, or cache under `/home`.** All tooling
lives under the project on the Workbench drive. When running Python/pip/npm/headless-Chrome,
redirect every cache and tempdir into `./.cache` (already gitignored):

```bash
export PIP_CACHE_DIR="$PWD/.cache/pip" XDG_CACHE_HOME="$PWD/.cache" \
       TMPDIR="$PWD/.cache/tmp" npm_config_cache="$PWD/.cache/npm"
. .venv/bin/activate
```

The `.venv/`, `.cache/`, and multi-GB raw `data/` are all gitignored; only `docs/` is deployed.

## Architecture: two independent layers

1. **Offline Python build (`scripts/`)** — turns raw EMA data into small coloured GLBs +
   JSON manifests in `docs/data/`. A build tool only; never runs in the browser. Python 3.14.
2. **No-build static site (`docs/`)** — `index.html` + `main.js`, Three.js via a CDN
   import-map (no Vite/webpack, no `package.json`). Loads the GLBs and runs the game.

Contract between layers: each GLB node is named `EMAPA<id>` and the sibling `<stage>.json`
manifest lists `{organ_id, display_name, mesh_node, rgb, faces}`. `main.js` matches organs
**across stages by EMAPA id** for the developmental slider, and converts node name
`EMAPA16846` → organ id `EMAPA:16846`.

## The mesh-quality problem (central to this project's history)

EMA models are stacked serial histological sections, so naïve marching-cubes over the
`*_anatomy.nii` label volume produces **terraced / "sliced"** surfaces. Two build paths exist,
in order of preference:

- **`scripts/build_from_stl.py` (preferred)** — `Surfaces.zip` ships per-organ high-res STL
  (`EMAPA<id>_<name>.stl`, one shared frame). Load → colour → pack GLB. Far more detail than
  the volume, especially thin organs. Each STL is itself a **stack of disconnected per-section
  slice-meshes**; genuinely-sliced organs (spinal cord, ribs, vertebrae) are rebuilt into one
  continuous solid by **`scripts/resection.py`**: voxelise → per-section 2-D signed-distance
  fields → natural cubic spline of the SDF across sections (the 1-D biharmonic / minimum-
  curvature interpolant) → marching cubes. Order matters: **resection/densify → decimate →
  biharmonic fair** (never fair the full ~1M-face reconstruction). Slice-count is a bad
  proxy for "needs resection" (the rib has the most slices yet must stay separate), so
  `ORGAN_POLICY` in `build_from_stl.py` hard-codes per-organ decisions from user review:
  rib=raw (individual ribs, merging is wrong anatomy), diaphragm=rough (continuous, no
  fairing), thymus/spleen=resect (merge into one bulk).
- **`scripts/convert_ema.py` (fallback)** — full volume pipeline for stages lacking a
  `Surfaces.zip` (currently TS24). Marching cubes → decimate → **biharmonic surface fairing**
  (libigl cotangent Laplacian + Voronoi mass, solve `(M + λ·L·M⁻¹·L)x = Mx`). Also has the
  older shape-based SDF interpolation (`--interp-factor`, Raya & Udupa 1990). See `METHODS.md`.

`scripts/ema_labels.py` parses the ITK-SnAP `*_anatomy.txt` label file (ITK index 1–359 →
RGB → EMAPA id → name). **Volume values are ITK indices, not EMAPA numbers** — always map
through the label file.

## Common commands

```bash
# Serve the site locally (all it takes — no build step)
cd docs && python3 -m http.server 8765   # -> http://localhost:8765/

# Rebuild a stage from STL surfaces (preferred path)
python scripts/build_from_stl.py \
  --stl-dir data/ema/raw/TS26_EMA102/stl_all \
  --labels  data/ema/raw/TS26_EMA102/TS26_EMA102_anatomy.txt \
  --stage TS26 --out docs/data --resection --max-faces 50000 --lam 0.000005 \
  --align-to scratch_build/ts26.glb   # reference must be a PLAIN (non-Draco) GLB; omit for the anchor

# Rebuild a stage lacking STL, from the volume (fallback)
python scripts/convert_ema.py \
  --nii data/ema/raw/TS24_EMA148/TS24_EMA148_anatomy.nii \
  --labels data/ema/raw/TS24_EMA148/TS24_EMA148_anatomy.txt \
  --stage TS24 --out docs/data --max-faces 60000 --smooth 0 --lam 0 --min-component 30 \
  --only 18010,19143,17701,16688,17331,18767,18768,16974,17577,17838,17503,17185,17021,16846,18321,17373,16728 \
  --align-to scratch_build/ts26.glb
```

Draco compression is applied via `gltf-pipeline` (npm); decode with `gltf-transform cp` for
inspection. There is no test suite — verify by rebuilding and viewing in the browser.

## Gotchas

- **GLTFLoader shares one material instance across meshes** — in `main.js` clone per mesh
  (`obj.material = obj.material.clone()`) before per-organ highlight edits, or the glow leaks
  to every organ.
- **Headless SwiftShader hangs on the Draco decoder worker.** Cannot verify Draco rendering
  headlessly — verify with plain (decoded) GLBs, or judge in a real browser.
- **Don't `pkill -f <pattern>` where the pattern matches your own command line** — it kills
  the invoking shell (e.g. `pkill -f convert_ema` from a shell whose args contain that string).
- **Spotlight organ uses proper depth**, not `depthTest=false` (that removes the position cue
  the user relies on). It is a solid emissive mesh embedded in a translucent grey body.
- Biharmonic fairing needs a cleaned mesh (`merge_vertices` + drop degenerate faces) or
  degenerate cotangents give a singular NaN solve → NaN GLB accessor bounds → the whole GLB
  fails to load. A Taubin fallback + non-finite guard cover residual cases.

## Stages & the shared frame

`main.js` `STAGES`: **TS23 (E15) · TS24 (E16) · TS26 (E18)**, matched by EMAPA id. Quiz uses
TS26 (richest, 20 organs). TS23 & TS26 are built from STL; TS24 from the volume (`--only`
restricts it to the 17 quiz organs). Earlier TS15–TS20 use a different labelling scheme
(excluded); TS25 is a partial delineation (dropped).

The app **only centers+scales each stage — it never rotates**, so every GLB must already be
in one shared frame or the slider spins/flips the embryo. STL and volume sources use
different (and mutually rotated) frames, so every build passes `--align-to <reference.glb>`
(rotate the whole scene onto the reference's body frame: vertex-cloud PCA axes + head/tail
sign from midbrain/tongue/lens vs metanephros/bladder centroids — `stage_frame` /
`body_alignment` in `convert_ema.py`). **TS26 is the anchor frame.** Organ-centroid Kabsch
was tried and does NOT work: embryos curl differently between stages, so the centroid
clouds are not congruent — use the body-PCA method. `scripts/align_stage.py` rotates an
already-built GLB without touching mesh quality.

## Data source & citation

3D models from **eMouseAtlas / EMAP** (CC-BY), Edinburgh DataShare collection 10283/2805.
Cite Richardson L, et al. *EMAGE mouse embryo spatial gene expression database: 2014 update.*
Nucleic Acids Res. 2014;42(D1):D835-44.


claude --resume 90997c0b-dd21-4e35-a6c5-86bcf46ee9d3