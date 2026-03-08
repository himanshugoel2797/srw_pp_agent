# SRW Beamline Propagation Tuning — MCP Server & Agent Design

## 1. Overview

This document describes the architecture of an MCP (Model Context Protocol) server that wraps SRW's Python bindings (`srwpy`) and the prompting strategy for an AI agent that iteratively tunes wavefront propagation parameters and generates validity reports for beamline definitions.

**Core loop:** The agent receives a beamline definition → builds analytical expectations → runs simulations with candidate propagation parameters → compares results to expectations → diagnoses discrepancies → adjusts parameters or modifies the beamline → repeats until results are physically consistent and computationally efficient.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────┐
│                   LLM Agent                     │
│  (system prompt + structured reasoning chain)   │
└──────────────────────┬──────────────────────────┘
                       │ MCP protocol (JSON-RPC)
                       │
┌──────────────────────▼──────────────────────────┐
│              MCP Server (Python)                 │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │  Beamline  │  │ Simulation │  │ Analysis   │ │
│  │  Manager   │  │  Runner    │  │  Engine    │ │
│  └────────────┘  └────────────┘  └────────────┘ │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │ Analytical │  │    Data    │  │  Session   │ │
│  │ Estimator  │  │ Aggregator │  │  State     │ │
│  └────────────┘  └────────────┘  └────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │
                  ┌────▼────┐
                  │  srwpy  │
                  └─────────┘
```

### 2.1 Session State

The server maintains a session object that persists across tool calls within a conversation:

```python
@dataclass
class TuningSession:
    original_definition: dict            # Beamline as originally provided by user
    canonical_definition: dict           # Updated by edit_beamline (permanent corrections)
    working_beamline: dict               # canonical + probes + idealizations + truncations
    propagation_params: dict[str, dict]   # element_label -> {mode, range_x, range_y, resolution_x, resolution_y}
    source_wavefront: SRWLWfr           # Cached source wavefront
    simulation_history: list[SimRun]     # All runs with params, results, timestamps
    analytical_estimates: dict           # Cached expectations per observation point
    edit_log: list[str]                  # Log of permanent edits (edit_beamline)
    active_probes: dict[str, dict]       # probe_id -> aperture probe definition (temporary)
    idealized_elements: dict[str, dict]  # label -> original element (for restore)
    truncated_drifts: dict[str, float]   # label -> original length (for restore)
```

The key distinction: `canonical_definition` accumulates permanent corrections from `edit_beamline` and is returned to the user at the end. `working_beamline` is rebuilt from canonical + any active probes/idealizations/truncations and is used for simulation. Probes, idealizations, and truncations never touch the canonical definition.

---

## 3. MCP Tools

### 3.1 Beamline Management

#### `load_beamline`

Parses and loads a beamline definition, caches the source wavefront, and returns a structured summary.

```
Input:
  beamline_definition: dict | str   # SRW beamline dict or path to JSON/Python file

Output:
  {
    source_type: "undulator" | "bending_magnet" | "gaussian",
    photon_energy_eV: float,
    source_mesh: {
      nx: int, ny: int,              # Initial grid dimensions
      range_x_mm: float,             # Initial horizontal window
      range_y_mm: float,             # Initial vertical window
      pitch_x_um: float,             # Initial horizontal point spacing
      pitch_y_um: float              # Initial vertical point spacing
    },
    elements: [
      {
        index: int,
        type: str,                  # "drift", "lens", "mirror", "aperture", "crl", ...
        label: str,                 # Unique label, used to reference this element in all tools
        key_params: dict,           # e.g. focal_length, grazing_angle, acceptance
        cumulative_distance_m: float,
        current_propagation_params: {mode, range_x, range_y, resolution_x, resolution_y},
        smallest_feature_size_m: float | null  # Smallest spatial feature the mesh must resolve
                                               # e.g. outermost zone width for zone plates,
                                               # grating pitch for gratings, null for drifts/lenses
      }
    ],
    total_length_m: float
  }
```

The `source_mesh` is derived from the source definition and determines the starting grid for propagation. The agent should check whether the initial mesh pitch is adequate for the first element downstream (e.g., if there's a zone plate early in the beamline, the source mesh may need to be overridden via `mesh_params` in `run_propagation`).

#### `edit_beamline`

Makes permanent corrections to the beamline definition. These changes persist and are reflected in the final beamline definition returned to the user. Use this when the beamline definition itself needs fixing — a missing aperture, a wrong drift length, an incorrect parameter.

```
Input:
  action: "insert" | "remove" | "edit"
  target_label: str                    # Element label to act on (for remove/edit)
  insert_before: str | None            # For insert: place new element before this label
  element_definition: dict | None      # For insert/edit; must include a unique label

Output:
  updated_elements: list               # Same structure as load_beamline output
  updated_definition: dict             # The corrected beamline definition
```

Use cases:
- Add a physically real aperture before a KB system that was missing from the definition
- Correct a drift length or mirror parameter that was wrong
- Remove an element that shouldn't be in the beamline

These changes update the canonical beamline definition. At the end of a session, the user receives the corrected definition with all `edit_beamline` changes applied.

#### `probe_aperture`

Temporarily inserts or removes a diagnostic aperture in the beamline. Probes do not modify the canonical beamline definition — they exist only for hypothesis testing.

Note: observation planes are not needed as a probe type. The server always returns before/after metrics at every element boundary in `run_propagation`. For mid-drift observation, use `truncate_drift` and pass `up_to_element` on `run_propagation`.

```
Input:
  action: "insert" | "remove" | "remove_all"
  probe_id: str | None                 # For action="remove" — which probe to remove
  at_element: str | None               # Element label — aperture goes before this element
  aperture_params: dict | None         # {shape: "circular"|"rectangular", size_x_m, size_y_m}

