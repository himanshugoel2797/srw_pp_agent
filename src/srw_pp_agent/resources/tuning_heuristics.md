## Propagator Mode Selection Heuristics

1. **Near a waist (within ~1 Rayleigh range):**
   Use mode 0 (standard). The beam phase is relatively flat.

2. **Far from waist, large divergence:**
   Use mode 1 or 2 (quadratic phase subtraction). The quadratic phase
   varies rapidly and needs to be factored out for accurate sampling.
   - Mode 1: allows grid resize (use when beam size changes significantly)
   - Mode 2: fixed grid (use when you need consistent mesh across elements)

3. **Propagating FROM a waist into far field:**
   Use mode 3. Optimized for the waist→far-field transition.

4. **Propagating TO a waist/focus:**
   Use mode 4. Optimized for far-field→waist transition.

**CRITICAL — Modes 3 and 4 invert range/resolution meaning:**

Modes 0/1/2 use 2 FFTs, so range controls window size and resolution
controls point density, as you'd expect.

Modes 3/4 use only 1 FFT. Because a single Fourier transform swaps
spatial and frequency domains, the meaning of the resize parameters
is inverted:
- To increase output **window size** → increase the **resolution** param
- To increase output **point density** → increase the **range** param

This is the most common source of "I changed range but nothing improved"
errors when using modes 3/4. Always double-check which mode is active
before adjusting range or resolution.

## Range and Resolution Heuristics

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
  Increase range factor (2-4×) to capture the full beam, then increase
  resolution if the focal spot is under-resolved.

- **Long drifts far from focus:** The beam expands. May need larger range
  but can often decrease resolution since the phase varies more slowly.

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
