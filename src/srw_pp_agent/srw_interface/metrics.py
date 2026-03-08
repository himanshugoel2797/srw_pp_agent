"""Wavefront metrics extraction: FWHM, flux, centroid, edge intensity ratios.

FWHM is computed from the actual intensity profile, NOT from Gaussian fits,
since the beam may be far from Gaussian.
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    import srwlib as srwl
    from srwlib import srwl as srwl_main
except ImportError:
    srwl = None
    srwl_main = None


def extract_metrics(wfr: Any) -> dict:
    """Extract full set of beam metrics from a wavefront.

    Returns dict with: fwhm_x_um, fwhm_y_um, peak_intensity, total_flux,
    mesh_nx, mesh_ny, mesh_range_x_mm, mesh_range_y_mm,
    mesh_pitch_x_um, mesh_pitch_y_um, rms_x_um, rms_y_um,
    centroid_x_um, centroid_y_um, edge_intensity_ratio_x, edge_intensity_ratio_y
    """
    intensity_2d, mesh_info = extract_intensity_2d(wfr)

    proj_x = compute_1d_projection(intensity_2d, axis="x")
    proj_y = compute_1d_projection(intensity_2d, axis="y")

    coords_x = np.linspace(mesh_info["x_start"], mesh_info["x_fin"], mesh_info["nx"])
    coords_y = np.linspace(mesh_info["y_start"], mesh_info["y_fin"], mesh_info["ny"])

    fwhm_x = compute_fwhm_from_profile(proj_x, coords_x)
    fwhm_y = compute_fwhm_from_profile(proj_y, coords_y)

    peak_intensity = float(np.max(intensity_2d))
    total_flux = compute_total_flux(intensity_2d, mesh_info)

    centroid_x, centroid_y = compute_centroid(intensity_2d, mesh_info)
    rms_x = compute_rms_size(intensity_2d, mesh_info, "x")
    rms_y = compute_rms_size(intensity_2d, mesh_info, "y")

    edge_ratio_x = compute_edge_intensity_ratio(intensity_2d, "x")
    edge_ratio_y = compute_edge_intensity_ratio(intensity_2d, "y")

    range_x_mm = (mesh_info["x_fin"] - mesh_info["x_start"]) * 1e3
    range_y_mm = (mesh_info["y_fin"] - mesh_info["y_start"]) * 1e3
    pitch_x_um = (range_x_mm / mesh_info["nx"] * 1e3) if mesh_info["nx"] > 1 else 0.0
    pitch_y_um = (range_y_mm / mesh_info["ny"] * 1e3) if mesh_info["ny"] > 1 else 0.0

    return {
        "fwhm_x_um": fwhm_x * 1e6,
        "fwhm_y_um": fwhm_y * 1e6,
        "peak_intensity": peak_intensity,
        "total_flux": total_flux,
        "mesh_nx": mesh_info["nx"],
        "mesh_ny": mesh_info["ny"],
        "mesh_range_x_mm": range_x_mm,
        "mesh_range_y_mm": range_y_mm,
        "mesh_pitch_x_um": pitch_x_um,
        "mesh_pitch_y_um": pitch_y_um,
        "rms_x_um": rms_x * 1e6,
        "rms_y_um": rms_y * 1e6,
        "centroid_x_um": centroid_x * 1e6,
        "centroid_y_um": centroid_y * 1e6,
        "edge_intensity_ratio_x": edge_ratio_x,
        "edge_intensity_ratio_y": edge_ratio_y,
    }


def extract_intensity_2d(wfr: Any) -> tuple[np.ndarray, dict]:
    """Extract 2D intensity array and mesh info from a wavefront."""
    mesh = wfr.mesh
    nx = mesh.nx
    ny = mesh.ny

    # Use srwl to calculate intensity (polarization component 6 = total)
    intensity_flat = srwl_main.CalcIntFromElecField(wfr, 6, 0, 3, mesh.eStart, 0, 0)
    intensity_2d = np.array(intensity_flat).reshape((ny, nx))

    mesh_info = {
        "nx": nx,
        "ny": ny,
        "x_start": mesh.xStart,
        "x_fin": mesh.xFin,
        "y_start": mesh.yStart,
        "y_fin": mesh.yFin,
    }
    return intensity_2d, mesh_info


def compute_1d_projection(intensity_2d: np.ndarray, axis: str) -> np.ndarray:
    """Compute 1D projection by integrating over the other axis."""
    if axis == "x":
        return np.sum(intensity_2d, axis=0)  # sum over y (rows)
    else:
        return np.sum(intensity_2d, axis=1)  # sum over x (columns)


def compute_fwhm_from_profile(profile: np.ndarray, coordinates: np.ndarray) -> float:
    """Compute FWHM from actual intensity profile using half-max crossing interpolation."""
    if len(profile) < 3 or np.max(profile) <= 0:
        return 0.0

    peak = np.max(profile)
    half_max = peak / 2.0

    # Find crossings above half-max
    above = profile >= half_max
    indices = np.where(above)[0]

    if len(indices) < 2:
        return 0.0

    # Interpolate left crossing
    left_idx = indices[0]
    if left_idx > 0:
        # Linear interpolation between left_idx-1 and left_idx
        y0, y1 = profile[left_idx - 1], profile[left_idx]
        x0, x1 = coordinates[left_idx - 1], coordinates[left_idx]
        if y1 != y0:
            left_pos = x0 + (half_max - y0) * (x1 - x0) / (y1 - y0)
        else:
            left_pos = x0
    else:
        left_pos = coordinates[0]

    # Interpolate right crossing
    right_idx = indices[-1]
    if right_idx < len(profile) - 1:
        y0, y1 = profile[right_idx], profile[right_idx + 1]
        x0, x1 = coordinates[right_idx], coordinates[right_idx + 1]
        if y0 != y1:
            right_pos = x0 + (half_max - y0) * (x1 - x0) / (y1 - y0)
        else:
            right_pos = x1
    else:
        right_pos = coordinates[-1]

    return abs(right_pos - left_pos)


def compute_edge_intensity_ratio(intensity_2d: np.ndarray, axis: str) -> float:
    """Compute max intensity in outer 10% of mesh / peak intensity.

    Should be ~0. If significantly >0, beam is clipped by mesh boundary.
    """
    peak = np.max(intensity_2d)
    if peak <= 0:
        return 0.0

    ny, nx = intensity_2d.shape

    if axis == "x":
        margin = max(1, int(nx * 0.1))
        edge_left = intensity_2d[:, :margin]
        edge_right = intensity_2d[:, -margin:]
        edge_max = max(np.max(edge_left), np.max(edge_right))
    else:
        margin = max(1, int(ny * 0.1))
        edge_top = intensity_2d[:margin, :]
        edge_bottom = intensity_2d[-margin:, :]
        edge_max = max(np.max(edge_top), np.max(edge_bottom))

    return float(edge_max / peak)


def compute_total_flux(intensity_2d: np.ndarray, mesh_info: dict) -> float:
    """Compute total flux by 2D integration."""
    dx = (mesh_info["x_fin"] - mesh_info["x_start"]) / max(mesh_info["nx"] - 1, 1)
    dy = (mesh_info["y_fin"] - mesh_info["y_start"]) / max(mesh_info["ny"] - 1, 1)
    return float(np.sum(intensity_2d) * dx * dy)


def compute_centroid(intensity_2d: np.ndarray, mesh_info: dict) -> tuple[float, float]:
    """Compute intensity-weighted centroid position."""
    total = np.sum(intensity_2d)
    if total <= 0:
        return 0.0, 0.0

    coords_x = np.linspace(mesh_info["x_start"], mesh_info["x_fin"], mesh_info["nx"])
    coords_y = np.linspace(mesh_info["y_start"], mesh_info["y_fin"], mesh_info["ny"])

    proj_x = np.sum(intensity_2d, axis=0)
    proj_y = np.sum(intensity_2d, axis=1)

    cx = float(np.sum(proj_x * coords_x) / np.sum(proj_x)) if np.sum(proj_x) > 0 else 0.0
    cy = float(np.sum(proj_y * coords_y) / np.sum(proj_y)) if np.sum(proj_y) > 0 else 0.0

    return cx, cy


def compute_rms_size(intensity_2d: np.ndarray, mesh_info: dict, axis: str) -> float:
    """Compute RMS beam size along the specified axis."""
    if axis == "x":
        coords = np.linspace(mesh_info["x_start"], mesh_info["x_fin"], mesh_info["nx"])
        proj = np.sum(intensity_2d, axis=0)
    else:
        coords = np.linspace(mesh_info["y_start"], mesh_info["y_fin"], mesh_info["ny"])
        proj = np.sum(intensity_2d, axis=1)

    total = np.sum(proj)
    if total <= 0:
        return 0.0

    mean = np.sum(proj * coords) / total
    variance = np.sum(proj * (coords - mean) ** 2) / total
    return float(np.sqrt(max(variance, 0.0)))