Output:
  probe_id: str | null                 # ID of inserted probe (null for remove actions)
  active_probes: [                     # All currently inserted probe apertures
    {
      probe_id: str,
      at_element: str,
      aperture_params: dict
    }
  ]
  updated_elements: list
```

Use cases:
- Insert a test aperture before a KB mirror to check whether clipping explains a downstream result
- Insert a test aperture at a suspected clipping point to see if it changes the result
- Remove probes when done to return to the real beamline

Probes are automatically excluded from the final beamline definition.

#### `truncate_drift`

Temporarily shortens a drift element to inspect the beam at an intermediate point within that drift. The original drift length is preserved and can be restored. Does not introduce new propagation boundaries.

```
Input:
  drift_label: str                     # Label of the drift element to truncate
  truncated_length_m: float            # Temporary new length

Output:
  original_length_m: float
  truncated_length_m: float
  updated_elements: list
```

#### `restore_drift`

Restores a previously truncated drift to its original length.

```
Input:
  drift_label: str

Output:
  restored_length_m: float
  updated_elements: list
```

#### `idealize_element`

Replaces one or more focusing elements with their ideal thin-lens + circular-aperture equivalents. This is a key validation technique: if the simulation result doesn't change significantly when an element is idealized, the propagation parameters are likely correct for that element. If it does change, the realistic element may be introducing effects that need more careful treatment.

The idealization is deterministic and hardcoded per element type:

| Realistic element | Ideal replacement |
|---|---|
| Mirror (curved) | Thin lens (same f) + rectangular aperture (tangential × sagittal size, projected at grazing angle) |
| Zone plate | Thin lens (same f) + circular aperture (zone plate diameter) |
| CRL stack | Single thin lens (same effective f) + circular aperture (physical aperture of CRL) |
| Compound / multilayer mirror | Thin lens (same f) + appropriate aperture |

```
Input:
  element_labels: list[str] | "all"    # Which focusing elements to idealize
  
Output:
  idealizations_applied: [
    {
      element_label: str,
      original_type: str,
      ideal_focal_length_m: float,
      ideal_aperture_type: str,        # "circular" | "rectangular"
      ideal_aperture_size_m: float | [float, float]
    }
  ]
  updated_elements: list
```

#### `restore_elements`

Reverts idealized elements back to their original realistic definitions.

```
Input:
  element_labels: list[str] | "all"

Output:
  restored_elements: list[str]
  updated_elements: list
```

#### `get_beamline_state`

Returns the current beamline state, distinguishing between permanent edits and temporary diagnostic modifications. Useful for the agent to re-orient after several modifications.

```
Output:
  canonical_elements: list             # The corrected beamline (edit_beamline changes only)
  working_elements: list               # What's actually being simulated (canonical + probes + idealizations + truncations)
  propagation_params: dict[str, dict]   # element_label -> {mode, range_x, range_y, resolution_x, resolution_y}
  edit_log: list[str]                  # Permanent changes made via edit_beamline
  active_probes: list                  # Currently inserted diagnostic apertures
  idealized_elements: list[str]        # Currently idealized element labels
  truncated_drifts: list[str]          # Currently truncated drift labels
  run_count: int
```

### 3.2 Propagation Parameter Control

#### `set_propagation_params`

Sets the 5 propagation parameters for one or more elements. This is the primary tuning lever. Elements are referenced by label, not index, to avoid breakage when probes or edits shift indices.

```
Input:
  params: dict[str, dict]   # element_label -> parameter dict

  Parameters per element (all 5 are the tunable knobs):
    mode: int               # Free-space propagator mode (0-4), applies to both axes
    range_x: float          # Horizontal range resize factor
    range_y: float          # Vertical range resize factor
    resolution_x: float     # Horizontal resolution resize factor
    resolution_y: float     # Vertical resolution resize factor

Output:
  applied_params: dict[str, dict]   # Confirmed parameters per element label
  warnings: list[str]               # e.g. "resolution factor > 4 may be slow"
```

Note: SRW's internal propagation parameter array has 12 entries, but only these 5 are relevant for tuning. The server manages the remaining internal parameters (semi-analytical treatment flags, etc.) and sets them to appropriate defaults.

**Propagator mode reference (returned in tool description for the agent):**

The mode is a single value that applies to both horizontal and vertical axes simultaneously (this is a 2D propagator). For astigmatic beamlines where horizontal and vertical have very different focusing geometry, mode 2 with high point counts is often a good compromise — it preserves the grid while handling quadratic phase subtraction.

| Mode | Name | When to use |
|------|------|-------------|
| 0 | Standard (2 FFTs) | Default. Near-field, no phase issues. |
| 1 | Quadratic phase subtraction (2 FFTs) | Large divergence, far from waist. Removes quadratic phase before propagation. |
| 2 | Quadratic phase subtraction, fixed grid (2 FFTs) | Like mode 1 but preserves the grid. Good for astigmatic beamlines where one axis is near focus and the other isn't. |
| 3 | From-waist far-field (1 FFT) | Propagating from a waist into far field. |
| 4 | To-waist far-field (1 FFT) | Propagating from far field toward a waist/focus. |

**Critical: range/resolution parameter inversion for modes 3 and 4.**
Modes 3/4 use a single FFT instead of two, which swaps the meaning of range and resolution: "range" controls point density, "resolution" controls window size. See `srw://tuning-heuristics` for the full explanation.

