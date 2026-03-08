"""FastMCP server entry point: tool/resource registration.

This file is deliberately thin — each @mcp.tool() function extracts the
session from context, calls the appropriate domain function, and returns
the result. All business logic lives in the domain modules.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP, Context

from .session import TuningSession
from .resources import read_resource


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize session state for the server lifetime."""
    session = TuningSession()
    yield {"session": session}


mcp = FastMCP("srw-beamline-tuning", lifespan=lifespan)


def _get_session(ctx: Context) -> TuningSession:
    """Extract the TuningSession from the MCP context."""
    return ctx.request_context.lifespan_context["session"]


# ---------------------------------------------------------------------------
# MCP Resources (3 read-only knowledge bases)
# ---------------------------------------------------------------------------

@mcp.resource("srw://tuning-heuristics")
def tuning_heuristics() -> str:
    """Propagation parameter selection heuristics: mode selection, range/resolution tuning, element sampling requirements."""
    return read_resource("tuning_heuristics.md")


@mcp.resource("srw://diagnostic-patterns")
def diagnostic_patterns() -> str:
    """Common failure patterns and interpretation guidelines for simulation results."""
    return read_resource("diagnostic_patterns.md")


@mcp.resource("srw://idealization-test-guide")
def idealization_guide() -> str:
    """Guide for using idealization tests to validate propagation parameters."""
    return read_resource("idealization_guide.md")


# ---------------------------------------------------------------------------
# Beamline Management Tools (8)
# ---------------------------------------------------------------------------

@mcp.tool()
def load_beamline(ctx: Context, beamline_definition: dict | str) -> dict:
    """Parse and load a beamline definition, cache source wavefront, return structured summary.

    Args:
        beamline_definition: SRW beamline dict or path to JSON/Python file
    """
    from .beamline.manager import load_beamline as _load
    return _load(_get_session(ctx), beamline_definition)


@mcp.tool()
def edit_beamline(ctx: Context, action: str, target_label: str = "",
                  insert_before: str | None = None,
                  element_definition: dict | None = None) -> dict:
    """Make permanent corrections to the beamline definition (insert/remove/edit elements).

    Args:
        action: "insert", "remove", or "edit"
        target_label: Element label to act on (for remove/edit)
        insert_before: For insert: place new element before this label
        element_definition: For insert/edit: the element dict (must include label)
    """
    from .beamline.manager import edit_beamline as _edit
    return _edit(_get_session(ctx), action, target_label, insert_before, element_definition)


@mcp.tool()
def probe_aperture(ctx: Context, action: str,
                   probe_id: str | None = None,
                   at_element: str | None = None,
                   aperture_params: dict | None = None) -> dict:
    """Temporarily insert or remove a diagnostic aperture (does NOT modify canonical beamline).

    Args:
        action: "insert", "remove", or "remove_all"
        probe_id: For remove: which probe to remove
        at_element: For insert: element label — aperture goes before this element
        aperture_params: For insert: {shape: "circular"|"rectangular", size_x_m, size_y_m}
    """
    from .beamline.manager import probe_aperture as _probe
    return _probe(_get_session(ctx), action, probe_id, at_element, aperture_params)


@mcp.tool()
def truncate_drift(ctx: Context, drift_label: str, truncated_length_m: float) -> dict:
    """Temporarily shorten a drift element to inspect beam at intermediate point.

    Args:
        drift_label: Label of the drift element to truncate
        truncated_length_m: Temporary new length in meters
    """
    from .beamline.manager import truncate_drift as _truncate
    return _truncate(_get_session(ctx), drift_label, truncated_length_m)


@mcp.tool()
def restore_drift(ctx: Context, drift_label: str) -> dict:
    """Restore a previously truncated drift to its original length.

    Args:
        drift_label: Label of the drift to restore
    """
    from .beamline.manager import restore_drift as _restore
    return _restore(_get_session(ctx), drift_label)


@mcp.tool()
def idealize_element(ctx: Context, element_labels: list[str] | str) -> dict:
    """Replace focusing elements with ideal thin-lens + aperture equivalents for validation.

    Args:
        element_labels: List of element labels to idealize, or "all"
    """
    from .beamline.manager import idealize_elements as _idealize
    return _idealize(_get_session(ctx), element_labels)


@mcp.tool()
def restore_elements(ctx: Context, element_labels: list[str] | str) -> dict:
    """Revert idealized elements back to their original realistic definitions.

    Args:
        element_labels: List of element labels to restore, or "all"
    """
    from .beamline.manager import restore_elements as _restore
    return _restore(_get_session(ctx), element_labels)


