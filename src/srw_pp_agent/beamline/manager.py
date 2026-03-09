"""High-level beamline operations that modify session state.

Each function that modifies the beamline triggers a working beamline rebuild
and cache invalidation for downstream wavefronts.
"""

from __future__ import annotations

import copy
import uuid

from ..session import TuningSession
from ..srw_interface.idealization import get_idealization_info
from ..srw_interface.source import detect_source_type
from ..srw_interface.wavefront import get_mesh_info
from .builder import rebuild_working_beamline
from .definition import (
    assign_cumulative_distances,
    find_element_index,
    format_element_list,
    get_total_length,
    parse_beamline_definition,
)


async def load_beamline(session: TuningSession, beamline_definition: dict | str) -> dict:
    """Parse and load a beamline definition, cache source wavefront.

    Returns structured summary per DESIGN.MD §3.1 load_beamline output.
    """
    definition = parse_beamline_definition(beamline_definition)

    session.original_definition = copy.deepcopy(definition)
    session.canonical_definition = copy.deepcopy(definition)
    session.active_probes = {}
    session.idealized_elements = {}
    session.truncated_drifts = {}
    session.simulation_history = []
    session.analytical_estimates = {}
    session.edit_log = []
    session.convergence_tests = []
    session.idealization_tests = []

    # Initialize default propagation params for all elements
    session.propagation_params = {}
    for elem in definition["elements"]:
        label = elem.get("label", "")
        session.propagation_params[label] = {
            "mode": 0,
            "range_x": 1.0,
            "range_y": 1.0,
            "resolution_x": 1.0,
            "resolution_y": 1.0,
        }

    # Create source wavefront in a subprocess to avoid blocking the MCP event loop
    source_def = definition.get("source", {})
    from ..simulation.runner import create_source_in_subprocess
    src_result = await create_source_in_subprocess(source_def)
    if "error" in src_result:
        session.source_wavefront = None
        session._source_error = src_result["error"]
        source_mesh = {
            "nx": 0, "ny": 0,
            "range_x_mm": 0.0, "range_y_mm": 0.0,
            "pitch_x_um": 0.0, "pitch_y_um": 0.0,
        }
    else:
        session.source_wavefront = src_result["wfr"]
        source_mesh = src_result["mesh_info"]

    # Build working beamline
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )
    session._loaded = True

    elements_out = format_element_list(
        session.working_beamline["elements"],
        session.propagation_params,
    )

    return {
        "source_type": detect_source_type(source_def),
        "photon_energy_eV": source_def.get("energy_eV", 0.0),
        "source_mesh": source_mesh,
        "elements": elements_out,
        "total_length_m": get_total_length(definition["elements"]),
    }


def edit_beamline(session: TuningSession, action: str, target_label: str,
                  insert_before: str | None = None,
                  element_definition: dict | None = None) -> dict:
    """Make permanent corrections to the beamline definition."""
    _require_loaded(session)

    elements = session.canonical_definition["elements"]

    if action == "insert":
        if element_definition is None:
            raise ValueError("element_definition required for insert action")
        if insert_before:
            idx = find_element_index(elements, insert_before)
        else:
            idx = len(elements)
        elements.insert(idx, element_definition)
        session.edit_log.append(f"Inserted {element_definition.get('label', '?')} before {insert_before}")

        # Add default propagation params for new element
        label = element_definition.get("label", "")
        if label:
            session.propagation_params[label] = {
                "mode": 0, "range_x": 1.0, "range_y": 1.0,
                "resolution_x": 1.0, "resolution_y": 1.0,
            }

    elif action == "remove":
        idx = find_element_index(elements, target_label)
        elements.pop(idx)
        session.edit_log.append(f"Removed {target_label}")
        session.propagation_params.pop(target_label, None)

    elif action == "edit":
        if element_definition is None:
            raise ValueError("element_definition required for edit action")
        idx = find_element_index(elements, target_label)
        # Preserve label if not in new definition
        if "label" not in element_definition:
            element_definition["label"] = target_label
        elements[idx] = element_definition
        session.edit_log.append(f"Edited {target_label}")

    else:
        raise ValueError(f"Unknown action: {action}")

    # Recompute cumulative distances
    session.canonical_definition["elements"] = assign_cumulative_distances(elements)

    # Rebuild working beamline
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )

    return {
        "updated_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
        "updated_definition": session.canonical_definition,
    }


def probe_aperture(session: TuningSession, action: str,
                   probe_id: str | None = None,
                   at_element: str | None = None,
                   aperture_params: dict | None = None) -> dict:
    """Temporarily insert or remove a diagnostic aperture."""
    _require_loaded(session)

    result_probe_id = None

    if action == "insert":
        if at_element is None or aperture_params is None:
            raise ValueError("at_element and aperture_params required for insert")
        result_probe_id = f"probe_{uuid.uuid4().hex[:8]}"
        session.active_probes[result_probe_id] = {
            "at_element": at_element,
            "aperture_params": aperture_params,
        }

    elif action == "remove":
        if probe_id is None:
            raise ValueError("probe_id required for remove")
        session.active_probes.pop(probe_id, None)

    elif action == "remove_all":
        session.active_probes.clear()

    else:
        raise ValueError(f"Unknown action: {action}")

    # Rebuild working beamline
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )

    active_probes_list = [
        {
            "probe_id": pid,
            "at_element": pdef["at_element"],
            "aperture_params": pdef["aperture_params"],
        }
        for pid, pdef in session.active_probes.items()
    ]

    return {
        "probe_id": result_probe_id,
        "active_probes": active_probes_list,
        "updated_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
    }


