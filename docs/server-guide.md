# SRW Propagation Parameter Tuning Server

An MCP (Model Context Protocol) server that wraps SRW's Python bindings
(`srwpy`) to enable AI-assisted tuning of wavefront propagation parameters for
X-ray beamline simulations.

## Overview

The server exposes SRW functionality through MCP tools and resources. An AI
agent iteratively tunes propagation parameters by:

1. Loading a beamline definition
2. Computing analytical expectations (Gaussian beam / ABCD matrices)
3. Running SRW simulations with candidate parameters
4. Comparing results to expectations
5. Diagnosing discrepancies and adjusting parameters
6. Repeating until results are physically consistent

## Installation

```bash
pip install -e .
```

Requires `srwpy` (SRW Python bindings) and `numpy`.

## Running the Server

```bash
# Via the entry point
srw-pp-agent

# Or directly
python -m srw_pp_agent.server
```

The server runs over stdio using the MCP JSON-RPC protocol.

## Architecture

```
Agent (LLM)
    │  MCP protocol (JSON-RPC over stdio)
    ▼
MCP Server
    ├── Beamline Manager    — load, edit, probe, idealize, truncate
    ├── Simulation Runner   — subprocess-isolated SRW propagation
    ├── Analytical Estimator— ABCD matrix / Gaussian beam math
    ├── Analysis Engine     — compare simulation vs estimates
    └── Session State       — persists across tool calls
         │
         ▼
       srwpy (SRW Python bindings)
```

### Session State

A single `TuningSession` persists for the lifetime of a conversation. It
tracks:

- **Original definition** — beamline as provided by the user
- **Canonical definition** — accumulates permanent edits via `edit_beamline`
- **Working beamline** — canonical + temporary modifications (probes,
  idealizations, truncations); this is what gets simulated
- **Propagation parameters** — per-element `{mode, range_x, range_y,
  resolution_x, resolution_y}`
- **Simulation history** — all past runs with parameters, metrics, and timing
- **Analytical estimates** — cached Gaussian beam predictions

### SRW Interface Layer

All direct `srwpy` imports are confined to the `srw_interface/` package. Other
modules access SRW through this abstraction, which provides:

- **elements** — build SRW optical elements from JSON definitions
- **propagation** — parameter expansion and propagation calls
- **wavefront** — copy, serialize, resize wavefronts
- **metrics** — extract FWHM, flux, centroid from wavefronts
- **source** — create source wavefronts (undulator, Gaussian, etc.)

This isolation makes the rest of the codebase testable without `srwpy`
installed.

## MCP Tools

### Beamline Management

| Tool                | Description                                              |
|---------------------|----------------------------------------------------------|
| `load_beamline`     | Parse a beamline definition and cache the source wavefront. |
| `edit_beamline`     | Permanently insert, remove, or edit elements.            |
| `probe_aperture`    | Temporarily insert/remove diagnostic apertures.          |
| `truncate_drift`    | Temporarily shorten a drift to inspect intermediate points. |
| `restore_drift`     | Restore a truncated drift to its original length.        |
| `idealize_element`  | Replace focusing elements with thin-lens equivalents.    |
| `restore_elements`  | Revert idealized elements to their original definitions. |
| `get_beamline_state`| Return current canonical and working beamline state.     |

### Propagation Parameters

| Tool                    | Description                                        |
|-------------------------|----------------------------------------------------|
| `set_propagation_params`| Set mode, range, and resolution for one or more elements. |

**Propagation modes:**

| Mode | Name                        | FFTs | Use when                         |
|------|-----------------------------|------|----------------------------------|
| 0    | Standard                    | 2    | Near waist                       |
| 1    | Quadratic phase subtraction | 2    | Far from waist, grid resizes     |
| 2    | Quadratic phase, fixed grid | 2    | Astigmatic beamlines             |
| 3    | From-waist far-field        | 1    | Far from waist (range/res inverted) |
| 4    | To-waist far-field          | 1    | Approaching waist (range/res inverted) |

**Modes 3 and 4 invert the meaning of range and resolution parameters.**

### Simulation

| Tool                   | Description                                         |
|------------------------|-----------------------------------------------------|
| `run_propagation`      | Run wavefront propagation through the beamline.     |
| `run_convergence_test` | Run at multiple scaling levels to check convergence.|

Propagation executes in a subprocess with timeout protection. Results include
per-element FWHM, flux, centroid, and mesh information.

### Analysis

| Tool                        | Description                                    |
|-----------------------------|------------------------------------------------|
| `compute_analytical_estimates` | Gaussian beam ABCD matrix predictions.      |
| `compare_to_estimates`      | Compare a simulation run against predictions.  |
| `test_hypothesis`           | Test parameter changes without committing them.|

### Reporting

| Tool             | Description                                            |
|------------------|--------------------------------------------------------|
| `get_report_data`| Return structured data for composing a validity report.|

## MCP Resources

Static knowledge bases the agent can consult:

| URI                              | Content                                    |
|----------------------------------|--------------------------------------------|
| `srw://tuning-heuristics`        | Mode selection rules, range/resolution guidance. |
| `srw://diagnostic-patterns`      | Common failure patterns and interpretation.     |
| `srw://idealization-test-guide`  | How to use idealization tests for validation.   |

## Typical Tuning Workflow

1. **`load_beamline`** — provide the beamline JSON definition
2. **`compute_analytical_estimates`** — get expected beam sizes at each element
3. **`set_propagation_params`** — set initial parameters based on heuristics
4. **`run_propagation`** — simulate the full beamline
5. **`compare_to_estimates`** — check simulation vs predictions
6. **Diagnose and iterate** — adjust parameters based on discrepancies
7. **`idealize_element`** — validate parameters with ideal optics
8. **`run_convergence_test`** — verify numerical convergence
9. **`get_report_data`** — gather data for the final validity report

A typical session uses 20-40 tool calls.

## Beamline Definition Format

See [beamline-json-format.md](beamline-json-format.md) for the complete JSON
schema reference, including all element types and their parameters.

## Element Idealization

Focusing elements can be temporarily replaced with ideal equivalents for
validation:

| Original Element           | Ideal Replacement                                  |
|----------------------------|----------------------------------------------------|
| Elliptical mirror          | Thin lens (same f) + rectangular aperture          |
| Cylindrical mirror         | Thin lens (1D, same f) + rectangular aperture      |
| Flat mirror                | Rectangular aperture only                          |
| Zone plate                 | Thin lens (same f) + circular aperture             |
| CRL stack                  | Single thin lens (effective f) + circular aperture |

If a simulation with idealized optics matches the full simulation closely
(< 5% FWHM difference), the propagation parameters are likely correct.

## Error Handling

The server returns structured errors with:

- `error_type` — `timeout`, `segfault`, `nan_inf`, `memory_limit`,
  `srw_error`, `validation`, `session_not_loaded`
- `message` — human-readable description
- `element_label` — which element caused the problem (when applicable)
- `suggestion` — recommended action to resolve the issue
