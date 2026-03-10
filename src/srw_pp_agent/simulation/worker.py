"""Subprocess entry point for SRW propagation.

This runs in a separate process to isolate the MCP server from SRW crashes,
memory leaks, and hangs. Communicates via pickle over temp files (or
stdin/stdout as fallback).

Protocol (file-based, used when --request/--response are provided):
  request file  <- pickle({command, wfr_data, elements_data, prop_params, labels, ...})
  response file -> pickle({status, results, intermediates, error})

Protocol (legacy stdin/stdout):
  stdin  <- pickle({command, ...})
  stdout -> pickle({status, ...})
"""

from __future__ import annotations

import argparse
import pickle
import sys
import math
import traceback

import numpy as np


def run_worker():
    """Main entry point for the worker subprocess."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default=None, help="Path to pickled request file")
    parser.add_argument("--response", default=None, help="Path to write pickled response")
    args = parser.parse_args()

    use_files = args.request is not None and args.response is not None

    try:
        # Read request
        if use_files:
            with open(args.request, "rb") as f:
                request = pickle.load(f)
        else:
            request = pickle.loads(sys.stdin.buffer.read())

        command = request.get("command", "propagate")

        if command == "propagate":
            result = _do_propagation(request)
        elif command == "preview":
            result = _do_preview(request)
        elif command == "create_source":
            result = _do_create_source(request)
        else:
            result = {"status": "error", "error": f"Unknown command: {command}"}

        # Write result
        if use_files:
            with open(args.response, "wb") as f:
                pickle.dump(result, f)
        else:
            sys.stdout.buffer.write(pickle.dumps(result))
            sys.stdout.buffer.flush()

    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        try:
            if use_files:
                with open(args.response, "wb") as f:
                    pickle.dump(error_result, f)
            else:
                sys.stdout.buffer.write(pickle.dumps(error_result))
                sys.stdout.buffer.flush()
        except Exception:
            pass
        sys.exit(1)


def _do_propagation(request: dict) -> dict:
    """Execute wavefront propagation and extract metrics."""
    from ..srw_interface.wavefront import deserialize_wavefront, serialize_wavefront
    from ..srw_interface.propagation import (
        build_propagation_container,
        propagate,
        propagate_element_by_element,
        expand_5_to_12_params,
    )
    from ..srw_interface.metrics import extract_metrics

    from ..srw_interface.elements import simplified_to_srw_element

    wfr = deserialize_wavefront(request["wfr_data"])
    # Build SRW elements from definitions (can't pickle C extension objects)
    element_defs = request.get("element_defs") or request.get("elements", [])
    if element_defs and isinstance(element_defs[0], dict):
        elements = [simplified_to_srw_element(ed) for ed in element_defs]
    else:
        elements = element_defs  # legacy: pre-built SRW objects
    prop_params = request["prop_params"]  # list of 12-element arrays
    labels = request.get("labels", [])
    element_by_element = request.get("element_by_element", True)

    intermediates = []

    if element_by_element:
        def callback(i, label, wfr, phase):
            metrics = extract_metrics(wfr)
            intermediates.append({
                "element_index": i,
                "element_label": label,
                "phase": phase,
                "metrics": metrics,
            })

        propagate_element_by_element(wfr, elements, prop_params, callback, labels)
    else:
        container = build_propagation_container(elements, prop_params)
        propagate(wfr, container)

    # Extract final metrics
    final_metrics = extract_metrics(wfr)

    # Check for NaN/Inf
    for key, value in final_metrics.items():
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return {
                "status": "nan_inf",
                "error": f"NaN/Inf detected in {key}",
                "final_metrics": final_metrics,
                "intermediates": intermediates,
            }

    return {
        "status": "ok",
        "final_metrics": final_metrics,
        "intermediates": intermediates,
        "wfr_data": serialize_wavefront(wfr),
    }


def _do_preview(request: dict) -> dict:
    """Propagate and capture 2D intensity snapshots at a target element."""
    from ..srw_interface.wavefront import deserialize_wavefront
    from ..srw_interface.propagation import propagate_element_by_element
    from ..srw_interface.metrics import extract_intensity_2d

    from ..srw_interface.elements import simplified_to_srw_element

    wfr = deserialize_wavefront(request["wfr_data"])
    # Build SRW elements from definitions (can't pickle C extension objects)
    element_defs = request.get("element_defs") or request.get("elements", [])
    if element_defs and isinstance(element_defs[0], dict):
        elements = [simplified_to_srw_element(ed) for ed in element_defs]
    else:
        elements = element_defs
    prop_params = request["prop_params"]
    labels = request.get("labels", [])
    target_label = request["target_label"]
    phase = request.get("phase", "both")

    snapshots = []

    def callback(i, label, wfr, cb_phase):
        if label != target_label:
            return
        # Capture "before" and/or "after" based on requested phase
        if phase == "both" or phase == cb_phase:
            intensity_2d, mesh_info = extract_intensity_2d(wfr)
            snapshots.append({
                "phase": cb_phase,
                "intensity_2d": intensity_2d,
                "mesh_info": mesh_info,
            })

    propagate_element_by_element(wfr, elements, prop_params, callback, labels)

    return {
        "status": "ok",
        "snapshots": snapshots,
        "element_label": target_label,
    }


def _do_create_source(request: dict) -> dict:
    """Create a source wavefront in an isolated subprocess."""
    from ..srw_interface.source import create_source_wavefront
    from ..srw_interface.wavefront import serialize_wavefront, get_mesh_info

    source_def = request["source_def"]
    mesh_params = request.get("mesh_params")

    wfr = create_source_wavefront(source_def, mesh_params)
    mesh_info = get_mesh_info(wfr)

    return {
        "status": "ok",
        "wfr_data": serialize_wavefront(wfr),
        "mesh_info": mesh_info,
    }


if __name__ == "__main__":
    run_worker()
