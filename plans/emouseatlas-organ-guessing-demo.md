# Plan: "Guess the Organ" — EMA/EMAP Mouse Embryo 3D Demo

An interactive 3D demo for college students. Show a mouse embryo reconstructed from the
**eMouseAtlas (EMA / EMAP)** anatomy data, isolate one organ at a time with its label
hidden, and let students guess which organ it is via **multiple choice**. Reveal the answer
with a short fact, keep score, and **scrub a time slider across Theiler stages** to watch
organs appear and grow.

**Decisions (locked):** multiple-choice answers · multi-stage with a developmental time
slider · **hosted on GitHub Pages**.

This narrows the broad 4D vision in [`draft.md`](draft.md) down to a single, shippable
classroom demo built on the EMA anatomy meshes only (no live-imaging or transcriptomics
for v1).

---

## Why EMA fits this demo

- EMA has **3D reconstructed models for Theiler Stages TS07–TS20 and TS26**, each with
  **delineated (segmented + labelled) anatomical components** — i.e. every organ is a
  named region, which is exactly what a "guess the organ" game needs.
- Data is **CC-BY licensed** (attribution required) and downloadable from eMouseAtlas and
  Edinburgh DataShare.
- **Data formats (verified by download):** the DataShare collection *"3D Embryo Models and
  Anatomy Delineations"* (handle 10283/2805, early→late gestation) provides each model in
  **Woolz (WLZ) + NIfTI** volumes, plus a per-model `Surfaces.zip`. **Important correction:**
  inside `Surfaces.zip` the *per-organ* surfaces are **Woolz `.wlz` surface objects, NOT STL**
  — only the whole-embryo `reference.stl` is STL. So "STL → glTF" does **not** work for
  individual organs; those need conversion. Pull data from the **DataShare REST API**, not the
  per-Theiler-stage pages (those only offer the raw WLZ volume + huge JPG sections).
- **Confirmed for TS26 (EMA102, E18.0):** `Surfaces.zip` contains **359 per-organ surface
  files** named `EMAPA<id>_<organ_name>.wlz`, matching **359 labelled components** in
  `TS26_EMA102_anatomy.txt` — an ITK-SnAP label file giving, per component, an index,
  **ready-made RGB colour**, EMAPA ontology ID, and human-readable organ name. So the organ
  list, names, and colours are handed to us. Recognizable organs present: heart, liver, lung,
  kidney, brain/cerebellum, bladder, gallbladder, femur, forebrain, etc.
- **Chosen conversion route (avoids compiling Woolz):** download each model's **`*_anatomy.nii`
  indexed volume** and run **`nibabel` + `skimage.measure.marching_cubes` per label ID** →
  one mesh per organ → decimate → glTF. This is pure Python and reuses the label/colour map.
  The per-organ `.wlz` surfaces are the fallback if we later build Woolz (`WlzExtFFConvert`).

**Stages to convert for the slider:** target **~3–4 stages** spanning development, e.g.
**TS15 (~E10) · TS18 (~E11) · TS20 (~E12) · TS26 (~E18.5)**. TS26 is the "hero" stage for the
quiz (organs — brain, heart, lungs, liver, kidney, gut, limbs — are large and recognizable);
earlier stages show the same organs forming as the student scrubs back in time. Start with
**one stage (TS26) end-to-end**, then add the rest once the pipeline works.

---

## Success criteria (definition of done for v1)

- [ ] A browser page loads the embryo where **each guessable organ is a separate,
      individually colourable 3D mesh**.
- [ ] **Quiz mode:** one organ is isolated/highlighted, its name hidden; student picks from
      **3–4 multiple-choice options**; correct/incorrect feedback + a one-line fact shown.
- [ ] Score across a round of N organs; rotate/zoom the embryo with the mouse.
- [ ] **Time slider** across ≥3 Theiler stages showing the same organs develop.
- [ ] **Deployed and reachable on GitHub Pages** (correct base path, assets load over HTTPS).
- [ ] Attribution/citation for EMA shown in the UI (CC-BY compliance).

---

## Stages

### Stage 1: Data acquisition & mesh conversion (highest risk — do first)

**Goal:** A folder of per-organ meshes for one stage, in a web-friendly format.

**Tooling constraint:** `/home` is 100% full — **do not install anything there.** Create the
Python venv on the Workbench drive and redirect caches to it, e.g. `python -m venv
data/../.venv` under the project and export `PIP_CACHE_DIR`, `XDG_CACHE_HOME`, `TMPDIR` to
project-local paths so no build/cache bytes land on `/home`.

