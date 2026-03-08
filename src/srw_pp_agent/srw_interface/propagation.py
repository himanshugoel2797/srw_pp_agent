"""Propagation execution: container building, parameter expansion, propagation calls.

This module handles the 5→12 propagation parameter expansion and all
calls to srwl.PropagElecField.
"""

from __future__ import annotations

from typing import Any, Callable

try:
    from srwlib import SRWLOptC, srwl as srwl_main
except ImportError:
    try:
        from srwpy.srwlib import SRWLOptC, srwl as srwl_main
    except ImportError:
        SRWLOptC = None
        srwl_main = None


def expand_5_to_12_params(mode: int, range_x: float, range_y: float,
                          resolution_x: float, resolution_y: float) -> list[float]:
    """Convert the 5 user-facing propagation parameters to the SRW parameter array.

    The SRW propagation parameter array is:
    [0] Auto-Resize before propagation (0=no, 1=yes)
    [1] Auto-Resize after propagation (0=no, 1=yes)
    [2] Relative precision for auto-resizing (1.0 nominal)
    [3] Semi-analytical treatment of quadratic phase (0=no, 1=yes)
    [4] Do resizing on Fourier side using FFT (0=no, 1=yes)
    [5] Horizontal range resize factor (1.0 = no change)
    [6] Horizontal resolution resize factor (1.0 = no change)
    [7] Vertical range resize factor (1.0 = no change)
    [8] Vertical resolution resize factor (1.0 = no change)
    [9-11] Optional shift parameters

    Mode mapping:
    - 0: Standard (2 FFTs), no semi-analytical
    - 1: Quadratic phase subtraction (2 FFTs), semi-analytical=1
    - 2: Quadratic phase subtraction with fixed grid, semi-analytical=2
    - 3: From-waist far-field (1 FFT), resize on Fourier side
    - 4: To-waist far-field (1 FFT), resize on Fourier side
    """
    params = [0, 0, 1.0, 0,
              0, 1.0, 1.0, 1.0, 1.0,
              0, 0, 0]

    # Set propagation mode
    if mode in (0,):
        params[3] = 0  # no semi-analytical
        params[4] = 0  # resize in real space
    elif mode in (1, 2):
        params[3] = 1  # semi-analytical treatment of quadratic phase
        params[4] = 0  # resize in real space
    elif mode in (3, 4):
        params[3] = 1
        params[4] = 1  # resize on Fourier side

    # Apply resize factors
    params[5] = range_x       # horizontal range
    params[6] = resolution_x  # horizontal resolution
    params[7] = range_y       # vertical range
    params[8] = resolution_y  # vertical resolution

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
