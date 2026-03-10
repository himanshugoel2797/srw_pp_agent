## Propagator Mode Selection Heuristics

These are useful starting-point heuristics, not hard rules. When results
don't converge or diagnostics look wrong, try a different mode — even if
the heuristic says otherwise. In particular, drifts can sometimes work
better with a different mode than the one suggested below, especially
near transitions between regimes (e.g. ~1 Rayleigh range from waist).

**Default recommendation: prefer mode 1 for drift spaces.** The mode 1
propagator (quadratic phase subtraction with grid resize) is substantially
more robust to undersampling than mode 0, because it factors out the
dominant quadratic phase curvature before the FFT step. This means the
residual phase varies more slowly and can be faithfully represented on a
coarser grid. For drift spaces — which make up the majority of
propagation steps — mode 1 is a safe default that tolerates modest grids
well. Reserve mode 0 for cases where the wavefront is genuinely flat
(very near a waist, within a fraction of the Rayleigh range) and you
have confirmed that mode 0 converges on the available grid.

1. **Near a waist (within ~1 Rayleigh range):**
   Mode 0 (standard) can work when the beam phase is relatively flat,
   but mode 1 is often equally good or better here because of its
   robustness. Only prefer mode 0 if mode 1 shows issues (rare) or you
   need to avoid grid resizing for a specific reason.

2. **Far from waist, large divergence:**
   Mode 1 or 2 (quadratic phase subtraction) is strongly preferred. The
   quadratic phase varies rapidly and needs to be factored out for
   accurate sampling.
   - Mode 1: allows grid resize (use when beam size changes significantly)
   - Mode 2: fixed grid (use when you need consistent mesh across elements,
     e.g. astigmatic beamlines where the two axes have very different
     Rayleigh ranges)

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
  mesh) while keeping the point spacing (pitch) the same. Increasing
  range makes the window larger by adding more grid points at the same
  pitch. This increases computational cost.

- **Resolution factor** changes the point spacing (pitch) while keeping
  the window size the same. Increasing resolution makes each pixel/point
  smaller (finer pitch) by adding more points within the same window.
  This also increases computational cost.

**Practical consequence:** Increasing range to accommodate a larger beam
preserves the existing point spacing — the mesh simply gets more points
to cover the wider window. Resolution stays the same automatically, so
there is no trade-off between window size and sampling quality. However,
larger meshes cost more to compute, so only increase range as much as
needed (≥3× beam FWHM is a good target).

- **Range factor:** The observation window should be ≥3× the expected beam
  size (FWHM) to avoid clipping artifacts. If flux is being lost, increase
  range first.

- **Wavefront edge margin:** The outer ~10% of the mesh on each side
  should have zero (or negligible) intensity. Check edge_intensity_ratio
  in the simulation output — if it is significantly above zero, the beam
  is spilling off the mesh and results are unreliable. Increase the range
  factor until the edges are clean. This is a necessary (not sufficient)
  condition for correctness.

  **This applies even when a downstream element will clip the beam.**
  A physical aperture (slit, mirror, zone plate) clips the beam correctly
  as part of the optics. Mesh-edge clipping is a numerical artifact: it
  truncates the wavefront before the FFT propagation step, introducing
  errors into the phase and amplitude that corrupt all subsequent results.
  The mesh must be wide enough to contain the full beam at every
  propagation step, regardless of what downstream optics do to it.

- **Resolution factor:** Start at 1.0. If FWHM is below diffraction limit
  or oscillates, increase resolution. Values above 2-3 are rarely needed
  and get expensive fast.

- **Large grid at a drift is a mode smell.** If a drift requires a very
  large number of grid points (high range or resolution factors) to
  converge, the propagator mode may be wrong — not the grid size. A
  correct mode choice factors out the dominant phase curvature, allowing
  the propagation to succeed on a modest grid. Needing an unusually large
  grid at a drift (absent a demanding downstream element like a zone plate
  or fine sample feature) is a sign that the quadratic phase is not being
  handled properly. Try a different mode before increasing the grid.