**Steps:**

1. **Download (DONE for TS26):** via the DSpace REST API of collection **10283/2805**, the
   TS26 model **EMA102** (item handle 10283/2841) is downloaded to
   `data/ema/raw/TS26_EMA102/`: `Surfaces.zip` (359 per-organ `.wlz` + `reference.stl`),
   `TS26_EMA102_anatomy.txt` (label/colour/name map), `README/model_info/citation`. The multi-
   GB `*_anatomy.nii` / `*_reference.nii` / `.wlz` volumes are **not yet** downloaded.
2. **Get the label volume:** download `TS26_EMA102_anatomy.nii` (~1.19 GB) — the indexed
   anatomy volume needed for marching cubes. (Bitstream URL captured in `raw/ts26_bitstreams.json`.)
3. **Convert (primary path — pure Python, no Woolz build):** with `nibabel` load the indexed
   volume; parse `*_anatomy.txt` for `index → (name, EMAPA id, RGB)`; for each label run
   `skimage.measure.marching_cubes`, smooth + decimate with `trimesh` (target <~50k tris),
   assign the label's RGB. Fallback: build Woolz and `WlzExtFFConvert` the per-organ `.wlz`.
4. **Package:** export **one glTF/GLB per stage** (Draco) with each organ as a named node,
   plus a per-stage JSON manifest `{ organ_id (EMAPA), display_name, mesh_node, rgb, fact,
   difficulty }`. Use the **EMAPA id as the stable organ_id across stages** so the slider maps
   the same organ over time.

**Success:** `ts26.glb` + `ts26.json` exist; a quick viewer shows ≥6 named organs as distinct
meshes. (Then repeat for the other stages.)
**Verify:** open the GLB in an online glTF viewer; count and name the separable organs.
**Status:** ✅ Complete for TS26 — NIfTI + marching-cubes route works; `docs/data/ts26.glb`
(20 curated organs, 324k faces, 6.5 MB) + `ts26.json` produced. Other stages for the slider
still to do.

### Stage 2: 3D viewer skeleton
**Goal:** Load and orbit the embryo in the browser.
**Steps:** Vite + Three.js app; `GLTFLoader` + Draco; `OrbitControls`; per-organ materials
driven by `organs.json`; hover → highlight organ; basic lighting/background.
**Success:** All organs render; hovering highlights the organ under the cursor; smooth on a
laptop iGPU.
**Verify:** manual — rotate, zoom, hover each organ; check 60fps-ish.
**Status:** ✅ Complete — no-build static Three.js app (`docs/`, CDN import-map, no Vite
needed). Loads GLB, orbits, auto-rotates. Note: per-organ material must be **cloned** (GLTF
shares one material instance) or highlight edits leak across organs.

### Stage 3: Quiz game logic
**Goal:** The actual "guess the organ" loop.
**Steps:** Round = shuffled list of target organs. For each: dim all, spotlight/glow the
target, hide its label; present 3–4 multiple-choice buttons (distractors sampled from other
organs). On answer → colour green/red, reveal name + fact, update score; "Next"; end-of-round
score screen with "Play again". Small state machine (`intro → question → reveal → summary`).
**Success:** A full round is playable start to finish; score is correct; distractors never
include the answer twice.
**Verify:** play 3 rounds; deliberately answer wrong/right; confirm scoring and reveal text.
**Status:** ✅ Complete — 10-organ rounds, 4 multiple-choice, target organ glows *through* the
faint grey ghost embryo (target uses `depthTest=false` + high `renderOrder`), reveal + fact,
score, summary, play-again. Facts written for all 20 organs.

### Stage 4: Developmental time slider
**Goal:** Scrub across stages to watch the same organs appear/grow.
**Steps:** UI slider over the converted stages (TS15→TS26); on change, swap/crossfade the
active GLB and re-bind the per-stage manifest; keep camera and the selected-organ ID stable
across stages (consistent IDs from Stage 1). Preload GLBs or lazy-load with a spinner.
**Success:** Moving the slider changes the embryo to the correct stage; picking "heart" stays
"heart" as you scrub.
**Verify:** manual — step through every stage; confirm organ identity persists and no leaks.
**Status:** ✅ Done — 3-stage slider **TS23 (E15) · TS24 (E16) · TS26 (E18)** (later stages
share the same EMAPA-labelled organs; TS15–TS20 use a different scheme so were excluded; TS25
EMA149 was a partial delineation, dropped). Separate **Explore** mode with organ chips +
deep-link params. Organ identity keyed by EMAPA id across stages. GLBs Draco-compressed
(~180–350 KB each). Note: my headless test browser hangs on Draco's decoder worker (SwiftShader
quirk) — Draco data verified valid via `gltf-transform` decode + app verified via plain GLBs;
**Draco-in-real-browser to be confirmed by user.**