@mcp.tool()
def get_beamline_state(ctx: Context) -> dict:
    """Return current beamline state: canonical vs working elements, params, probes, idealizations."""
    from .beamline.manager import get_beamline_state as _state
    return _state(_get_session(ctx))


# ---------------------------------------------------------------------------
# Propagation Parameter Control (1)
# ---------------------------------------------------------------------------

@mcp.tool()
def set_propagation_params(ctx: Context, params: dict[str, dict]) -> dict:
    """Set the 5 propagation parameters for one or more elements.

    Args:
        params: element_label -> {mode (0-4), range_x, range_y, resolution_x, resolution_y}

    Mode reference:
    - 0: Standard (2 FFTs) — near waist
    - 1: Quadratic phase subtraction (2 FFTs) — far from waist, grid resizes
    - 2: Quadratic phase subtraction, fixed grid (2 FFTs) — astigmatic beamlines
    - 3: From-waist far-field (1 FFT) — RANGE/RESOLUTION MEANING INVERTED
    - 4: To-waist far-field (1 FFT) — RANGE/RESOLUTION MEANING INVERTED
    """
    from .propagation_params import set_propagation_params as _set
    return _set(_get_session(ctx), params)


# ---------------------------------------------------------------------------
# Simulation Execution (2)
# ---------------------------------------------------------------------------

@mcp.tool()
def run_propagation(ctx: Context,
                    up_to_element: str | None = None,
                    at_element: str | None = None,
                    mesh_params: dict | None = None) -> dict:
    """Run wavefront propagation through the beamline (or subset) with current parameters.

    Args:
        up_to_element: Stop after this element label (None = full beamline)
        at_element: Return intermediates only for this element (None = all)
        mesh_params: Override source mesh if needed
    """
    from .simulation.runner import run_propagation as _run
    return _run(_get_session(ctx), up_to_element, at_element, mesh_params)


@mcp.tool()
def run_convergence_test(ctx: Context,
                         element_label: str | None = None,
                         scaling_factors: list[float] | None = None,
                         axis: str = "both") -> dict:
    """Run simulation at multiple scaling levels to check convergence.

    Mode-aware: for modes 0/1/2 scales resolution; for modes 3/4 scales range.

    Args:
        element_label: Test at this element (None = final)
        scaling_factors: e.g. [0.5, 1.0, 1.5, 2.0]
        axis: "x", "y", or "both"
    """
    from .simulation.convergence import run_convergence_test as _conv
    return _conv(_get_session(ctx), element_label, scaling_factors, axis)


# ---------------------------------------------------------------------------
# Analytical Estimation (2)
# ---------------------------------------------------------------------------

@mcp.tool()
def compute_analytical_estimates(ctx: Context,
                                 at_element: str | None = None) -> dict:
    """Compute expected beam parameters using Gaussian beam propagation / ABCD matrices.

    Returns per-element estimates: FWHM, demagnification, diffraction limit, NA,
    beam-to-aperture ratio, Rayleigh range, distance from waist, wavefront ROC,
    Fresnel number.

    Args:
        at_element: Compute at this element only (None = all elements)
    """
    from .analysis.estimator import compute_analytical_estimates as _est
    return _est(_get_session(ctx), at_element)


@mcp.tool()
def compare_to_estimates(ctx: Context, run_id: str | None = None) -> dict:
    """Compare simulation results against analytical estimates — returns numerical deviations.

    Args:
        run_id: Compare this run (None = latest)
    """
    from .analysis.comparison import compare_to_estimates as _comp
    return _comp(_get_session(ctx), run_id)


# ---------------------------------------------------------------------------
# Hypothesis Testing (1)
# ---------------------------------------------------------------------------

@mcp.tool()
def test_hypothesis(ctx: Context, hypothesis: str,
                    param_changes: dict[str, dict],
                    compare_to_run_id: str | None = None) -> dict:
    """Test a parameter change hypothesis without permanently modifying active parameters.

    Runs simulation with modified params, compares to baseline, then reverts params.

    Args:
        hypothesis: Free-text description for logging
        param_changes: element_label -> param changes to test
        compare_to_run_id: Compare against this run (None = latest)
    """
    from .analysis.hypothesis import test_hypothesis as _test
    return _test(_get_session(ctx), hypothesis, param_changes, compare_to_run_id)


# ---------------------------------------------------------------------------
# Report Data (1)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_report_data(ctx: Context, include_history: bool = False) -> dict:
    """Return all structured data needed for composing a validity report.

    The server provides data; the agent writes the narrative.

    Args:
        include_history: Include full parameter exploration history
    """
    from .report import get_report_data as _report
    return _report(_get_session(ctx), include_history)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