def truncate_drift(session: TuningSession, drift_label: str,
                   truncated_length_m: float) -> dict:
    """Temporarily shorten a drift element."""
    _require_loaded(session)

    elements = session.canonical_definition["elements"]
    elem = None
    for e in elements:
        if e.get("label") == drift_label:
            elem = e
            break

    if elem is None:
        raise ValueError(f"Drift not found: {drift_label}")
    if elem.get("type", "").lower() != "drift":
        raise ValueError(f"Element {drift_label} is not a drift")

    original_length = elem.get("length_m", 0.0)

    # Store original length for restore
    session.truncated_drifts[drift_label] = original_length

    # Mark the truncated length on the canonical element for the builder
    elem["_truncated_length_m"] = truncated_length_m

    # Rebuild working beamline
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )

    return {
        "original_length_m": original_length,
        "truncated_length_m": truncated_length_m,
        "updated_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
    }


def restore_drift(session: TuningSession, drift_label: str) -> dict:
    """Restore a previously truncated drift to its original length."""
    _require_loaded(session)

    if drift_label not in session.truncated_drifts:
        raise ValueError(f"Drift not truncated: {drift_label}")

    original_length = session.truncated_drifts.pop(drift_label)

    # Remove the truncation marker from canonical
    for elem in session.canonical_definition["elements"]:
        if elem.get("label") == drift_label:
            elem.pop("_truncated_length_m", None)
            break

    # Rebuild
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )

    return {
        "restored_length_m": original_length,
        "updated_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
    }


def idealize_elements(session: TuningSession,
                      element_labels: list[str] | str) -> dict:
    """Replace focusing elements with ideal thin-lens + aperture equivalents."""
    _require_loaded(session)

    if element_labels == "all":
        # Find all focusing elements
        focusing_types = {"mirror", "crl", "zone_plate"}
        element_labels = [
            e["label"] for e in session.canonical_definition["elements"]
            if e.get("type", "").lower() in focusing_types
            and e.get("focal_length_m") is not None  # only curved mirrors
        ]
        # Also include CRLs and zone plates regardless of focal_length
        for e in session.canonical_definition["elements"]:
            etype = e.get("type", "").lower()
            if etype in ("crl", "zone_plate") and e["label"] not in element_labels:
                element_labels.append(e["label"])

    idealizations_applied = []
    for label in element_labels:
        if label in session.idealized_elements:
            continue  # already idealized

        # Find the element in canonical
        elem = None
        for e in session.canonical_definition["elements"]:
            if e.get("label") == label:
                elem = e
                break

        if elem is None:
            continue

        # Store original for restore
        session.idealized_elements[label] = copy.deepcopy(elem)
        idealizations_applied.append(get_idealization_info(elem))

    # Rebuild
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )

    return {
        "idealizations_applied": idealizations_applied,
        "updated_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
    }


def restore_elements(session: TuningSession,
                     element_labels: list[str] | str) -> dict:
    """Revert idealized elements back to their original definitions."""
    _require_loaded(session)

    if element_labels == "all":
        element_labels = list(session.idealized_elements.keys())

    restored = []
    for label in element_labels:
        if label in session.idealized_elements:
            session.idealized_elements.pop(label)
            restored.append(label)

    # Rebuild
    session.working_beamline = rebuild_working_beamline(
        session.canonical_definition,
        session.active_probes,
        session.idealized_elements,
        session.truncated_drifts,
    )

    return {
        "restored_elements": restored,
        "updated_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
    }


def get_beamline_state(session: TuningSession) -> dict:
    """Return the current beamline state for agent orientation."""
    _require_loaded(session)

    return {
        "canonical_elements": format_element_list(
            session.canonical_definition["elements"],
            session.propagation_params,
        ),
        "working_elements": format_element_list(
            session.working_beamline["elements"],
            session.propagation_params,
        ),
        "propagation_params": session.propagation_params,
        "edit_log": session.edit_log,
        "active_probes": [
            {"probe_id": pid, "at_element": p["at_element"], "aperture_params": p["aperture_params"]}
            for pid, p in session.active_probes.items()
        ],
        "idealized_elements": list(session.idealized_elements.keys()),
        "truncated_drifts": list(session.truncated_drifts.keys()),
        "run_count": len(session.simulation_history),
    }


def _require_loaded(session: TuningSession) -> None:
    """Raise if no beamline has been loaded."""
    if not session.is_loaded:
        raise ValueError("No beamline loaded. Call load_beamline first.")