### Stage 5: Polish & deploy to GitHub Pages
**Goal:** Presentable, robust, and live on the web.
**Steps:** Title/instructions screen; large readable UI (projector-friendly); EMA attribution
+ citation footer; configure Vite `base: '/<repo>/'` so asset paths resolve on Pages; build
to `dist/` and publish via a **GitHub Actions Pages workflow** (or `gh-pages` branch); verify
Draco/GLB assets load over HTTPS and `.glb` is served with a correct MIME type. Smoke-test the
live URL on a fresh browser and on the demo laptop.
**Success:** The public Pages URL loads, plays a full round, and the slider works — with no
console/network errors.
**Verify:** open the live URL in an incognito window; a colleague plays it without help.
**Status:** 🟡 Deployed — **live at https://yuehhua.github.io/mouse-embryo-vis/** (repo
`yuehhua/mouse-embryo-vis`, Pages from `main` `/docs`, `.nojekyll`, relative paths so the
`/mouse-embryo-vis/` subpath works with no base config). Remaining polish: bigger
projector-friendly UI, intro screen, Draco compression of the GLB. Slider (Stage 4) still
pending other stages.

---

## Tech stack (kept minimal)

- **Frontend:** Three.js + `OrbitControls` + `GLTFLoader`/Draco; Vite; vanilla JS/TS (no
  heavy framework needed). Matches the `draft.md` recommendation.
- **Data pipeline (offline, one-time):** Python — Woolz/PyWoolz **or** `scikit-image`
  (marching cubes) + `trimesh`/`pygltflib` for mesh export & Draco/glTF packaging.
- **No backend:** everything static — a good fit for **GitHub Pages** (set Vite `base` to the
  repo name; publish `dist/` via GitHub Actions).

## Open questions to confirm before/early in Stage 1

1. Are the collection-10283/2805 STL surfaces split **per anatomy component** (one mesh per
   organ) with a discoverable file→organ-name mapping, and do our target stages have
   delineated anatomy? (First thing to verify when a real download is in hand.)
2. Which **~8–12 organs** to include for the target audience (recognizability vs. challenge)?
3. Exactly which stages for the slider — is TS15/TS18/TS20/TS26 the right spread, or fewer?

*Resolved:* per-anatomy **STL surfaces are provided** (DataShare 10283/2805) → likely
STL→glTF, no voxel pipeline · multiple-choice interaction · developmental time slider in
scope · deploy target is GitHub Pages.

## Risks

- **WLZ conversion** is the make-or-break — mitigated by Stage-1-first ordering and the
  EMAP-contact fallback.
- **Mesh size/perf** on classroom hardware — mitigated by decimation + Draco.
- **Segmentation granularity** — some EMA labels are fine sub-structures; may need to merge
  child labels up to whole-organ level using the EMA anatomy ontology tree.

## Attribution (required — CC-BY)

Credit eMouseAtlas/EMAP and cite the informatics paper in the UI and README, e.g.
Armit C. et al., *eMouseAtlas informatics: embryo atlas and gene expression database*
(PMC4602050). Data © University of Edinburgh, CC-BY.

## Sources

- [EMAP home / versions](https://www.emouseatlas.org/emap/home.html)
- [Theiler-stage downloads (WLZ volumes, JPG sections)](https://www.emouseatlas.org/emap/ema/theiler_stages/downloads/ts18_downloads.html)
- [Edinburgh DataShare — e-Mouse Atlas top collection](https://datashare.ed.ac.uk/handle/10283/821)
- [DataShare — 3D Embryo Models and Anatomy Delineations (WLZ + NIfTI + STL)](https://datashare.ed.ac.uk/handle/10283/2805)
- [eMouseAtlas informatics (citation)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4602050/)
- [STL/Blender conversion precedent (bioRxiv)](https://www.biorxiv.org/content/10.1101/2020.11.23.393991v1.full)
