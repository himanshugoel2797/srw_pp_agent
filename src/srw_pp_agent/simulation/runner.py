"""Subprocess orchestration for SRW propagation.

Launches worker.py in a subprocess with timeout and error handling.
Maps subprocess failures to structured SimulationError responses.
"""

from __future__ import annotations

import math
import pickle
import signal
import subprocess
import sys
import time
from typing import Any

from ..errors import SimulationError
from ..session import TuningSession
from ..srw_interface.propagation import expand_5_to_12_params
from ..srw_interface.source import create_source_wavefront
from ..srw_interface.wavefront import copy_wavefront, serialize_wavefront
from ..srw_interface.elements import simplified_to_srw_element
from .cache import WavefrontCache

# Default timeout for a single propagation run
DEFAULT_TIMEOUT_S = 180

# Memory limit: warn if estimated memory exceeds this (bytes)
MEMORY_WARN_THRESHOLD = 4 * 1024**3  # 4 GB


def estimate_memory(nx: int, ny: int) -> int:
    """Estimate memory usage for a wavefront with nx*ny points.

    Each point stores complex E-field for 2 polarizations = 4 floats * 8 bytes.
    """
    return nx * ny * 4 * 8


def _build_propagation_request(
    session: TuningSession,
    up_to_element: str | None = None,
    mesh_params: dict | None = None,
) -> dict | SimulationError:
    """Build common request data for propagation/preview.

    Returns a dict with keys: wfr_data, elements, prop_params, labels,
    or a SimulationError on failure.
    """
    if session.source_wavefront is None:
        return SimulationError(
            error_type="srw_error",
            message="No source wavefront available. Load a beamline first.",
        )

    working_elements = session.working_beamline.get("elements", [])

    # Determine which elements to propagate through
    if up_to_element:
        stop_idx = None
        for i, elem in enumerate(working_elements):
            if elem.get("label") == up_to_element:
                stop_idx = i + 1
                break
        if stop_idx is None:
            return SimulationError(
                error_type="srw_error",
                message=f"Element not found: {up_to_element}",
            )
        working_elements = working_elements[:stop_idx]

    # Build SRW elements and propagation parameter arrays
    srw_elements = []
    prop_params_arrays = []
    labels = []

    for elem in working_elements:
        label = elem.get("label", "")
        labels.append(label)

        try:
            srw_elem = simplified_to_srw_element(elem)
            srw_elements.append(srw_elem)
        except Exception as e:
            return SimulationError(
                error_type="srw_error",
                message=f"Failed to build element {label}: {e}",
                element_label=label,
            )

        # Get propagation params for this element
        params = session.propagation_params.get(label, {
            "mode": 0, "range_x": 1.0, "range_y": 1.0,
            "resolution_x": 1.0, "resolution_y": 1.0,
        })
        param_array = expand_5_to_12_params(
            mode=params.get("mode", 0),
            range_x=params.get("range_x", 1.0),
            range_y=params.get("range_y", 1.0),
            resolution_x=params.get("resolution_x", 1.0),
            resolution_y=params.get("resolution_y", 1.0),
        )
        prop_params_arrays.append(param_array)

    # Estimate memory
    mesh = session.source_wavefront.mesh if session.source_wavefront else None
    if mesh:
        mem = estimate_memory(mesh.nx, mesh.ny)
        if mem > MEMORY_WARN_THRESHOLD:
            return SimulationError(
                error_type="memory_limit",
                message=f"Estimated memory {mem / 1024**3:.1f} GB exceeds threshold",
            )

    # Prepare source wavefront
    if mesh_params is not None:
        wfr = create_source_wavefront(session.canonical_definition["source"], mesh_params)
    else:
        wfr = copy_wavefront(session.source_wavefront)

    wfr_data = serialize_wavefront(wfr)

    return {
        "wfr_data": wfr_data,
        "elements": srw_elements,
        "prop_params": prop_params_arrays,
        "labels": labels,
    }