### 3.3 Simulation Execution

#### `run_propagation`

Runs the wavefront propagation through the full beamline (or a subset) with current parameters. Returns numerical results.

```
Input:
  up_to_element: str | None    # Stop after this element label (None = full beamline)
  at_element: str | None       # Return intermediates only for this element (None = all elements)
  mesh_params: dict | None      # Override source mesh if needed

Output:
  {
    final: {
      fwhm_x_um: float,
      fwhm_y_um: float,
      peak_intensity: float,
      total_flux: float,
      mesh_nx: int, mesh_ny: int,
      mesh_range_x_mm: float, mesh_range_y_mm: float,
      mesh_pitch_x_um: float, mesh_pitch_y_um: float,  # range / num_points
      rms_x_um: float, rms_y_um: float,
      centroid_x_um: float, centroid_y_um: float,
      edge_intensity_ratio_x: float,   # max intensity in outer 10% of mesh (x) / peak
      edge_intensity_ratio_y: float,   # max intensity in outer 10% of mesh (y) / peak
                                       # Should be ~0. If significantly >0, beam is clipped.
    },
    intermediates: [              # Before/after metrics at every element (or just at_element if specified)
      {
        element_index: int,
        element_label: str,
        before: {                   # At entrance plane, after propagating preceding drift
          fwhm_x_um: float,
          fwhm_y_um: float,
          peak_intensity: float,
          total_flux: float,
          mesh_nx: int, mesh_ny: int,
          mesh_pitch_x_um: float, mesh_pitch_y_um: float,
          edge_intensity_ratio_x: float,
          edge_intensity_ratio_y: float,
        },
        after: {                    # At same plane, after applying element transmission/reflection
          fwhm_x_um: float,
          fwhm_y_um: float,
          peak_intensity: float,
          total_flux: float,
          mesh_nx: int, mesh_ny: int,
          mesh_pitch_x_um: float, mesh_pitch_y_um: float,
          edge_intensity_ratio_x: float,
          edge_intensity_ratio_y: float,
        },
        flux_ratio_before_to_source: float,
        flux_ratio_after_to_source: float
      }
    ],
    wall_time_s: float,
    run_id: str                   # Reference for history
  }
```

#### `run_convergence_test`

Runs the same beamline at multiple scaling levels to check whether the result has converged. The server is mode-aware: for modes 0/1/2, scaling factors are applied to the resolution parameters; for modes 3/4, they are applied to the range parameters instead (since the meaning is inverted for single-FFT modes). The agent does not need to account for the mode 3/4 inversion when requesting convergence tests.

```
Input:
  element_label: str | None            # Test convergence at this element (None = final)
  scaling_factors: list[float]         # e.g. [0.5, 1.0, 1.5, 2.0]
  axis: "x" | "y" | "both"

Output:
  {
    active_mode: int,                  # Which mode was active (for agent's reference)
    parameter_scaled: str,             # "resolution" for modes 0/1/2, "range" for modes 3/4
    results: [
      {
        scaling_factor: float,
        fwhm_x_um: float,
        fwhm_y_um: float,
        peak_intensity: float,
        total_flux: float,
        wall_time_s: float
      }
    ]
  }
```

### 3.4 Analytical Estimation

#### `compute_analytical_estimates`

Computes expected beam parameters using Gaussian beam propagation formulas, accounting for source demagnification and diffraction limits at focusing elements.

```
Input:
  at_element: str | None              # Compute at this element label (None = all elements)

Output:
  {
    estimates: [
      {
        element_index: int,
        element_label: str,

        // --- FWHM estimates ---
        expected_fwhm_x_um: float,       # max(demagnification, diffraction_limit)
        expected_fwhm_y_um: float,
        source_demagnification_x_um: float,  # Geometric image size
        source_demagnification_y_um: float,
        diffraction_limit_x_um: float,       # 0.44 * λ / NA_effective
        diffraction_limit_y_um: float,

        // --- Numerical aperture (dual values) ---
        element_na_x_mrad: float,        # NA from element's physical size
        element_na_y_mrad: float,
        beam_na_x_mrad: float,           # NA from beam divergence at this element
        beam_na_y_mrad: float,
        effective_na_x_mrad: float,      # min(element_na, beam_na) — the one that matters
        effective_na_y_mrad: float,
        // When beam_na > element_na, the element is fully illuminated and
        // the element's geometric NA sets the diffraction limit authoritatively.
        // When beam_na < element_na, the beam underfills the element and
        // the beam's own divergence sets the effective NA.

        // --- Aperture fill ---
        beam_to_aperture_ratio_x: float,     # beam_size / aperture_size
        beam_to_aperture_ratio_y: float,     # ≥1.0 means fully filled / overfilled
        limiting_aperture_element: str,      # Which element label sets the NA

        // --- Gaussian beam parameters ---
        rayleigh_range_x_m: float,
        rayleigh_range_y_m: float,
        distance_from_waist_x_m: float,      # Signed distance from nearest waist
        distance_from_waist_y_m: float,
        wavefront_roc_x_m: float,            # Wavefront radius of curvature
        wavefront_roc_y_m: float,            # Large = nearly flat; small = strongly curved

        // --- Focusing geometry ---
        object_distance_m: float,            # For focusing elements
        image_distance_m: float,
        focal_length_m: float | null,
        object_to_focal_ratio: float | null, # object_distance / focal_length
        // When >>1, demagnification is tiny and diffraction dominates.
        // When ~1-3, demagnification can be significant.

        // --- Regime indicators ---
        fresnel_number: float                # beam_size² / (λ * propagation_distance)
        // >>1: geometric optics regime, aperture diffraction negligible
        // ~1: diffraction from aperture edges is significant
        // <<1: far-field / Fraunhofer regime
      }
    ]
  }
```

