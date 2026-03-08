"""Translate simplified JSON element definitions to SRW optical element objects.

This is the central element-building module. Used by beamline/builder.py,
beamline/manager.py, and srw_interface/idealization.py.
"""

from __future__ import annotations

from typing import Any

try:
    from srwlib import (
        SRWLOptA, SRWLOptC, SRWLOptD, SRWLOptL,
        SRWLOptMirEl, SRWLOptMirCyl, SRWLOptMirPl,
    )
except ImportError:
    SRWLOptA = None
    SRWLOptD = None
    SRWLOptL = None
    SRWLOptC = None
    SRWLOptMirEl = None
    SRWLOptMirCyl = None
    SRWLOptMirPl = None


def simplified_to_srw_element(element_def: dict) -> Any:
    """Dispatch: convert a simplified JSON element dict to an SRW optical element.

    Supported types: drift, lens, aperture, mirror, crl, zone_plate
    """
    elem_type = element_def.get("type", "").lower()

    dispatch = {
        "drift": _build_drift,
        "lens": _build_lens,
        "aperture": _build_aperture,
        "mirror": _build_mirror,
        "crl": _build_crl,
        "zone_plate": _build_zone_plate,
    }

    builder = dispatch.get(elem_type)
    if builder is None:
        raise ValueError(f"Unknown element type: {elem_type}")

    return builder(element_def)


def create_drift(length_m: float) -> Any:
    """Create an SRW drift space element."""
    return SRWLOptD(length_m)


def create_lens(fx: float, fy: float | None = None) -> Any:
    """Create an SRW thin lens element."""
    if fy is None:
        fy = fx
    return SRWLOptL(fx, fy)


def create_aperture(shape: str, size_x_m: float, size_y_m: float | None = None) -> Any:
    """Create an SRW aperture element.

    Args:
        shape: "circular" or "rectangular"
        size_x_m: horizontal size (diameter for circular)
        size_y_m: vertical size (ignored for circular)
    """
    if size_y_m is None:
        size_y_m = size_x_m

    if shape == "circular":
        return SRWLOptA("c", "a", size_x_m / 2)
    else:
        return SRWLOptA("r", "a", size_x_m / 2, size_y_m / 2)


def _build_drift(element_def: dict) -> Any:
    return create_drift(element_def["length_m"])


def _build_lens(element_def: dict) -> Any:
    fx = element_def.get("focal_length_m") or element_def.get("fx", 1e23)
    fy = element_def.get("fy", fx)
    return create_lens(fx, fy)


def _build_aperture(element_def: dict) -> Any:
    shape = element_def.get("shape", "rectangular")
    size_x = element_def.get("size_x_m", element_def.get("diameter_m", 0.001))
    size_y = element_def.get("size_y_m", size_x)
    return create_aperture(shape, size_x, size_y)


def _build_mirror(element_def: dict) -> Any:
    """Build an SRW mirror element from simplified definition.

    Mirror subtypes (determined by "subtype" key):
    - "flat": Flat mirror (no focusing). Default when no focal_length_m given.
    - "elliptical": Elliptical mirror (focuses in both tangential and sagittal planes).
      Specified via object_distance_m (p) and image_distance_m (q).
      Default when focal_length_m is given without an explicit subtype.
    - "cylindrical": Cylindrical mirror (focuses in one plane only).
      Requires a "focusing_plane" key ("tangential" or "sagittal").
      Uses a radius of curvature R = 2*p*q/(p+q)/sin(theta).
    """
    grazing_angle = element_def.get("grazing_angle_mrad", 3.0) * 1e-3  # mrad -> rad
    tangential_size = element_def.get("tangential_size_m", 0.4)
    sagittal_size = element_def.get("sagittal_size_m", 0.02)
    focal_length = element_def.get("focal_length_m")
    subtype = element_def.get("subtype", "").lower()

    # Infer subtype from available parameters when not explicitly set
    if not subtype:
        if focal_length is not None:
            subtype = "elliptical"
        else:
            subtype = "flat"

    if subtype == "elliptical":
        p = element_def.get("object_distance_m", 1e23)
        q = element_def.get("image_distance_m", focal_length or 1e23)
        mirror = SRWLOptMirEl(
            _p=p,
            _q=q,
            _ang_graz=grazing_angle,
            _size_tang=tangential_size,
            _size_sag=sagittal_size,
        )
    elif subtype == "cylindrical":
        p = element_def.get("object_distance_m", 1e23)
        q = element_def.get("image_distance_m", focal_length or 1e23)
        mirror = SRWLOptMirCyl(
            _size_tang=tangential_size,
            _size_sag=sagittal_size,
            _p=p,
            _q=q,
            _ang_graz=grazing_angle,
        )
    else:
        # Flat mirror
        mirror = SRWLOptMirPl(
            _size_tang=tangential_size,
            _size_sag=sagittal_size,
            _ang_graz=grazing_angle,
        )

    return mirror