- **After focusing elements:** The beam size changes dramatically.
  Increase range factor (2-4×) to capture the full beam. Since
  increasing range preserves point spacing, the focal spot resolution
  is maintained — but the larger mesh will cost more to compute.

- **Long drifts far from focus:** The beam expands. May need larger range
  but can often decrease resolution since the phase varies more slowly.
  Decreasing resolution (coarser pitch) saves compute, which can offset
  the cost of the larger range.

## Minimize Resize Operations

Every resize (range or resolution factor ≠ 1) requires interpolation of
the wavefront onto a new grid, which introduces small numerical errors.
These errors accumulate: a sharp reduction followed shortly by a large
expansion (or vice versa) compounds interpolation losses from both steps.
The goal is to achieve a correct result with the **fewest resizes**.

- **Prefer increasing range and resolution upstream, once.** It is far
  better to set a generous range and resolution at an early element (e.g.
  the first optical element) and carry that grid through the beamline,
  than to repeatedly increase and decrease range/resolution at successive
  elements. Each resize is an interpolation step that introduces error.
  If you know the beam will expand downstream (e.g. a long drift after
  the source), increase the range *before* that expansion — at the first
  optical element or the first drift — rather than chasing the expansion
  with incremental increases at each subsequent element. Similarly, if a
  downstream element requires fine pitch (e.g. a zone plate or grating),
  increase resolution upstream of it once rather than applying multiple
  smaller boosts along the way.

  **Do not increase the source point count (nx, ny) for propagation
  purposes.** The source mesh point count controls the radiation
  calculation sampling and should be left at its default. If more grid
  points are needed downstream, increase the resolution factor at the
  first optical element instead. Increasing the source *range* (spatial
  window) is acceptable when the beam is being clipped at the source.

- **Avoid shrink-then-expand patterns.** Shrinking the range or
  resolution at one element and then expanding it by a large factor a
  few elements later discards grid points (and the information they
  carry) only to re-create them by interpolation. The re-created points
  are less accurate than the originals. For example, reducing range by
  0.1× at a pinhole and then expanding by 60× at the next drift loses
  precision compared to a more moderate shrink (0.3×) followed by a
  smaller expansion (12×). Prefer the gentlest resize that still
  satisfies the edge-intensity and sampling requirements.

- **Combine resizes when possible.** If two consecutive elements both
  need a resize in the same direction (e.g. both need range expansion),
  apply the full factor at the first element rather than splitting it
  across two steps. Each resize is an interpolation pass; fewer passes
  mean less accumulated error.

- **Leave factors at 1.0 unless there is a clear reason to change
  them.** Do not resize "just in case." Only adjust range when
  edge_intensity_ratio indicates clipping, or when the beam size is
  about to change dramatically (focusing, aperture clip). Only adjust
  resolution when the mesh pitch is too coarse for the beam or element
  features.

- **Watch for cascading grid bloat.** Range and resolution factors
  compound multiplicatively through the beamline. A 1.8× V range
  expansion early on propagates through every subsequent element,
  potentially creating an unnecessarily large grid at the end. If an
  early expansion is needed, look for a natural place downstream
  (e.g. an aperture that clips the beam) to bring the range back
  down, rather than carrying the enlarged grid through the entire
  beamline.

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

## Grid Point Budget at Apertures

When a pinhole, slit, or other aperture dramatically compresses the mesh
range, the number of grid points can drop to dangerously low levels.
Range and resolution factors compound: `new_n ≈ old_n × range × resolution`.

**Hard minimum: 100 points per axis. Target: 150+ points per axis.**

The agent MUST compute the expected post-aperture grid size before
finalizing parameters. If the grid would fall below 100 points in either
axis, the agent MUST increase the resolution factor (Rx or Ry) to
compensate. Leaving a coarse grid (e.g. 50-70 points) is never acceptable
— it produces noisy, artifact-ridden profiles at ALL downstream elements
and cannot be fixed downstream.