The estimator walks the beamline element-by-element using ABCD matrix / thin-lens Gaussian beam propagation:
- Tracks beam waist size and location in both planes
- At focusing elements: computes both the geometric demagnification (source size × image distance / object distance) and the diffraction limit (0.44 × λ / NA_effective for FWHM)
- Computes both the element's geometric NA and the beam's divergence-based NA so the agent can determine which is the limiting factor
- Reports beam-to-aperture ratios at each element so the agent can assess clipping
- Reports distance from waist and wavefront radius of curvature so the agent can assess Gaussian validity and choose propagator modes
- Reports Fresnel number so the agent can judge whether aperture diffraction effects are significant

#### `compare_to_estimates`

Compares simulation results against analytical estimates. Returns numerical deviations only — the agent is responsible for interpreting the physical meaning of any discrepancies.

```
Input:
  run_id: str | None                  # Compare this run (None = latest)

Output:
  {
    comparisons: [
      {
        element_index: int,
        element_label: str,
        simulated_fwhm_x_um: float,
        estimated_fwhm_x_um: float,
        deviation_x_pct: float,
        simulated_fwhm_y_um: float,
        estimated_fwhm_y_um: float,
        deviation_y_pct: float
      }
    ],
    flux_conservation: {
      source_flux: float,
      final_flux: float,
      ratio: float
    }
  }
```

### 3.5 Hypothesis Testing

#### `test_hypothesis`

A compound tool that lets the agent test a specific hypothesis about a propagation parameter choice. It runs a simulation with modified parameters and compares to a baseline run. The parameter changes are scoped to the test only — after the run completes (or fails), the active propagation parameters are unchanged. The agent can use this tool as many times as needed.

To adopt tested parameters permanently, call `set_propagation_params` separately.

```
Input:
  hypothesis: str                      # Free-text description for logging
  param_changes: dict[str, dict]       # Element label -> param changes to test
  compare_to_run_id: str | None        # Compare against this run (None = latest)

Output:
  {
    hypothesis: str,
    baseline_run_id: str,
    test_run_id: str,
    baseline: { fwhm_x_um, fwhm_y_um, peak_intensity, total_flux, wall_time_s },
    test: { fwhm_x_um, fwhm_y_um, peak_intensity, total_flux, wall_time_s },
    deltas: {
      fwhm_x_change_pct: float,
      fwhm_y_change_pct: float,
      flux_change_pct: float,
      speedup_factor: float
    },
    params_reverted: true               # Confirms params were scoped to this test only
  }
```

### 3.6 Report Data

#### `get_report_data`

Returns all data needed for the agent to compose a validity report. The server provides structured numerical data; the agent writes the narrative, interprets element dominance, and draws conclusions.

```
Input:
  include_history: bool                # Include parameter exploration history

Output:
  {
    beamline_summary: {
      source_type: str,
      photon_energy_eV: float,
      canonical_elements: list,        # The corrected beamline definition (permanent edits applied)
      total_length_m: float,
      edits_from_original: list[str]   # Permanent corrections made via edit_beamline
    },
    corrected_definition: dict,        # Full corrected beamline definition for user export
    propagation_parameters: [
      {
        element_label: str,
        mode: int,
        range_x: float, range_y: float,
        resolution_x: float, resolution_y: float
      }
    ],
    latest_estimates: { ... },         # Output of compute_analytical_estimates
    latest_comparison: { ... },        # Output of compare_to_estimates
    convergence_tests: [               # All convergence tests run this session
      {
        element_label: str,
        results: [ { resolution_factor, fwhm_x_um, fwhm_y_um, wall_time_s } ]
      }
    ],
    idealization_tests: [              # All idealization test results
      {
        elements_idealized: list[str],
        realistic_run_id: str,
        idealized_run_id: str,
        realistic_fwhm: { x_um, y_um },
        idealized_fwhm: { x_um, y_um },
        realistic_flux: float,
        idealized_flux: float
      }
    ],
    simulation_history: list | None    # Full run history if include_history=True
  }
```

The agent uses this data to compose a validity report that includes its own physical reasoning about which elements dominate, why deviations exist, and whether the parameters are trustworthy.

---

## 4. MCP Resources

The server exposes the following read-only resources for the agent to consult:

#### `srw://tuning-heuristics`
Encodes the accumulated heuristics for propagation parameter selection:

```markdown
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
```

#### `srw://diagnostic-patterns`
Common failure patterns the agent should recognize. These are reasoning aids, not server-generated diagnoses:

