## Diagnostic Patterns

| Symptom | Likely causes to investigate |
|---------|----------------------------|
| FWHM well below diffraction limit | Aliasing; try higher resolution, different propagator mode, or both |
| FWHM much larger than estimate | Beam clipping (range too small); wrong propagator mode near focus |
| Asymmetric deviation (x ok, y not) | Astigmatism; try different range/resolution values per axis, or try mode 2 with higher point count |
| Flux loss without apertures | Range too small (beam clipped at edge of mesh); increase range to fix clipping |
| edge_intensity_ratio > 0.01 | Beam reaches mesh boundary; increase range before diagnosing anything else — even if a downstream element will clip the beam, mesh-edge clipping corrupts the wavefront numerically and must be fixed first. **This is never an acceptable tradeoff.** An edge ratio of 0.05+ means significant flux loss and wavefront corruption. Even 0.01 must be actively reduced. Do not leave edge ratios >0.01 with a note that it is "acceptable" — increase the range factor, switch propagation modes, or increase the source mesh until the ratio is below 0.01. |
| edge_intensity_ratio 0.001–0.01 | Low-level beam wings at boundary. Acceptable only for hard-edged aperture diffraction (sinc/Airy wings decay as 1/x and extend very far). Verify the source is aperture diffraction, not grid clipping of a Gaussian beam. For Gaussian beams, this must be zero. |
| FWHM oscillates with resolution | Not converged; try higher resolution, a different propagator mode, or both |
| Idealized element gives same result | Propagation params are likely correct for that element |
| Idealized element gives different result | Realistic element introduces effects (e.g. slope errors, aberrations) that need more careful resolution |
| Result changes when resize factors are smoothed out | Excessive resizing — shrink-then-expand or many consecutive resizes are accumulating interpolation error; reduce the number of resize steps (see "Minimize Resize Operations" in tuning_heuristics.md) |

## Interpretation Guidelines

### Trusting analytical estimates

Not all analytical estimates are equally reliable. The agent should use
the metrics from compute_analytical_estimates to judge how much weight
to give each estimate:

- **Fully illuminated element (beam_to_aperture_ratio ≥ 1.0 or
  beam_na > element_na):** The element's physical size is the limiting
  aperture. The element_na-based diffraction limit is the authoritative
  estimate for the contribution of this element. The beam underfill
  doesn't matter because the element truncates the beam.

- **Underfilled element (beam_to_aperture_ratio << 1.0 or
  beam_na << element_na):** The beam's own divergence sets the effective
  NA, not the element size. The diffraction limit from element_na will
  overestimate the spot size. Use effective_na (which equals beam_na
  in this case) for the diffraction limit.

- **Large object_to_focal_ratio (>>1):** The source is very far from the
  focusing element relative to its focal length. Geometric
  demagnification is tiny (image ≈ f, not image ≈ object × f/object).
  Diffraction almost certainly dominates. If the simulation shows a
  spot much larger than the diffraction limit, suspect demagnification
  is not the cause — look at aberrations or propagation errors instead.

- **Small object_to_focal_ratio (~1-3):** Source is relatively close to
  the optic. The geometric image size can be comparable to the
  diffraction limit. Both contributions matter and the FWHM will be
  somewhere between the two (not simply the max, since they convolve).

- **Fresnel number >>1 at an aperture:** Geometric optics approximation
  is reasonable. Diffraction from the aperture edges is negligible and
  shouldn't significantly broaden the beam beyond the geometric
  prediction.

- **Fresnel number ~1 at an aperture:** Diffraction from the aperture
  is significant. The beam profile will have diffraction fringes and the
  FWHM will differ from the geometric prediction. The Gaussian
  analytical estimate will be unreliable here — rely on convergence
  tests and idealization tests instead.

- **Fresnel number <<1:** Far-field / Fraunhofer regime. The beam
  profile is essentially the Fourier transform of the aperture, and
  the spot size is set entirely by diffraction.

