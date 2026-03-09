## Propagator Mode Selection Heuristics

These are useful starting-point heuristics, not hard rules. When results
don't converge or diagnostics look wrong, try a different mode — even if
the heuristic says otherwise. In particular, drifts can sometimes work
better with a different mode than the one suggested below, especially
near transitions between regimes (e.g. ~1 Rayleigh range from waist).

1. **Near a waist (within ~1 Rayleigh range):**
   Mode 0 (standard) is usually a good starting point. The beam phase
   is relatively flat.

2. **Far from waist, large divergence:**
   Mode 1 or 2 (quadratic phase subtraction) typically works well. The
   quadratic phase varies rapidly and needs to be factored out for
   accurate sampling.
   - Mode 1: allows grid resize (use when beam size changes significantly)
   - Mode 2: fixed grid (use when you need consistent mesh across elements)

3. **Propagating FROM a waist into far field:**
   Mode 3 is often a good choice. Optimized for the waist→far-field transition.

4. **Propagating TO a waist/focus:**
   Mode 4 is often a good choice. Optimized for far-field→waist transition.

**When to deviate from these heuristics:** If convergence tests show
instability, FWHM is far from analytical estimates, or results oscillate
with parameter changes, try neighboring modes. For example, a drift that
is "near" a waist but showing convergence issues with mode 0 may benefit
from mode 1 or 2. Similarly, mode 3/4 can sometimes outperform mode 0
for drifts that are within ~1 Rayleigh range but propagating through a
significant fraction of it.

## Range and Resolution Heuristics

**How range and resolution differ:**

- **Range factor** scales the observation window (spatial extent of the
  mesh) while keeping the number of grid points the same. Increasing
  range makes the window larger with the same point count, so each
  pixel/point covers a larger area (coarser pitch). This adds no
  computational cost.

- **Resolution factor** changes the number of grid points while keeping
  the window size the same. Increasing resolution adds more points within
  the same window, making each pixel/point smaller (finer pitch). This
  increases computational cost.

**Practical consequence:** Increasing range to accommodate a larger beam
also makes the mesh coarser (larger pitch). If the original resolution
was more than sufficient, this may be fine — the extra room from a
larger range can absorb a coarser pitch without affecting accuracy.
Conversely, if the mesh was already borderline for resolving features,
increasing range without also increasing resolution will degrade
sampling. Always check whether the resulting mesh pitch is still
adequate for the physics (see Element Sampling Requirements below).

- **Range factor:** The observation window should be ≥3× the expected beam
  size (FWHM) to avoid clipping artifacts. If flux is being lost, increase
  range first.

- **Wavefront edge margin:** The outer ~10% of the mesh on each side
  should have zero (or negligible) intensity. Check edge_intensity_ratio
  in the simulation output — if it is significantly above zero, the beam
  is spilling off the mesh and results are unreliable. Increase the range
  factor until the edges are clean. This is a necessary (not sufficient)
  condition for correctness.

- **Resolution factor:** Start at 1.0. If FWHM is below diffraction limit
  or oscillates, increase resolution. Values above 2-3 are rarely needed
  and get expensive fast.

- **After focusing elements:** The beam size changes dramatically.
  Increase range factor (2-4×) to capture the full beam. Because
  increasing range keeps the point count fixed, the mesh pitch gets
  coarser — check whether the focal spot is still adequately resolved.
  If not, increase resolution as well.

- **Long drifts far from focus:** The beam expands. May need larger range
  but can often decrease resolution since the phase varies more slowly.
  This is a case where the range increase "pays for itself": the beam is
  larger and smoother, so the coarser pitch from a bigger window is
  perfectly acceptable, and you may even be able to drop resolution to
  save compute.

## Element Sampling Requirements

Before worrying about propagation accuracy, the computational mesh must
have enough points to faithfully represent each optical element's
transmission/reflection profile. If the grid is too coarse, sharp
features get rounded off and the element effectively becomes a different
optic than what was intended.

- **Zone plates:** The mesh must resolve the outermost zone. The
  outermost zone width is typically tens of nanometers, while the beam
  window may span hundreds of microns. This often requires a very large
  resolution rescale (potentially 10-50×) immediately before the zone
  plate. Without this, the fine zone structure is smeared out and the
  zone plate behaves like a blurry approximation of itself.

- **Diffraction gratings:** The mesh must resolve individual grating
  lines. Similar to zone plates, the pitch of the grating (line spacing)
  sets the minimum sampling requirement. The number of points across the
  beam window must be sufficient that the grating period spans multiple
  pixels.

- **Apertures and obstacles:** Sharp edges must land on or very near
  grid points. If the mesh is too coarse, the edge position gets rounded
  to the nearest grid point, effectively changing the aperture size. For
  a circular aperture, this also distorts the shape. Ensure enough
  resolution that the edge position error is small relative to the
  feature size.

- **Mirrors at grazing incidence:** The projected footprint on the
  mirror surface may be very elongated. The mesh needs to resolve
  any surface features (figure errors, slope errors) along the
  tangential direction. For flat mirrors this is less critical, but
  for curved mirrors the sampling along the tangential direction
  affects how well the curvature is represented.

**General rule:** Before an element with fine spatial structure,
check whether the current mesh pitch (window_size / num_points) is
small enough to resolve the element's smallest feature. If not,
increase the resolution rescale factor for the preceding propagation
step. This is a hard sampling requirement — no choice of propagator
mode will compensate for under-resolving the element itself.

## Red Flags
- FWHM < 0.5× diffraction limit → almost certainly aliasing
- Flux ratio < 0.8 without apertures → beam clipped by mesh range
- edge_intensity_ratio > 0 → beam extends to mesh boundary, increase range
- FWHM changes >10% when resolution changes by 0.5× → not converged
