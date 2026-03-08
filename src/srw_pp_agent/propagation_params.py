"""Propagation parameter management: validation, warnings, 5→12 expansion."""

from __future__ import annotations

from .session import TuningSession
from .srw_interface.propagation import expand_5_to_12_params

VALID_MODES = {0, 1, 2, 3, 4}


def set_propagation_params(session: TuningSession, params: dict[str, dict]) -> dict:
    """Set the 5 propagation parameters for one or more elements.

    Args:
        session: Current tuning session
        params: element_label -> {mode, range_x, range_y, resolution_x, resolution_y}

    Returns:
        {applied_params, warnings}
    """
    warnings = []

    for label, p in params.items():
        # Validate label exists
        element_labels = session.get_element_labels()
        if label not in element_labels and label not in session.propagation_params:
            warnings.append(f"Unknown element label: {label}")
            continue

        # Validate and sanitize parameters
        mode = p.get("mode", 0)
        if mode not in VALID_MODES:
            warnings.append(f"{label}: invalid mode {mode}, using 0")
            mode = 0

        range_x = max(0.01, p.get("range_x", 1.0))
        range_y = max(0.01, p.get("range_y", 1.0))
        resolution_x = max(0.01, p.get("resolution_x", 1.0))
        resolution_y = max(0.01, p.get("resolution_y", 1.0))

        # Generate warnings
        warnings.extend(generate_warnings(label, mode, range_x, range_y, resolution_x, resolution_y))

        # Apply
        session.propagation_params[label] = {
            "mode": mode,
            "range_x": range_x,
            "range_y": range_y,
            "resolution_x": resolution_x,
            "resolution_y": resolution_y,
        }

    return {
        "applied_params": {
            label: session.propagation_params.get(label, {})
            for label in params
        },
        "warnings": warnings,
    }


def generate_warnings(label: str, mode: int, range_x: float, range_y: float,
                      resolution_x: float, resolution_y: float) -> list[str]:
    """Generate warnings about propagation parameter choices."""
    warnings = []

    if resolution_x > 4 or resolution_y > 4:
        warnings.append(f"{label}: resolution factor > 4 may be slow")

    if resolution_x > 10 or resolution_y > 10:
        warnings.append(f"{label}: resolution factor > 10 will be very slow and memory-intensive")

    if range_x > 10 or range_y > 10:
        warnings.append(f"{label}: range factor > 10 is unusually large")

    if mode in (3, 4):
        # Remind about inversion
        if range_x != 1.0 or range_y != 1.0:
            warnings.append(
                f"{label}: mode {mode} — range controls point density (inverted from modes 0/1/2)"
            )
        if resolution_x != 1.0 or resolution_y != 1.0:
            warnings.append(
                f"{label}: mode {mode} — resolution controls window size (inverted from modes 0/1/2)"
            )

    return warnings


def get_default_params() -> dict:
    """Return the default propagation parameters."""
    return {
        "mode": 0,
        "range_x": 1.0,
        "range_y": 1.0,
        "resolution_x": 1.0,
        "resolution_y": 1.0,
    }
