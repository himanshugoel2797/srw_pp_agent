"""Rebuild working beamline from canonical + probes + idealizations + truncations.

The working beamline is what's actually simulated. It's rebuilt from scratch
on every modification (cheap: list operations, no SRW calls).
"""

from __future__ import annotations

import copy

from ..srw_interface.idealization import idealize_element as compute_idealization
from .definition import assign_cumulative_distances, validate_labels_unique


def rebuild_working_beamline(
    canonical_definition: dict,
    active_probes: dict[str, dict],
    idealized_elements: dict[str, dict],
    truncated_drifts: dict[str, float],
) -> dict:
    """Rebuild the working beamline from its components.

    Application order:
    1. Start from canonical definition
    2. Apply idealizations (replace elements)
    3. Apply truncations (shorten drifts)
    4. Insert probes (add apertures at specified positions)

    Args:
        canonical_definition: The corrected beamline (edit_beamline changes only)
        active_probes: probe_id -> {at_element, aperture_params}
        idealized_elements: label -> original element def (stored for restore)
        truncated_drifts: label -> original length (stored for restore)

    Returns:
        Complete working beamline definition dict
    """
    working = copy.deepcopy(canonical_definition)
    elements = working.get("elements", [])

    # 1. Apply idealizations
    elements = _apply_idealizations(elements, idealized_elements)

    # 2. Apply truncations
    elements = _apply_truncations(elements, truncated_drifts)

    # 3. Insert probes
    elements = _apply_probes(elements, active_probes)

    # Recompute cumulative distances
    elements = assign_cumulative_distances(elements)

    working["elements"] = elements
    return working


def _apply_idealizations(elements: list[dict],
                         idealized_elements: dict[str, dict]) -> list[dict]:
    """Replace idealized elements with their ideal equivalents."""
    if not idealized_elements:
        return elements

    result = []
    for elem in elements:
        label = elem.get("label", "")
        if label in idealized_elements:
            # Replace with ideal equivalent(s)
            ideal_replacements = compute_idealization(elem)
            result.extend(ideal_replacements)
        else:
            result.append(elem)

    return result


def _apply_truncations(elements: list[dict],
                       truncated_drifts: dict[str, float]) -> list[dict]:
    """Shorten truncated drifts to their temporary lengths."""
    if not truncated_drifts:
        return elements

    for elem in elements:
        label = elem.get("label", "")
        if label in truncated_drifts and elem.get("type", "").lower() == "drift":
            # truncated_drifts stores original_length, but we need to set the truncated length
            # The truncated length is stored separately; here we need to know the target
            # This is handled by storing the truncated length in the element itself
            # The manager sets _truncated_length_m when truncating
            if "_truncated_length_m" in elem:
                elem["length_m"] = elem["_truncated_length_m"]

    return elements


def _apply_probes(elements: list[dict],
                  active_probes: dict[str, dict]) -> list[dict]:
    """Insert probe apertures before specified elements."""
    if not active_probes:
        return elements

    # Collect probes grouped by their target element
    probes_by_target: dict[str, list[dict]] = {}
    for probe_id, probe_def in active_probes.items():
        target = probe_def.get("at_element", "")
        if target not in probes_by_target:
            probes_by_target[target] = []

        aperture_params = probe_def.get("aperture_params", {})
        probe_element = {
            "type": "aperture",
            "label": f"probe_{probe_id}",
            "shape": aperture_params.get("shape", "rectangular"),
            "size_x_m": aperture_params.get("size_x_m", 0.001),
            "size_y_m": aperture_params.get("size_y_m", 0.001),
            "_is_probe": True,
        }
        probes_by_target[target].append(probe_element)

    # Insert probes before their target elements
    result = []
    for elem in elements:
        label = elem.get("label", "")
        if label in probes_by_target:
            result.extend(probes_by_target[label])
        result.append(elem)

    return result
