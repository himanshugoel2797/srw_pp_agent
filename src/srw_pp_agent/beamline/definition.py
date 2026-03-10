"""Beamline definition parsing, validation, and label management."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


def parse_beamline_definition(raw: dict | str) -> dict:
    """Parse a beamline definition from simplified JSON, file path, or SRW-native format.

    Returns a normalized internal canonical form:
    {
        "source": { ... },
        "elements": [ { type, label, ... }, ... ]
    }
    """
    if isinstance(raw, str):
        path = Path(raw)
        if path.exists():
            with open(path) as f:
                if path.suffix == ".json":
                    raw = json.load(f)
                else:
                    # Python file — execute and look for beamline definition
                    raw = _load_from_python_file(path)
        else:
            # Try to parse as JSON string
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raise ValueError(f"Cannot parse beamline definition: not a valid file path or JSON string")

    if not isinstance(raw, dict):
        raise ValueError("Beamline definition must be a dict")

    # Normalize
    definition = _normalize_definition(raw)
    validate_labels_unique(definition["elements"])
    first_optic_dist = definition.get("source", {}).get("first_optic_distance_m", 0.0)
    definition["elements"] = assign_cumulative_distances(definition["elements"], first_optic_dist)
    definition["elements"] = compute_smallest_feature_sizes(definition["elements"])

    return definition


def _normalize_definition(raw: dict) -> dict:
    """Normalize to the internal canonical form."""
    definition = copy.deepcopy(raw)

    # Ensure source exists
    if "source" not in definition:
        definition["source"] = {"type": "gaussian", "energy_eV": 12000}

    # Ensure elements is a list
    if "elements" not in definition:
        definition["elements"] = []

    # Ensure every element has a label
    for i, elem in enumerate(definition["elements"]):
        if "label" not in elem:
            elem_type = elem.get("type", "unknown")
            elem["label"] = f"{elem_type}_{i}"

    return definition


def validate_labels_unique(elements: list[dict]) -> None:
    """Raise ValueError if any element labels are duplicated."""
    labels = [e.get("label", "") for e in elements]
    seen = set()
    for label in labels:
        if label in seen:
            raise ValueError(f"Duplicate element label: {label}")
        seen.add(label)


def assign_cumulative_distances(elements: list[dict], initial_distance: float = 0.0) -> list[dict]:
    """Compute cumulative_distance_m for each element.

    Args:
        elements: List of element dicts.
        initial_distance: Distance from source to the first optical element (op_r).
    """
    distance = initial_distance
    for elem in elements:
        elem_type = elem.get("type", "").lower()
        if elem_type == "drift":
            distance += elem.get("length_m", 0.0)
        elem["cumulative_distance_m"] = distance
    return elements


def compute_smallest_feature_sizes(elements: list[dict]) -> list[dict]:
    """Annotate elements with their smallest_feature_size_m."""
    for elem in elements:
        elem_type = elem.get("type", "").lower()
        if elem_type == "zone_plate":
            elem["smallest_feature_size_m"] = elem.get("outermost_zone_width_m")
        elif elem_type == "grating":
            elem["smallest_feature_size_m"] = elem.get("grating_pitch_m")
        else:
            elem["smallest_feature_size_m"] = None
    return elements


def get_total_length(elements: list[dict]) -> float:
    """Compute total beamline length in meters."""
    total = 0.0
    for elem in elements:
        if elem.get("type", "").lower() == "drift":
            total += elem.get("length_m", 0.0)
    return total


def find_element_index(elements: list[dict], label: str) -> int:
    """Find the index of an element by label. Raises ValueError if not found."""
    for i, elem in enumerate(elements):
        if elem.get("label") == label:
            return i
    raise ValueError(f"Element not found: {label}")


def get_element_by_label(elements: list[dict], label: str) -> dict:
    """Get an element by its label. Raises ValueError if not found."""
    idx = find_element_index(elements, label)
    return elements[idx]


def format_element_list(elements: list[dict], prop_params: dict[str, dict] | None = None) -> list[dict]:
    """Format elements for output in tool responses."""
    from ..srw_interface.elements import get_element_summary

    result = []
    for i, elem in enumerate(elements):
        summary = get_element_summary(elem)
        entry = {
            "index": i,
            "type": summary["type"],
            "label": summary["label"],
            "key_params": summary["key_params"],
            "cumulative_distance_m": elem.get("cumulative_distance_m", 0.0),
            "smallest_feature_size_m": summary["smallest_feature_size_m"],
        }
        if prop_params and summary["label"] in prop_params:
            entry["current_propagation_params"] = prop_params[summary["label"]]
        else:
            entry["current_propagation_params"] = {
                "mode": 0, "range_x": 1.0, "range_y": 1.0,
                "resolution_x": 1.0, "resolution_y": 1.0,
            }
        result.append(entry)
    return result


def _load_from_python_file(path: Path) -> dict:
    """Load a beamline definition from a Python file.

    Supports two formats:
    1. Simplified JSON style — looks for ``beamline_definition``, ``beamline``,
       or ``bl`` variable containing a dict.
    2. SRW-native style — looks for ``varParam`` list (Sirepo/SRW standard
       parameter format) and converts it to simplified JSON.
    """
    source_text = path.read_text()

    # First, try a safe stubbed parse for SRW-native scripts (varParam style).
    # This avoids running heavy SRW simulations when we only need the parameters.
    from .srw_script_parser import parse_srw_script
    try:
        result = parse_srw_script(path)
        return result
    except ValueError:
        pass  # No varParam found — fall through to simplified format

    # Fall back to direct execution for simplified-format Python files
    # that define beamline_definition / beamline / bl variables.
    namespace: dict[str, Any] = {}
    exec(source_text, namespace)  # noqa: S102

    for name in ("beamline_definition", "beamline", "bl"):
        if name in namespace:
            return namespace[name]

    raise ValueError(f"No beamline definition found in {path}")
