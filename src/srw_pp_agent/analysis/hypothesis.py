"""Hypothesis testing: test parameter changes without permanently modifying them.

Saves current params, applies temporary changes, runs propagation,
computes deltas vs baseline, restores original params.
"""

from __future__ import annotations

from ..session import TuningSession
from ..simulation.runner import run_propagation


def test_hypothesis(
    session: TuningSession,
    hypothesis: str,
    param_changes: dict[str, dict],
    compare_to_run_id: str | None = None,
) -> dict:
    """Test a hypothesis by running with modified params and comparing.

    Args:
        session: Current tuning session
        hypothesis: Free-text description for logging
        param_changes: Element label -> param changes to test
        compare_to_run_id: Compare against this run (None = latest)

    Returns:
        Comparison per DESIGN.MD §3.5
    """
    # Get baseline run
    if compare_to_run_id:
        baseline_run = session.get_run_by_id(compare_to_run_id)
    else:
        baseline_run = session.get_latest_run()

    if baseline_run is None:
        raise ValueError("No baseline run found. Run propagation first.")

    # Save current params
    original_params = {k: dict(v) for k, v in session.propagation_params.items()}

    # Apply temporary changes
    for label, changes in param_changes.items():
        if label in session.propagation_params:
            session.propagation_params[label].update(changes)
        else:
            session.propagation_params[label] = {
                "mode": 0, "range_x": 1.0, "range_y": 1.0,
                "resolution_x": 1.0, "resolution_y": 1.0,
                **changes,
            }

    # Run propagation with modified params
    test_result = run_propagation(session)

    # Restore original params immediately
    session.propagation_params = original_params

    # Extract metrics for comparison
    baseline_final = baseline_run.results.get("final", {})
    test_final = test_result.get("final", {})

    baseline_metrics = {
        "fwhm_x_um": baseline_final.get("fwhm_x_um", 0),
        "fwhm_y_um": baseline_final.get("fwhm_y_um", 0),
        "peak_intensity": baseline_final.get("peak_intensity", 0),
        "total_flux": baseline_final.get("total_flux", 0),
        "wall_time_s": baseline_run.wall_time_s,
    }

    test_metrics = {
        "fwhm_x_um": test_final.get("fwhm_x_um", 0),
        "fwhm_y_um": test_final.get("fwhm_y_um", 0),
        "peak_intensity": test_final.get("peak_intensity", 0),
        "total_flux": test_final.get("total_flux", 0),
        "wall_time_s": test_result.get("wall_time_s", 0),
    }

    # Compute deltas
    def pct_change(new, old):
        if old == 0:
            return 0.0 if new == 0 else float('inf')
        return (new - old) / old * 100.0

    deltas = {
        "fwhm_x_change_pct": pct_change(test_metrics["fwhm_x_um"], baseline_metrics["fwhm_x_um"]),
        "fwhm_y_change_pct": pct_change(test_metrics["fwhm_y_um"], baseline_metrics["fwhm_y_um"]),
        "flux_change_pct": pct_change(test_metrics["total_flux"], baseline_metrics["total_flux"]),
        "speedup_factor": baseline_metrics["wall_time_s"] / max(test_metrics["wall_time_s"], 0.001),
    }

    # Get test run_id
    test_run = session.get_latest_run()
    test_run_id = test_run.run_id if test_run else "unknown"

    return {
        "hypothesis": hypothesis,
        "baseline_run_id": baseline_run.run_id,
        "test_run_id": test_run_id,
        "baseline": baseline_metrics,
        "test": test_metrics,
        "deltas": deltas,
        "params_reverted": True,
    }
