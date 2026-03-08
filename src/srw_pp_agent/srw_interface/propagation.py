"""Propagation execution: container building, parameter expansion, propagation calls.

This module handles the 5→12 propagation parameter expansion and all
calls to srwl.PropagElecField.
"""

from __future__ import annotations

from typing import Any, Callable

try:
    from srwlib import SRWLOptC, srwl as srwl_main
except ImportError:
    SRWLOptC = None
    srwl_main = None


def expand_5_to_12_params(mode: int, range_x: float, range_y: float,
                          resolution_x: float, resolution_y: float) -> list[float]:
    """Convert the 5 user-facing propagation parameters to the 12-element SRW array.

    The 12-element array is:
    [0] auto-resize before (0=no, 1=yes)
    [1] auto-resize after (0=no, 1=yes)
    [2] relative precision for propagation with auto-resizing
    [3] allow semi-analytical treatment (0=no, 1=yes)
    [4] resize range before: horizontal
    [5] resize resolution before: horizontal
    [6] resize range before: vertical
    [7] resize resolution before: vertical
    [8] resize range after: horizontal
    [9] resize resolution after: horizontal
    [10] resize range after: vertical
    [11] resize resolution after: vertical

    The 5 user-facing params map to the "after" resize slots (indices 8-11)
    with the mode controlling indices 0-3.
    """
    # Default: no auto-resize, apply user params as "after" resize
    params = [0] * 12

    # Set propagation mode
    if mode in (0, 1, 2):
        params[0] = 0  # no auto-resize before
        params[1] = 0  # no auto-resize after
        params[2] = 1.0  # relative precision
        params[3] = mode  # semi-analytical treatment / propagator type
    elif mode in (3, 4):
        params[0] = 0
        params[1] = 0
        params[2] = 1.0
        params[3] = mode

    # Apply resize factors as "after" parameters
    params[8] = range_x
    params[9] = resolution_x
    params[10] = range_y
    params[11] = resolution_y

    return params


def build_propagation_container(elements: list[Any],
                                prop_params_per_element: list[list[float]]) -> Any:
    """Build an SRW optical container from element list and propagation parameter arrays.

    Args:
        elements: List of SRW optical elements
        prop_params_per_element: List of 12-element param arrays, one per element

    Returns:
        SRWLOptC container object
    """
    return SRWLOptC(elements, prop_params_per_element)


def propagate(wfr: Any, container: Any) -> Any:
    """Propagate a wavefront through an optical container.

    Args:
        wfr: SRWLWfr wavefront (modified in-place)
        container: SRWLOptC optical container

    Returns:
        The modified wavefront
    """
    srwl_main.PropagElecField(wfr, container)
    return wfr


def propagate_element_by_element(
    wfr: Any,
    elements: list[Any],
    prop_params_per_element: list[list[float]],
    callback: Callable[[int, str, Any, str], None] | None = None,
    element_labels: list[str] | None = None,
) -> list[dict]:
    """Propagate one element at a time, extracting intermediates.

    Args:
        wfr: Source wavefront (will be modified)
        elements: List of SRW optical elements
        prop_params_per_element: List of 12-element param arrays
        callback: Called after each element with (index, label, wfr, phase)
                  where phase is "before" or "after"
        element_labels: Element labels for callback reporting

    Returns:
        List of intermediate results (populated by callback)
    """
    labels = element_labels or [f"element_{i}" for i in range(len(elements))]
    intermediates = []

    for i, (elem, params) in enumerate(zip(elements, prop_params_per_element)):
        label = labels[i] if i < len(labels) else f"element_{i}"

        # Build single-element container and propagate
        container = SRWLOptC([elem], [params])

        if callback:
            callback(i, label, wfr, "before")

        srwl_main.PropagElecField(wfr, container)

        if callback:
            callback(i, label, wfr, "after")

    return intermediates
