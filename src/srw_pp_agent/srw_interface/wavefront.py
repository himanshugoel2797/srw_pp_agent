"""Wavefront manipulation: copy, serialize, deserialize, resize."""

from __future__ import annotations

import copy
import pickle
from typing import Any

try:
    from srwlib import srwl as srwl_main
except ImportError:
    srwl_main = None


def copy_wavefront(wfr: Any) -> Any:
    """Deep copy a wavefront object for caching/branching."""
    return copy.deepcopy(wfr)


def serialize_wavefront(wfr: Any) -> bytes:
    """Serialize a wavefront for subprocess transfer."""
    return pickle.dumps(wfr)


def deserialize_wavefront(data: bytes) -> Any:
    """Deserialize a wavefront from bytes."""
    return pickle.loads(data)


def resize_wavefront(wfr: Any, range_x: float = 1.0, range_y: float = 1.0,
                     resolution_x: float = 1.0, resolution_y: float = 1.0) -> Any:
    """Resize the wavefront mesh using SRW's ResizeElecField.

    Args:
        wfr: Wavefront to resize (modified in-place)
        range_x: Horizontal range resize factor
        range_y: Vertical range resize factor
        resolution_x: Horizontal resolution resize factor
        resolution_y: Vertical resolution resize factor
    """
    srwl_main.ResizeElecField(wfr, "c", [
        0,  # method (0 = standard)
        range_x, resolution_x,
        range_y, resolution_y,
    ])
    return wfr


def get_mesh_info(wfr: Any) -> dict:
    """Extract mesh information from a wavefront."""
    mesh = wfr.mesh
    nx, ny = mesh.nx, mesh.ny
    range_x = mesh.xFin - mesh.xStart
    range_y = mesh.yFin - mesh.yStart

    return {
        "nx": nx,
        "ny": ny,
        "range_x_mm": range_x * 1e3,
        "range_y_mm": range_y * 1e3,
        "pitch_x_um": (range_x / max(nx - 1, 1)) * 1e6,
        "pitch_y_um": (range_y / max(ny - 1, 1)) * 1e6,
    }