```markdown
## Diagnostic Patterns

| Symptom | Likely causes to investigate |
|---------|----------------------------|
| FWHM well below diffraction limit | Aliasing; try higher resolution or different propagator mode |
| FWHM much larger than estimate | Beam clipping (range too small); wrong propagator mode near focus |
| Asymmetric deviation (x ok, y not) | Astigmatism; try different range/resolution values per axis, or switch to mode 2 with higher point count |
| Flux loss without apertures | Range too small (beam clipped at edge of mesh) |
| edge_intensity_ratio > 0 | Beam reaches mesh boundary; increase range before diagnosing anything else |
| FWHM oscillates with resolution | Not converged; try higher resolution or mode 1/2 |
| Idealized element gives same result | Propagation params are likely correct for that element |
| Idealized element gives different result | Realistic element introduces effects (e.g. slope errors, aberrations) that need more careful resolution |

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
  wavefront is nearly flat. Mode 0 is appropriate.

- **Small wavefront_roc (comparable to or less than propagation
  distance):** The quadratic phase varies rapidly across the mesh.
  Modes 1-4 are needed to factor out this curvature. The ratio
  distance_from_waist / rayleigh_range indicates how far from flat
  the wavefront is — values >>1 mean strong curvature.

### General principles

- A 10-20% deviation between simulation and analytical estimate is often
  acceptable and explainable (non-Gaussian beam shape, clipping effects).
  The agent should reason about WHY the deviation exists, not just flag it.

- When the analytical estimate is known to be unreliable (e.g. beam is
  heavily clipped, far from Gaussian, Fresnel number ~1), the agent
  should state this and rely more on convergence tests and idealization
  tests for validation.

- Flux conservation is a strong independent check. If flux is conserved
  but FWHM disagrees with estimate, the simulation is likely correct and
  the estimate is the problem.

- Always check edge_intensity_ratio before diagnosing any other issue.
  If the beam is hitting the mesh boundary, nothing else is trustworthy.
```

#### `srw://idealization-test-guide`
Guide for using idealization tests as a validation technique:

```markdown
## Idealization Tests

Replacing a realistic focusing element with its ideal thin-lens +
aperture equivalent is a key technique for validating propagation
parameters.

### Strategy

1. **Test all elements at once first.** If realistic and idealized
   beamlines agree, the propagation parameters are likely correct
   for the entire beamline.

2. **If they disagree, test one element at a time.** Replace each
   focusing element individually to isolate which one is causing
   the discrepancy.

3. **Interpreting results:**
   - Small difference (<5% FWHM): Propagation is handling the
     realistic element correctly.
   - Large difference: Either the propagation params need adjustment
     for that element, or the realistic element has physical effects
     (slope errors, figure errors, higher-order aberrations) that
     the ideal model doesn't capture. The agent should reason about
     which case applies.

### When to use
- After initial parameter tuning, before declaring success
- When a discrepancy persists and you can't determine if it's
  numerical or physical
- When validating parameters for a new element type you haven't
  tuned before
```

---

## 5. Agent Prompting Strategy

### 5.1 System Prompt

```
You are an expert synchrotron radiation beamline physicist specializing in
wavefront propagation simulations using SRW. You tune propagation parameters
for beamline definitions to achieve physically correct results with minimal
computational cost.

The MCP tools give you numerical data — beam sizes, flux values, mesh
parameters, analytical estimates. YOU are responsible for all physical
interpretation: deciding what's correct, diagnosing what's wrong, explaining
why results look the way they do, and determining which element dominates
the beam behavior at any given point.

## Your workflow

1. **Understand the beamline:** Load the definition. Identify all optical
   elements, their types, positions, and key parameters (focal lengths,
   grazing angles, apertures).

2. **Build expectations:** Compute analytical estimates for beam size at
   each element using Gaussian beam propagation. Look at the raw numbers:
   demagnification vs. diffraction limit, beam-to-aperture ratios,
   distance from waist. Reason about where the Gaussian approximation
   will break down and where you should trust it.

3. **Select initial propagation parameters:** Based on the heuristics in
   the srw://tuning-heuristics resource, choose propagator modes and
   range/resolution factors for each element. Use the distance_from_waist
   and rayleigh_range values from the estimates to guide mode selection.
   Also check smallest_feature_size_m for each element — if an element
   has fine spatial structure (zone plates, gratings, sharp apertures),
   the mesh pitch at that element must be smaller than the feature size.
   This may require a large resolution rescale on the preceding step.
   Err on the side of higher fidelity for the first run.

4. **Run and diagnose:** Execute the propagation and compare results to
   analytical estimates. For each discrepancy:
   - Look at the numbers: how far off? Which axis? Is flux conserved?
   - Form a hypothesis about the cause (aliasing, clipping, wrong mode)
   - Test the hypothesis by changing one parameter at a time
   - Confirm the fix by checking convergence

5. **Validate with idealization tests:** Replace focusing elements with
   ideal thin-lens + aperture equivalents. Test all at once first — if
   results agree, parameters are likely correct. If they disagree, test
   one element at a time to isolate the issue. Reason about whether any
   remaining discrepancy is numerical (needs parameter adjustment) or
   physical (the realistic element has effects the ideal model doesn't).

6. **Optimize:** Once results match expectations (or you can explain why
   they shouldn't), reduce resolution/range to find the most
   computationally efficient settings that still converge.

7. **Report:** Compose a validity report using the structured data from
   get_report_data. Write the narrative yourself — explain which physical
   effects dominate at each point, why deviations exist, and why you
   trust (or don't trust) the result.

## Key principles

- **Change one thing at a time.** When diagnosing, modify a single
  parameter and observe the effect before changing another.

- **Trust the physics.** If a focal spot is below the diffraction limit,
  the simulation is wrong, not the optics. Increase resolution or change
  the propagator mode.

- **You do the reasoning.** The tools return numbers. You interpret what
  they mean physically. When you see a beam-to-aperture ratio of 0.9,
  you conclude the beam is significantly clipped. When you see
  demagnification at 0.4 μm but diffraction limit at 1.1 μm, you
  conclude diffraction dominates. State these conclusions explicitly.

- **Explain your reasoning.** Before each tool call, state what you expect
  to see and why. After each result, explain whether it matched and what
  you learned.

- **Be efficient.** A few-second simulation that agrees with estimates is
  better than a minute-long simulation with 4× the resolution that gives
  the same answer.

- **Know when the analytical estimate is unreliable.** After apertures
  with high beam-to-aperture ratios, with strong astigmatism, or with
  highly non-Gaussian beams, the estimate itself may be off. State this
  explicitly and rely on convergence tests and idealization tests instead.

- **Truncate, don't split.** To inspect the beam at an intermediate point
  in a drift, use truncate_drift to shorten the drift and pass
  up_to_element on run_propagation to stop there. Do NOT split drifts
  into segments — that introduces new propagation parameter boundaries.
  Restore the original drift when done.

- **Idealization tests are your best friend.** When in doubt about whether
  a result is correct, replace the suspicious element with its ideal
  equivalent and compare. This separates numerical issues from physics.

## Propagator modes (quick reference)
The mode is a single value per element, applied to both axes (2D propagator).
- 0: Standard, 2 FFTs (near waist)
- 1: Quadratic phase subtraction, 2 FFTs (far from waist, grid resizes)
- 2: Quadratic phase subtraction, 2 FFTs, fixed grid
- 3: From waist → far field, 1 FFT
- 4: To waist ← far field, 1 FFT

**Modes 3/4: range and resolution params are INVERTED.**
Because a single FFT swaps spatial ↔ frequency domains:
- "range" param actually controls output **point density**
- "resolution" param actually controls output **window size**
This is the opposite of modes 0/1/2. Always check which mode you're
using before adjusting range or resolution.

**Astigmatic beamlines:** When horizontal and vertical have different
focusing geometry (e.g., one axis near focus, the other far from it),
mode 2 with high point counts is often a good compromise — it handles
quadratic phase subtraction while preserving the grid. Astigmatic
beamlines typically require more exploration and may need higher
resolution to get both axes right simultaneously.

## Diagnostic red flags (check in this order)
- edge_intensity_ratio > 0 → beam hits mesh boundary; fix this FIRST
  before diagnosing anything else (increase range)
- FWHM < diffraction limit → aliasing (increase resolution or change mode)
- Unexpected flux loss → mesh range too small (increase range)
- FWHM oscillates with resolution → not converged
- x/y disagree when optics are symmetric → check per-axis parameters
- Idealized element gives very different result → investigate that element
- mesh_pitch > smallest_feature_size at an element → the mesh cannot
  represent this element faithfully; increase resolution rescale before it
```

