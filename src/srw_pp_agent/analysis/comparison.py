"""Compare simulation results against analytical estimates.

Returns numerical deviations only — the agent interprets physical meaning.
"""

from __future__ import annotations

from ..session import TuningSession


def compare_to_estimates(session: TuningSession, run_id: str | None = None) -> dict:
    """Compare a simulation run against analytical estimates.

    Args:
        session: Current tuning session
        run_id: Compare this run (None = latest)

    Returns:
        Comparison per DESIGN.MD §3.4
    """
    # Get the run to compare
    if run_id:
        run = session.get_run_by_id(run_id)
    else:
        run = session.get_latest_run()

    if run is None:
        raise ValueError("No simulation run found" + (f" with id {run_id}" if run_id else ""))

    # Get analytical estimates
    estimates = session.analytical_estimates.get("estimates", [])
    if not estimates:
        raise ValueError("No analytical estimates computed. Call compute_analytical_estimates first.")

    # Build comparison
    run_results = run.results
    intermediates = run_results.get("intermediates", [])
    final = run_results.get("final", {})

    # Build lookup of sim results by element label
    sim_by_label = {}
    for inter in intermediates:
        label = inter.get("element_label", "")
        # Use the "after" metrics if available
        after = inter.get("after", inter.get("before", {}))
        sim_by_label[label] = after

    # Also add "final" as a special entry
    sim_by_label["_final"] = final

    comparisons = []
    for est in estimates:
        label = est["element_label"]
        sim = sim_by_label.get(label, {})

        if not sim:
            continue

        sim_fwhm_x = sim.get("fwhm_x_um", 0)
        sim_fwhm_y = sim.get("fwhm_y_um", 0)
        est_fwhm_x = est.get("expected_fwhm_x_um", 0)
        est_fwhm_y = est.get("expected_fwhm_y_um", 0)

        dev_x = _pct_deviation(sim_fwhm_x, est_fwhm_x)
        dev_y = _pct_deviation(sim_fwhm_y, est_fwhm_y)

        comparisons.append({
            "element_index": est["element_index"],
            "element_label": label,
            "simulated_fwhm_x_um": sim_fwhm_x,
            "estimated_fwhm_x_um": est_fwhm_x,
            "deviation_x_pct": dev_x,
            "simulated_fwhm_y_um": sim_fwhm_y,
            "estimated_fwhm_y_um": est_fwhm_y,
            "deviation_y_pct": dev_y,
        })

    # Flux conservation
    source_flux = final.get("total_flux", 1.0)
    final_flux = final.get("total_flux", 0.0)
    flux_ratio = final_flux / source_flux if source_flux > 0 else 0.0

    return {
        "comparisons": comparisons,
        "flux_conservation": {
            "source_flux": source_flux,
            "final_flux": final_flux,
            "ratio": flux_ratio,
        },
    }


def _pct_deviation(simulated: float, estimated: float) -> float:
    """Compute percentage deviation of simulated from estimated."""
    if estimated == 0:
        return 0.0 if simulated == 0 else float('inf')
    return (simulated - estimated) / estimated * 100.0