### Wavefront curvature and propagator modes

- **Large wavefront_roc (relative to propagation distance):** The
  wavefront is nearly flat. Mode 0 is typically a good starting point,
  but other modes may still work if convergence is better.

- **Small wavefront_roc (comparable to or less than propagation
  distance):** The quadratic phase varies rapidly across the mesh.
  Modes 1-4 are generally needed to factor out this curvature. The ratio
  distance_from_waist / rayleigh_range indicates how far from flat
  the wavefront is — values >>1 mean strong curvature.

- **Near regime boundaries:** When the beam is near a transition
  (e.g. ~1 Rayleigh range from waist), multiple modes may give
  acceptable results. If one mode shows convergence issues, try
  others — the heuristics are guidelines, not guarantees.

### General principles

- A 10-20% deviation between simulation and analytical estimate is often
  acceptable and explainable (non-Gaussian beam shape, clipping effects).
  The agent should reason about WHY the deviation exists, not just flag it.

- When the analytical estimate is known to be unreliable (e.g. beam is
  heavily clipped, far from Gaussian, Fresnel number ~1), the agent
  should state this and rely more on convergence tests and idealization
  tests for validation.

- **Flux conservation** is a necessary but not sufficient condition for
  correctness. SRW reports intensity in **ph/s/mm²/0.1%bw** — a spectral
  flux *density*. Checking conservation requires integrating over the
  mesh area (the server already does this), not comparing raw peak
  intensities. For fully coherent (monochromatic) simulations the
  0.1%bw factor is constant and cancels in any ratio.

  **Crystal monochromators are an expected exception:** they select a
  narrow bandwidth slice, so total flux *should* drop across the
  monochromator. A flux ratio < 1 after a crystal is normal and should
  not be flagged as a mesh problem.

  If flux is NOT conserved (and no bandwidth-selecting element is
  present), the simulation has a problem — usually the mesh is too
  small. But if flux IS conserved, the simulation may still be wrong:
  good flux only means the mesh captured all the light, not that the
  phase was sampled correctly. When the FWHM disagrees with the
  analytical estimate despite good flux conservation, the agent must
  still explain WHY: is the estimate unreliable (e.g. non-Gaussian
  beam, Fresnel number ~1, heavy clipping)? Is the propagator mode
  inappropriate? Is the resolution too low to resolve the phase
  correctly? Simply noting "flux is conserved" is not enough to close
  the diagnostic.

- Always check edge_intensity_ratio before diagnosing any other issue.
  If the beam is hitting the mesh boundary, nothing else is trustworthy.
  Do not skip this check on the grounds that a downstream element (aperture,
  slit, mirror) will clip the beam anyway. Physical clipping by an optical
  element is a real effect and is computed correctly. Mesh-edge clipping is
  a numerical artifact that corrupts the wavefront phase and amplitude before
  the propagation FFT, invalidating all results at that step and beyond.

- **Grid adequacy after apertures is mandatory.** When an aperture (slit,
  pinhole) dramatically compresses the grid via small range factors, the
  agent MUST verify that the resulting grid has enough points — at minimum
  100 points per axis, ideally 150+. Compute the expected grid size:
  `new_n ≈ old_n × range × resolution`. If this falls below 100, increase
  the resolution factor (Rx, Ry) until ≥150 points are achieved. A coarse
  grid at an aperture (e.g. 50-70 points) produces noisy, artifact-ridden
  profiles at all downstream elements. This is NOT an acceptable tradeoff —
  it must be corrected by increasing resolution factors or source mesh size.

- **Noisy downstream profiles trace back to upstream grid bottlenecks.**
  If a beam profile shows high-frequency oscillations or noise (especially
  in line cuts), the cause is almost always insufficient grid points at an
  upstream aperture or focus. The agent must trace back through the beamline
  to find the element with the fewest grid points and increase resolution
  there, rather than attempting to fix the noise at the downstream element.
