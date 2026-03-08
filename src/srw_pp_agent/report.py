"""Report data aggregation for get_report_data tool.

Collects all structured data the agent needs to compose a validity report.
The server provides data; the agent writes the narrative.
"""

from __future__ import annotations

from .session import TuningSession
from .beamline.definition import format_element_list, get_total_length
from .srw_interface.source import detect_source_type


def get_report_data(session: TuningSession, include_history: bool = False) -> dict:
    """Return all data needed for composing a validity report.

    Returns per DESIGN.MD §3.6.
    """
    source = session.canonical_definition.get("source", {})

    beamline_summary = {
        "source_type": detect_source_type(source),
        "photon_energy_eV": source.get("energy_eV", 0.0),
        "canonical_elements": format_element_list(
            session.canonical_definition.get("elements", []),
            session.propagation_params,
        ),
        "total_length_m": get_total_length(session.canonical_definition.get("elements", [])),
        "edits_from_original": list(session.edit_log),
    }

    propagation_parameters = [
        {
            "element_label": label,
            **params,
        }
        for label, params in session.propagation_params.items()
    ]

    # Latest estimates and comparison
    latest_estimates = session.analytical_estimates

    latest_comparison = None
    latest_run = session.get_latest_run()
    if latest_run and latest_estimates:
        from .analysis.comparison import compare_to_estimates
        try:
            latest_comparison = compare_to_estimates(session)
        except ValueError:
            latest_comparison = None

    result = {
        "beamline_summary": beamline_summary,
        "corrected_definition": session.canonical_definition,
        "propagation_parameters": propagation_parameters,
        "latest_estimates": latest_estimates,
        "latest_comparison": latest_comparison,
        "convergence_tests": session.convergence_tests,
        "idealization_tests": session.idealization_tests,
    }

    if include_history:
        result["simulation_history"] = [
            {
                "run_id": run.run_id,
                "timestamp": run.timestamp.isoformat(),
                "propagation_params": run.propagation_params,
                "up_to_element": run.up_to_element,
                "wall_time_s": run.wall_time_s,
                "final_fwhm_x_um": run.results.get("final", {}).get("fwhm_x_um"),
                "final_fwhm_y_um": run.results.get("final", {}).get("fwhm_y_um"),
                "final_flux": run.results.get("final", {}).get("total_flux"),
            }
            for run in session.simulation_history
        ]
    else:
        result["simulation_history"] = None

    return result
