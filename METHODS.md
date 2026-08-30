# Mesh reconstruction & inter-section interpolation

How the eMouseAtlas indexed anatomy volume (`*_anatomy.nii`) becomes the per-organ 3D
meshes in the web app, and specifically how the **cubic-spline interpolation between
histological sections** works. Implemented in `scripts/convert_ema.py`.

## The problem: section terracing

The EMA models are reconstructed by stacking serial 2D histological sections. Each organ
boundary is delineated **independently on each section**, so along the stacking axis the
boundary jumps from one section to the next. When you run marching cubes on the raw label
volume you get a **terraced / "sliced" surface** — a staircase of flat steps perpendicular
to the section axis. Simply smoothing the mesh afterwards blurs the steps but does not
remove them; the underlying geometry is still stepped.

## Why you can't just spline the labels

The volume is a *label* (index) image: each voxel holds an integer organ id. Interpolating
those integers directly is meaningless — half-way between label 16 (aorta) and label 22
(heart atrium) is not "label 19". Categorical data cannot be linearly/cubically
interpolated.

## The fix: shape-based interpolation (Raya & Udupa, 1990)

Interpolate the **shape**, not the labels. For each organ, per stage:

1. **Binary mask.** Take the organ's voxels: `mask = (volume == label_id)`, cropped to its
   bounding box.

2. **Signed distance field (SDF).** Convert the hard mask into a smooth scalar field whose
   zero level-set *is* the organ boundary:

   ```
   sdf(x) = EDT(mask)(x) − EDT(¬mask)(x)
   ```

   where `EDT` is the Euclidean distance transform. `sdf > 0` inside the organ, `< 0`
   outside, `= 0` exactly on the surface. Unlike the 0/1 mask, this field varies smoothly.

3. **Cubic-spline upsampling along the section axis.** Resample the SDF, increasing
   resolution by an integer `factor` **only along the section-stacking axis** (the in-plane
   section resolution is already fine). We use a cubic B-spline (`scipy.ndimage.zoom`,
   `order=3`). Because the SDF is smooth, the spline invents physically plausible
   sub-section boundary positions instead of repeating each section.

4. **Re-threshold.** The interpolated organ is `sdf_up ≥ 0`. This binary volume now has the
   boundary sampled `factor`× finer between the original sections, so the terrace steps are
   replaced by a smooth ramp.

5. **Marching cubes** at `step_size = 1` on the upsampled mask, with the section-axis voxel
   spacing set to `1/factor` so the mesh keeps its true proportions.

6. **Decimate then lightly smooth.** Quadric-decimate to a triangle budget, then a few
   Taubin iterations to remove residual voxel aliasing. (Decimate *before* smoothing —
   smoothing a 200k-triangle raw mesh is far too slow and looks the same.)

Because the interpolation already produces a smooth boundary, only light post-smoothing is
needed, which preserves real anatomical detail better than heavy smoothing of a stepped mesh.

## Auto-detecting the section axis

Different EMA models are stored in different orientations, so the stacking axis is not
always the same array axis (e.g. TS26 → axis 2, TS23 → axis 0). We detect it from the whole
embryo mask by counting **boundary "step" faces per unit length** along each axis:

```
score(a) = Σ |diff(body, axis=a)| / shape[a]
section_axis = argmax_a score(a)
```

The stacking axis carries the terrace steps, so it has by far the most boundary faces per
slice (for TS26: 15181 vs 1408 vs 758). This can be overridden with `--interp-axis`.

## Parameters (`scripts/convert_ema.py`)

| flag | meaning |
|------|---------|
| `--interp-factor N` | upsampling factor between sections (`0`/`1` = off). We use `3`. |
| `--interp-axis A`   | section axis; `-1` = auto-detect (default). |
| `--smooth K`        | Taubin smoothing iterations after decimation (`~10` with interpolation). |
| `--max-faces F`     | per-organ triangle cap via quadric decimation. |
| `--step S`          | marching-cubes step size when interpolation is **off**. |

Performance note: label bounding boxes are found in a single `scipy.ndimage.find_objects`
pass rather than scanning the full volume per organ.

## Reference

Raya SP, Udupa JK. *Shape-based interpolation of multidimensional objects.* IEEE Trans Med
Imaging. 1990;9(1):32–42.