### 5.2 Structured Reasoning Protocol

The agent should follow this chain-of-thought structure at each decision point. This can be enforced via few-shot examples in the system prompt:

```
## Before each simulation:

<planning>
**Current state:** [Summary of where we are in the tuning process]
**Goal of this run:** [What question are we answering?]
**Hypothesis:** [What do we expect to see and why?]
**Parameter choices:** [What we're setting and the reasoning]
</planning>

[tool call]

## After each result:

<diagnosis>
**Result summary:** [Key numbers]
**Compared to expectation:** [Match or discrepancy, with magnitudes]
**Interpretation:** [What this tells us physically]
**Next step:** [What to try next, or declare done]
</diagnosis>
```

### 5.3 Example Agent Conversation Flow

```
User: Here's my beamline definition: [JSON blob with undulator source,
      3 mirrors, CRL, and a 40m drift to sample]

Agent:
  <planning>
  Loading the beamline to understand the optical layout before
  making any parameter choices.
  </planning>

  → calls load_beamline(...)

  <diagnosis>
  This is an undulator beamline at 12 keV with:
  - M1 (flat mirror) at 28m, 3 mrad grazing angle
  - M2 (KB vertical focusing) at 35m, f=2.5m
  - M3 (KB horizontal focusing) at 36m, f=2.0m
  - CRL (compound refractive lens) at 37m
  - Sample at 40m

  I need the analytical estimates to understand where the foci
  are and what beam sizes to expect.
  </diagnosis>

  → calls compute_analytical_estimates()

  <diagnosis>
  Looking at the raw numbers:
  - At M2 focus: demagnification_y = 0.4 μm, diffraction_limit_y = 1.1 μm.
    Since diffraction_limit >> demagnification, this focus is
    diffraction-dominated. NA is set by M2's 0.8 mrad acceptance.
  - beam_to_aperture_ratio at M1 is 0.85 — the beam nearly fills M1.
    This means the Gaussian estimate may underestimate the FWHM at
    downstream foci due to diffraction from the clipped wings.
  - distance_from_waist at sample is 2.2m in vertical, with
    rayleigh_range = 0.3m — we're ~7 Rayleigh ranges from the waist.
    Need mode 1 or 3 for the last drift, not mode 0.

  For initial propagation parameters (mode is single value, both axes):
  - D1 (before M2): far from waist → mode 1
  - D2 (M2 to M3): converging to V focus but H still diverging.
    This is astigmatic — mode 2 is a good compromise here.
  - D3 (after focus through CRL): re-expanding → mode 1
  - D4 (long drift to sample): far from focus → mode 1

  Setting range factors generously (3×) and resolution at 1.5.
  </planning>

  → calls set_propagation_params({"D1": {mode: 1, ...}, "D2": {mode: 2, ...}, ...})
  → calls run_propagation()
  → calls compare_to_estimates()

  <diagnosis>
  Results at sample: simulated FWHM_y = 18.3 μm, estimated = 15.1 μm,
  deviation = +21%. Flux ratio = 0.79.

  First checking edge_intensity_ratio — at D1 it's 0.02, which means
  there's still some intensity at the mesh edges. That could explain
  the flux loss.

  The beam_to_aperture_ratio at M1 was 0.85, so some clipping is
  physical, but edge_intensity_ratio > 0 suggests the mesh itself is
  also too small. I'll increase range first and see if both improve.
  </diagnosis>

  → calls test_hypothesis(
      hypothesis="Mesh range too small — increasing range at D1",
      param_changes={"D1": {range_x: 4.0, range_y: 4.0}})

  [... after several iterations, results converge ...]

  <planning>
  Results now agree within 12%. The remaining deviation is likely
  physical — the beam_to_aperture_ratio of 0.85 at M1 means the
  beam isn't truly Gaussian at the foci. Before declaring success,
  I should validate with an idealization test.
  </planning>

  → calls idealize_element(element_labels="all")
  → calls run_propagation()

  <diagnosis>
  Idealized beamline gives FWHM_y = 17.9 μm at sample vs. 18.3 μm
  with realistic elements. Only 2% difference — the propagation
  parameters are handling the realistic elements correctly. The
  12% deviation from the analytical estimate is physical (clipping
  at M1), not numerical.
  </diagnosis>

  → calls restore_elements(element_labels="all")
  → calls get_report_data(include_history=True)

  [Agent composes validity report from the structured data]
```