def _build_crl(element_def: dict) -> Any:
    """Build a compound refractive lens element."""
    # CRL is implemented as a thin lens with effective focal length
    n_lenses = element_def.get("n_lenses", 1)
    single_f = element_def.get("single_lens_focal_length_m")
    effective_f = element_def.get("focal_length_m")

    if effective_f is None and single_f is not None:
        effective_f = single_f / n_lenses
    elif effective_f is None:
        effective_f = 1.0  # fallback

    return create_lens(effective_f, effective_f)


def _build_zone_plate(element_def: dict) -> Any:
    """Build a zone plate as a thin lens + aperture pair.

    Returns a thin lens (SRW doesn't have a native zone plate with full detail
    for our purposes, so we approximate with thin lens at the specified focal length).
    """
    focal_length = element_def.get("focal_length_m", 0.1)
    return create_lens(focal_length, focal_length)


def get_element_summary(element_def: dict) -> dict:
    """Extract a human-readable summary of an element for output."""
    elem_type = element_def.get("type", "unknown")
    label = element_def.get("label", "unlabeled")

    key_params = {}
    if elem_type == "drift":
        key_params["length_m"] = element_def.get("length_m")
    elif elem_type == "lens":
        key_params["focal_length_m"] = element_def.get("focal_length_m")
    elif elem_type == "mirror":
        subtype = element_def.get("subtype", "")
        if not subtype:
            subtype = "elliptical" if element_def.get("focal_length_m") is not None else "flat"
        key_params["subtype"] = subtype
        key_params["grazing_angle_mrad"] = element_def.get("grazing_angle_mrad")
        key_params["focal_length_m"] = element_def.get("focal_length_m")
        key_params["tangential_size_m"] = element_def.get("tangential_size_m")
        key_params["sagittal_size_m"] = element_def.get("sagittal_size_m")
        if subtype == "cylindrical":
            key_params["focusing_plane"] = element_def.get("focusing_plane", "tangential")
    elif elem_type == "aperture":
        key_params["shape"] = element_def.get("shape")
        key_params["size_x_m"] = element_def.get("size_x_m")
        key_params["size_y_m"] = element_def.get("size_y_m")
    elif elem_type == "crl":
        key_params["n_lenses"] = element_def.get("n_lenses")
        key_params["focal_length_m"] = element_def.get("focal_length_m")
    elif elem_type == "zone_plate":
        key_params["focal_length_m"] = element_def.get("focal_length_m")
        key_params["diameter_m"] = element_def.get("diameter_m")
        key_params["outermost_zone_width_m"] = element_def.get("outermost_zone_width_m")

    # Filter out None values
    key_params = {k: v for k, v in key_params.items() if v is not None}

    # Smallest feature size
    smallest_feature = None
    if elem_type == "zone_plate":
        smallest_feature = element_def.get("outermost_zone_width_m")
    elif elem_type == "grating":
        smallest_feature = element_def.get("grating_pitch_m")

    return {
        "type": elem_type,
        "label": label,
        "key_params": key_params,
        "smallest_feature_size_m": smallest_feature,
    }