**Strategy for tight apertures:**
- Use aggressive range compression (rx, ry << 1) to match the aperture
  size — this is correct and necessary.
- Compensate with resolution boost (Rx, Ry > 1) to maintain point count.
- If the upstream grid is too small to provide enough points even with
  large Rx/Ry, increase the resolution factor at the first optical
  element (e.g. S0) rather than changing the source point count (nx, ny).
  The source mesh point count is set by the radiation calculation and
  should not be tweaked for propagation convenience. Increasing the
  source range (to cover a wider spatial window) is acceptable, but
  adding more source points changes the radiation sampling and can have
  unintended side effects. Push extra points into the beamline via
  resolution factors at the first element instead.
- After computing expected grid size, also verify that the pitch
  (range / n_points) is fine enough to resolve the beam: at least 10-20
  points across the beam FWHM at the aperture.

## Diffraction Limit Considerations

The simple diffraction-limit estimate (0.44λ/NA) based on a single
element's numerical aperture is **not** a hard lower bound on the
achievable spot size. The actual diffraction limit depends on the
wavefront's radius of curvature at the focusing element, which is set
by the full upstream optical system — not just the element itself.

For example, if an upstream optic partially collimates the beam or
introduces wavefront curvature, the effective NA at a downstream
focusing element can differ from the element's geometric NA. A converging
beam arriving at a focusing mirror has a different effective numerical
aperture than a plane wave arriving at the same mirror. The beam's
radius of curvature encodes the cumulative effect of all upstream optics,
and this is what determines the actual diffraction-limited spot size.

In practice:
- The per-element diffraction limit from `compute_analytical_estimates`
  is a useful *reference* for the contribution of that element, but the
  actual achievable spot size depends on the coherent interaction of the
  full beamline.
- A simulation result slightly below a single element's diffraction
  limit does not automatically indicate aliasing — it may reflect the
  combined effect of multiple optical elements. Conversely, a result
  well above the single-element limit may indicate aberrations or
  clipping effects from upstream optics.
- When diagnosing whether a spot size is physically reasonable, consider
  the wavefront curvature and effective NA at the focal plane, not just
  the geometric acceptance of the nearest focusing element.

## Red Flags
- FWHM well below the expected diffraction limit for the full optical
  system → likely aliasing (but verify against the effective NA, not
  just a single element's geometric NA)
- Flux ratio < 0.8 without apertures → beam clipped by mesh range
- edge_intensity_ratio > 0.01 → beam extends to mesh boundary, increase
  range; this must be fixed regardless of whether a downstream element
  clips the beam (physical aperture clipping ≠ numerical mesh-edge
  clipping). **An edge ratio >0.05 (5%) is a critical failure** — it means
  substantial flux loss and wavefront corruption. Do not document these as
  "acceptable tradeoffs." Fix them by increasing range, switching modes,
  or enlarging the source mesh. Values of 0.001-0.01 are acceptable ONLY
  for hard-edged aperture diffraction (sinc/Airy wing spillover).
- Grid < 100 points in any axis at any element → insufficient sampling;
  increase resolution factor at the first optical element (not the source
  point count). This produces noisy profiles downstream and is never
  acceptable.
- FWHM changes >10% when resolution changes by 0.5× → not converged
- Sharp range/resolution decrease followed by large increase (or vice versa)
  within a few elements → excessive resizing; interpolation error accumulates
  from both steps. Prefer fewer, gentler resizes that achieve the same net
  effect
- Drift requiring very large grid (high range/resolution) to converge →
  likely wrong propagator mode; a correct mode factors out the dominant phase
  curvature and should not need an oversized grid. Exception: drifts
  immediately before elements with fine spatial structure (zone plates,
  gratings, detailed samples) may legitimately need high resolution
- Noisy or oscillating line profiles at downstream elements → trace back to
  find the upstream element with fewest grid points (often an aperture) and
  increase resolution there. Do not attempt to fix noise at the downstream
  element — the damage is done upstream.