### 5.4 Prompt Templates for Common Scenarios

#### Initial tuning prompt (user-facing)
```
Tune the propagation parameters for this beamline: {beamline_json}

Start by loading the beamline and computing analytical estimates.
Then select initial propagation parameters, run the simulation,
and iterate until the results match expectations within 20%.
Finally, optimize for speed and generate a validity report.
```

#### Element-by-element debugging prompt
```
The full beamline simulation shows a {x_fwhm} μm horizontal
focal spot at element {N}, but the analytical estimate is {est} μm.
Use up_to_element on run_propagation to propagate up to each element in sequence
and identify where the discrepancy originates. If you need to
inspect a point within a long drift, use truncate_drift — do not
split the drift.
```

#### Convergence check prompt
```
The current parameters give a {time}s simulation. Run a convergence
test at the sample position to determine the minimum resolution
that reproduces the FWHM within 5%.
```

---

## 6. Implementation Notes

### 6.1 Beamline Definition Format

The server accepts SRW-native beamline definitions (the nested list/dict structure used by `srwpy`) and also a simplified JSON schema for readability:

```json
{
  "source": {
    "type": "undulator",
    "energy_eV": 12000,
    "undulator_period_m": 0.021,
    "num_periods": 72,
    "K_vertical": 1.5
  },
  "elements": [
    {
      "type": "drift",
      "length_m": 28.0,
      "label": "D1"
    },
    {
      "type": "mirror",
      "orientation": "vertical",
      "grazing_angle_mrad": 3.0,
      "tangential_size_m": 0.4,
      "sagittal_size_m": 0.02,
      "focal_length_m": null,
      "label": "M1_flat"
    }
  ]
}
```

The server translates this to SRW internal structures. The original SRW format is also accepted directly for users who already have beamlines defined.

### 6.2 Wavefront Metrics Extraction

The server extracts beam metrics from `SRWLWfr` objects using these methods:

```python
def extract_metrics(wfr: SRWLWfr) -> dict:
    """Extract FWHM, flux, centroid from a wavefront."""
    # Get intensity on axis
    intensity = srwl.CalcIntFromElecField(wfr, 6, 0, 0, ...)
    # Compute 1D projections for FWHM
    proj_x = integrate_over_y(intensity, mesh)
    proj_y = integrate_over_x(intensity, mesh)
    fwhm_x = compute_fwhm(proj_x, mesh.xStart, mesh.xFin)
    fwhm_y = compute_fwhm(proj_y, mesh.yStart, mesh.yFin)
    # Total flux via integration
    total_flux = integrate_2d(intensity, mesh)
    return { ... }
```

Importantly, FWHM is computed from the actual intensity profile, not from Gaussian fits, since the beam may be far from Gaussian.

### 6.3 Error Handling

The server should handle errors gracefully and return structured error responses so the agent can reason about what went wrong and decide how to recover.

```
Error response format:
  {
    error: true,
    error_type: "timeout" | "segfault" | "nan_inf" | "memory_limit" | "srw_error",
    message: str,                     # Human-readable description
    element_label: str | null,        # Which element was being processed when it failed
    params_at_failure: dict | null,   # Propagation params that caused the failure
    wall_time_s: float                # How long it ran before failing
  }
```

Specific failure modes:
- **SRW crashes** (segfaults from extreme parameters): Run simulations in a subprocess with timeout. Return `error_type: "segfault"` rather than crashing the server.
- **Memory limits**: Estimate memory usage before running (proportional to nx × ny) and return `error_type: "memory_limit"` with the estimated memory requirement if it exceeds a threshold.
- **Non-physical results**: Detect NaN/Inf in output and return `error_type: "nan_inf"` with the element label where it was first detected.
- **Timeout**: If a run exceeds the configured timeout, kill the subprocess and return `error_type: "timeout"`.
- **SRW internal errors**: Catch SRW exceptions and return `error_type: "srw_error"` with the original error message.

The agent should treat errors as diagnostic information: a timeout suggests the resolution is too high; a segfault or NaN often means the propagator mode is inappropriate for the beam state; memory limits mean the mesh is too large.

### 6.4 Performance Considerations

