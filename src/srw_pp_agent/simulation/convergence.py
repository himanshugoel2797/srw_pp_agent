"""Convergence test orchestration.

Runs the same beamline at multiple scaling levels. Mode-aware: for modes 0/1/2,
scales resolution; for modes 3/4, scales range (since the meaning is inverted).
"""

from __future__ import annotations

import copy

from ..session import TuningSession
from .runner import run_propagation


async def run_convergence_test(
    session: TuningSession,
    element_label: str | None = None,
    scaling_factors: list[float] | None = None,
    axis: str = "both",
) -> dict:
    """Run convergence test at multiple scaling levels.

    Args:
        session: Current tuning session
        element_label: Test at this element (None = final)
        scaling_factors: e.g. [0.5, 1.0, 1.5, 2.0]
        axis: "x", "y", or "both"

    Returns:
        Convergence test results per DESIGN.MD §3.3
    """
    if scaling_factors is None:
        scaling_factors = [0.5, 1.0, 1.5, 2.0]

    # Determine the active mode at the test element
    test_label = element_label
    if test_label is None:
        elements = session.working_beamline.get("elements", [])
        if elements:
            test_label = elements[-1].get("label", "")

    active_mode = 0
    if test_label and test_label in session.propagation_params:
        active_mode = session.propagation_params[test_label].get("mode", 0)

    # Determine which parameter to scale based on mode
    # Modes 0/1/2: scale resolution (point density)
    # Modes 3/4: scale range (which controls point density for single-FFT modes)
    if active_mode in (3, 4):
        parameter_scaled = "range"
    else:
        parameter_scaled = "resolution"

    # Save original params
    original_params = {k: dict(v) for k, v in session.propagation_params.items()}

    results = []
    for factor in scaling_factors:
        # Apply scaling to target element only
        _apply_scaling(session, factor, parameter_scaled, axis, test_label)

        # Run propagation
        run_result = await run_propagation(session, up_to_element=element_label)

        if "error" in run_result:
            results.append({
                "scaling_factor": factor,
                "error": run_result.get("message", "Error"),
            })
        else:
            final = run_result.get("final", {})
            results.append({
                "scaling_factor": factor,
                "fwhm_x_um": final.get("fwhm_x_um", 0),
                "fwhm_y_um": final.get("fwhm_y_um", 0),
                "peak_intensity": final.get("peak_intensity", 0),
                "total_flux": final.get("total_flux", 0),
                "mesh_nx": final.get("mesh_nx", 0),
                "mesh_ny": final.get("mesh_ny", 0),
                "wall_time_s": run_result.get("wall_time_s", 0),
            })

        # Restore params after each run
        session.propagation_params = {k: dict(v) for k, v in original_params.items()}

    # Record convergence test
    test_record = {
        "element_label": element_label,
        "results": results,
    }
    session.convergence_tests.append(test_record)

    return {
        "active_mode": active_mode,
        "parameter_scaled": parameter_scaled,
        "results": results,
    }


def _apply_scaling(session: TuningSession, factor: float,
                   parameter: str, axis: str,
                   target_label: str | None = None) -> None:
    """Apply scaling factor to propagation params of the target element only."""
    if target_label is None or target_label not in session.propagation_params:
        return

    params = session.propagation_params[target_label]
    if parameter == "resolution":
        if axis in ("x", "both"):
            params["resolution_x"] = params.get("resolution_x", 1.0) * factor
        if axis in ("y", "both"):
            params["resolution_y"] = params.get("resolution_y", 1.0) * factor
    else:  # range
        if axis in ("x", "both"):
            params["range_x"] = params.get("range_x", 1.0) * factor
        if axis in ("y", "both"):
            params["range_y"] = params.get("range_y", 1.0) * factor