def run_propagation(
    session: TuningSession,
    up_to_element: str | None = None,
    at_element: str | None = None,
    mesh_params: dict | None = None,
    cache: WavefrontCache | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """Run wavefront propagation through the beamline or a subset.

    Args:
        session: Current tuning session
        up_to_element: Stop after this element (None = full beamline)
        at_element: Return intermediates only for this element (None = all)
        mesh_params: Override source mesh parameters
        cache: Optional wavefront cache
        timeout_s: Timeout in seconds

    Returns:
        Result dict per DESIGN.MD §3.3, or SimulationError.to_dict()
    """
    req_data = _build_propagation_request(session, up_to_element, mesh_params)
    if isinstance(req_data, SimulationError):
        return req_data.to_dict()

    # Build request for worker subprocess
    request = {
        "command": "propagate",
        **req_data,
        "element_by_element": True,
    }

    # Run in subprocess
    start_time = time.time()
    result = _run_in_subprocess(request, timeout_s)
    wall_time = time.time() - start_time

    if isinstance(result, SimulationError):
        result.wall_time_s = wall_time
        return result.to_dict()

    # Process results
    status = result.get("status", "error")

    if status == "nan_inf":
        return SimulationError(
            error_type="nan_inf",
            message=result.get("error", "NaN/Inf detected"),
            wall_time_s=wall_time,
        ).to_dict()

    if status != "ok":
        return SimulationError(
            error_type="srw_error",
            message=result.get("error", "Unknown error"),
            wall_time_s=wall_time,
        ).to_dict()

    # Format output per DESIGN.MD spec
    final = result.get("final_metrics", {})
    intermediates_raw = result.get("intermediates", [])

    # Group intermediates by element (before/after pairs)
    intermediates = _format_intermediates(intermediates_raw, at_element)

    # Compute flux ratios
    source_flux = final.get("total_flux", 1.0)
    for inter in intermediates:
        if source_flux > 0:
            inter["flux_ratio_before_to_source"] = inter.get("before", {}).get("total_flux", 0) / source_flux
            inter["flux_ratio_after_to_source"] = inter.get("after", {}).get("total_flux", 0) / source_flux

    # Record in session history
    run_id = session.record_run(
        results={"final": final, "intermediates": intermediates},
        params=session.propagation_params,
        up_to_element=up_to_element,
        mesh_params=mesh_params,
        wall_time_s=wall_time,
    )

    return {
        "final": final,
        "intermediates": intermediates,
        "wall_time_s": wall_time,
        "run_id": run_id,
    }


def _run_in_subprocess(request: dict, timeout_s: float) -> dict | SimulationError:
    """Launch worker subprocess and communicate via pickle."""
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "srw_pp_agent.simulation.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        request_data = pickle.dumps(request)
        stdout_data, stderr_data = proc.communicate(input=request_data, timeout=timeout_s)

        if proc.returncode < 0:
            sig = -proc.returncode
            sig_name = signal.Signals(sig).name if sig in signal.Signals._value2member_map_ else str(sig)
            return SimulationError(
                error_type="segfault",
                message=f"SRW process killed by signal {sig_name}",
            )

        if proc.returncode != 0:
            return SimulationError(
                error_type="srw_error",
                message=f"Worker exited with code {proc.returncode}: {stderr_data.decode(errors='replace')[:500]}",
            )

        return pickle.loads(stdout_data)

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return SimulationError(
            error_type="timeout",
            message=f"Propagation timed out after {timeout_s}s",
        )
    except Exception as e:
        return SimulationError(
            error_type="srw_error",
            message=f"Subprocess error: {e}",
        )


def run_preview(
    session: TuningSession,
    element_label: str,
    phase: str = "both",
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """Run propagation and return a preview image at the specified element.

    Args:
        session: Current tuning session
        element_label: Element to capture preview at
        phase: "before", "after", or "both"
        timeout_s: Timeout in seconds

    Returns:
        Dict with "image_base64" (PNG) and "media_type", or error dict
    """
    import base64
    from .plotting import render_preview_image

    req_data = _build_propagation_request(session, up_to_element=element_label)
    if isinstance(req_data, SimulationError):
        return req_data.to_dict()

    request = {
        "command": "preview",
        **req_data,
        "target_label": element_label,
        "phase": phase,
    }

    start_time = time.time()
    result = _run_in_subprocess(request, timeout_s)
    wall_time = time.time() - start_time

    if isinstance(result, SimulationError):
        result.wall_time_s = wall_time
        return result.to_dict()

    if result.get("status") != "ok":
        return SimulationError(
            error_type="srw_error",
            message=result.get("error", "Preview failed"),
            wall_time_s=wall_time,
        ).to_dict()

    snapshots = result.get("snapshots", [])
    if not snapshots:
        return SimulationError(
            error_type="srw_error",
            message=f"No snapshots captured for element '{element_label}'. Check the label.",
            wall_time_s=wall_time,
        ).to_dict()

    png_bytes = render_preview_image(snapshots, element_label)

    return {
        "image_base64": base64.b64encode(png_bytes).decode("ascii"),
        "media_type": "image/png",
        "element_label": element_label,
        "phase": phase,
        "wall_time_s": wall_time,
    }


def _format_intermediates(raw: list[dict], at_element: str | None) -> list[dict]:
    """Group raw before/after metrics into per-element intermediate entries."""
    by_element: dict[str, dict] = {}

    for entry in raw:
        label = entry["element_label"]
        idx = entry["element_index"]
        phase = entry["phase"]
        metrics = entry["metrics"]

        if label not in by_element:
            by_element[label] = {
                "element_index": idx,
                "element_label": label,
            }

        by_element[label][phase] = metrics

    result = list(by_element.values())

    if at_element:
        result = [r for r in result if r["element_label"] == at_element]

    return result