- **Cache the source wavefront.** Recomputing the undulator source on every run is wasteful. Cache it and only recompute if source parameters change.
- **Subprocess isolation.** Run SRW propagation in a subprocess so that if it hangs or leaks memory, the MCP server stays alive.
- **Intermediate wavefront caching.** The server should cache intermediate wavefronts internally and invalidate them automatically when upstream changes occur. The agent does not need to know about the cache — it just calls tools and gets correct results. Invalidation rules: if propagation parameters change at element N, invalidate from N onward; if `edit_beamline`, `probe_aperture`, or `idealize_element` modifies element N, invalidate from N onward; if `truncate_drift` changes a drift, invalidate from that drift onward. This is purely a server-side optimization.
- **Timeout.** Set a configurable timeout (default: 180s) for any single propagation run. If exceeded, kill the subprocess and suggest reducing resolution.

---

## 7. Validity Report Structure

The validity report is **composed by the agent**, not generated by the server. The agent calls `get_report_data` to retrieve all structured numerical data, then writes the narrative — interpreting which elements dominate, explaining deviations, and drawing conclusions about correctness.

Example of what the agent would produce:

```markdown
# Beamline Validity Report
## Beamline: KB Microscopy Endstation
## Date: 2025-01-15
## Source: Undulator, 12 keV

### Optical Layout

| # | Element | Distance (m) | Type |
|---|---------|-------------|------|
| 0 | D1      | 0 → 28      | Drift |
| 1 | M1_flat | 28           | Flat mirror, 3 mrad |
| 2 | D2      | 28 → 35     | Drift |
| 3 | M2_KB_V | 35           | KB mirror (V), f=2.5m |
| ...                                  |

### Propagation Parameters

| Element | Mode | Range X | Range Y | Res X | Res Y |
|---------|------|---------|---------|-------|-------|
| D1      | 1    | 4.0     | 4.0     | 1.0   | 1.0   |
| M1_flat | 0    | 1.5     | 1.5     | 1.0   | 1.0   |
| ...                                                  |

### Simulation vs. Analytical Estimates

| Element | Sim FWHM X (μm) | Est FWHM X (μm) | Δ (%) |
|---------|-----------------|-----------------|-------|
| Sample  | 18.3            | 15.1            | +21%  |

The 21% deviation at the sample is expected and understood. The
analytical estimate assumes a Gaussian beam, but M1 has a
beam-to-aperture ratio of 0.85, meaning the beam wings are
clipped. This introduces diffraction sidelobes that broaden the
FWHM beyond the Gaussian prediction. The idealization test
confirms this is physical, not numerical (see below).

### Flux Conservation

Source flux: 1.0e12 ph/s → Final flux: 8.2e11 ph/s (ratio: 0.82)

The 18% loss is consistent with: M1 reflectivity (~95% at 3 mrad
and 12 keV), beam clipping at M1 (~5% of the beam extends beyond
the mirror acceptance at beam-to-aperture ratio 0.85), and CRL
absorption (~12% for this number of lenses at 12 keV). No
unexplained flux loss.

### Element Dominance Analysis

At the vertical KB focus (element 5), the estimated
demagnification contribution is 0.4 μm while the diffraction
limit from M2's 0.8 mrad numerical aperture is 1.1 μm.
Diffraction dominates the vertical focal spot by nearly 3×.

At the sample (element 9), the beam has re-expanded to 18.3 μm
vertically. This is 7 Rayleigh ranges past the vertical focus,
so the beam size is governed by the divergence from the focal spot.
The horizontal and vertical sizes differ because the KB pair
has different focal lengths and NAs in the two planes.

### Idealization Tests

Replacing all focusing elements (M2, M3, CRL) with ideal
thin-lens + aperture equivalents gave FWHM_y = 17.9 μm at the
sample vs. 18.3 μm with realistic elements (2% difference).
This confirms propagation parameters are adequate — the realistic
element profiles are not introducing numerical artifacts.

### Convergence

Resolution factors [1.0, 1.5, 2.0] give FWHM at sample of
[18.9, 18.3, 18.3] μm. The result has converged at resolution
factor 1.5. Factor 1.0 shows a 3% deviation, suggesting it is
marginally under-resolved.

### Conclusion

Parameters are stable and efficient (runtime: 4.2s per run at
resolution factor 1.5). The 21% deviation from the analytical
estimate is physical and understood. Idealization tests and
convergence tests both pass.
```

---

## 8. Tool Call Budget Guidance

To keep the agent efficient, include budget guidance in the system prompt:

| Task | Expected tool calls |
|------|-------------------|
| Initial load + estimates | 2-3 |
| First full run + comparison | 3 |
| Single parameter hypothesis test | 1 each (use as many as needed) |
| Truncate drift + inspect intermediate | 3 (truncate, run, restore) |
| Idealization test (all elements) | 3-4 (idealize, run, compare, restore) |
| Idealization test (per element) | 3-4 per element |
| Convergence test | 1 |
| Get report data | 1 |
| **Typical full tuning session** | **20-40 total** |

If the agent exceeds 40 tool calls without converging, it should pause and summarize what it has tried, what's still failing, and ask the user for guidance.

---

## 9. Extension Points

Areas to expand in future iterations:

- **Partially coherent simulations:** Multi-electron calculations with statistical sampling. The agent would need to manage both single-electron propagation parameters and multi-electron sampling strategy.
- **Source tuning:** Extend the agent to also optimize undulator parameters (K value, harmonics selection) for a given target photon energy.
- **Visualization tools:** Return 2D intensity maps and phase profiles as base64 images for the agent to inspect (or pass to a vision model).
- **Parameter space search:** For particularly difficult beamlines, implement a systematic grid search or Bayesian optimization over propagation parameters, guided by the agent's physical intuition for which parameters to explore.
- **Beamline library:** A collection of known-good parameter sets for common beamline archetypes that the agent can use as starting points.

