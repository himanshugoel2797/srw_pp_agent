"""Translate simplified JSON element definitions to SRW optical element objects.

This is the central element-building module. Used by beamline/builder.py,
beamline/manager.py, and srw_interface/idealization.py.
"""

from __future__ import annotations

from typing import Any

import math

try:
    from srwlib import (
        SRWLOptA, SRWLOptC, SRWLOptCryst, SRWLOptD, SRWLOptL,
        SRWLOptMirEl, SRWLOptMirPl, SRWLOptMirTor,
        srwl_opt_setup_CRL, srwl_opt_setup_surf_height_1d,
        srwl_uti_read_data_cols,
    )
except ImportError:
    try:
        from srwpy.srwlib import (
            SRWLOptA, SRWLOptC, SRWLOptCryst, SRWLOptD, SRWLOptL,
            SRWLOptMirEl, SRWLOptMirPl, SRWLOptMirTor,
            srwl_opt_setup_CRL, srwl_opt_setup_surf_height_1d,
            srwl_uti_read_data_cols,
        )
    except ImportError:
        SRWLOptA = None
        SRWLOptC = None
        SRWLOptCryst = None
        SRWLOptD = None
        SRWLOptL = None
        SRWLOptMirEl = None
        SRWLOptMirPl = None
        SRWLOptMirTor = None
        srwl_opt_setup_CRL = None
        srwl_opt_setup_surf_height_1d = None
        srwl_uti_read_data_cols = None


def _mirror_orientation_vectors(grazing_angle_rad: float, orientation: str = "vertical"):
    """Compute SRW normal and tangential vectors from grazing angle and orientation.

    Args:
        grazing_angle_rad: Grazing angle in radians.
        orientation: "vertical" (deflects vertically) or "horizontal".

    Returns:
        (nvx, nvy, nvz, tvx, tvy) orientation vector components.
    """
    cos_a = math.cos(grazing_angle_rad)
    sin_a = math.sin(grazing_angle_rad)
    if orientation == "vertical":
        # Mirror deflects beam vertically
        return 0, cos_a, -sin_a, 0, sin_a, cos_a
    else:
        # Mirror deflects beam horizontally
        return cos_a, 0, -sin_a, sin_a, 0, cos_a


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
        "crystal": _build_crystal,
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
        size_x_m: horizontal full size (diameter for circular)
        size_y_m: vertical full size (ignored for circular)

    SRW's SRWLOptA _Dx/_Dy are full transverse dimensions, not half-sizes.
    """
    if size_y_m is None:
        size_y_m = size_x_m

    if shape == "circular":
        return SRWLOptA("c", "a", size_x_m)
    else:
        return SRWLOptA("r", "a", size_x_m, size_y_m)


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
    - "flat": Flat mirror (no focusing). Default when no curved parameters given.
    - "height_profile": Flat mirror with surface height errors from a data file.
      Uses srwl_opt_setup_surf_height_1d for proper phase-error modeling.
    - "elliptical": Elliptical mirror (focuses in the tangential plane only).
      Defined by object_distance_m (p) and image_distance_m (q).
      Default when p and q are given without an explicit subtype.
    - "cylindrical": Cylindrical mirror (focuses in one plane only).
      Defined by radius_of_curvature_m (R).
    """
    grazing_angle = element_def.get("grazing_angle_mrad", 3.0) * 1e-3  # mrad -> rad
    tangential_size = element_def.get("tangential_size_m", 0.4)
    sagittal_size = element_def.get("sagittal_size_m", 0.02)
    orientation = element_def.get("orientation", "vertical")
    subtype = element_def.get("subtype", "").lower()

    # Infer subtype from available parameters when not explicitly set
    if not subtype:
        if "object_distance_m" in element_def or "image_distance_m" in element_def:
            subtype = "elliptical"
        elif "radius_of_curvature_m" in element_def:
            subtype = "cylindrical"
        elif "height_profile_file" in element_def:
            subtype = "height_profile"
        else:
            subtype = "flat"

    # Height-profile mirror: use srwl_opt_setup_surf_height_1d
    if subtype == "height_profile":
        return _build_height_profile_mirror(element_def)

    # Compute orientation vectors from grazing angle
    nvx, nvy, nvz, tvx, tvy, _tvz = _mirror_orientation_vectors(grazing_angle, orientation)

    if subtype == "elliptical":
        p = element_def.get("object_distance_m", 1e23)
        q = element_def.get("image_distance_m", 1e23)
        mirror = SRWLOptMirEl(
            _p=p,
            _q=q,
            _ang_graz=grazing_angle,
            _size_tang=tangential_size,
            _size_sag=sagittal_size,
            _nvx=nvx, _nvy=nvy, _nvz=nvz,
            _tvx=tvx, _tvy=tvy,
        )
    elif subtype == "cylindrical":
        radius = element_def.get("radius_of_curvature_m", 1e23)
        focusing_plane = element_def.get("focusing_plane", "tangential")
        if focusing_plane == "tangential":
            rt, rs = radius, 1e23
        else:
            rt, rs = 1e23, radius
        mirror = SRWLOptMirTor(
            _rt=rt,
            _rs=rs,
            _size_tang=tangential_size,
            _size_sag=sagittal_size,
            _nvx=nvx, _nvy=nvy, _nvz=nvz,
            _tvx=tvx, _tvy=tvy,
        )
    else:
        # Flat mirror
        mirror = SRWLOptMirPl(
            _size_tang=tangential_size,
            _size_sag=sagittal_size,
            _nvx=nvx, _nvy=nvy, _nvz=nvz,
            _tvx=tvx, _tvy=tvy,
        )

    return mirror


def _build_height_profile_mirror(element_def: dict) -> Any:
    """Build a mirror from a 1D surface height profile file.

    Uses srwl_opt_setup_surf_height_1d which creates a transmission element
    encoding the phase errors from the measured/simulated surface profile.
    Falls back to a flat mirror if the height profile file is not found or
    the SRW function is unavailable.
    """
    import os

    hpf = element_def.get("height_profile_file", "")
    grazing_angle = element_def.get("grazing_angle_rad",
                                     element_def.get("grazing_angle_mrad", 3.0) * 1e-3)
    dim = element_def.get("orientation", "x")
    amp_coef = element_def.get("height_amplification", 1.0)
    size_x = element_def.get("tangential_size_m", 0.4)
    size_y = element_def.get("sagittal_size_m", 0.02)

    if (srwl_opt_setup_surf_height_1d is not None
            and srwl_uti_read_data_cols is not None
            and os.path.isfile(hpf)):
        height_data = srwl_uti_read_data_cols(hpf, "\t", 0, 1)
        return srwl_opt_setup_surf_height_1d(
            height_data,
            _dim=dim,
            _ang=grazing_angle,
            _amp_coef=amp_coef,
            _size_x=size_x,
            _size_y=size_y,
        )

    # Fallback: flat mirror (no height errors)
    nvx, nvy, nvz, tvx, tvy, _tvz = _mirror_orientation_vectors(
        grazing_angle, "vertical" if dim == "y" else "horizontal")
    return SRWLOptMirPl(
        _size_tang=size_x,
        _size_sag=size_y,
        _nvx=nvx, _nvy=nvy, _nvz=nvz,
        _tvx=tvx, _tvy=tvy,
    )


def _build_crystal(element_def: dict) -> Any:
    """Build an SRW crystal element from simplified definition.

    Crystal orientation vectors can be specified explicitly (nvx, nvy, nvz, tvx, tvy)
    or computed from grazing_angle_rad and orientation. Explicit vectors are preferred
    when loading from SRW-native scripts since crystal geometry is more complex than
    simple mirror reflections (e.g. DCM pairs have opposite normal vector signs).
    """
    # Orientation vectors: prefer explicit, fall back to computed
    if "nvx" in element_def:
        nvx = element_def["nvx"]
        nvy = element_def.get("nvy", 0)
        nvz = element_def["nvz"]
        tvx = element_def["tvx"]
        tvy = element_def.get("tvy", 0)
    else:
        grazing_angle = element_def.get("grazing_angle_rad", 0.2)
        orientation = element_def.get("orientation", "horizontal")
        nvx, nvy, nvz, tvx, tvy, _tvz = _mirror_orientation_vectors(grazing_angle, orientation)

    crystal = SRWLOptCryst(
        _d_sp=element_def.get("d_spacing_A", 3.1356),
        _psi0r=element_def.get("psi0r", 0),
        _psi0i=element_def.get("psi0i", 0),
        _psi_hr=element_def.get("psiHr", 0),
        _psi_hi=element_def.get("psiHi", 0),
        _psi_hbr=element_def.get("psiHBr", 0),
        _psi_hbi=element_def.get("psiHBi", 0),
        _tc=element_def.get("thickness_m", 0.01),
        _ang_as=element_def.get("asymmetry_angle_rad", 0.0),
        _nvx=nvx, _nvy=nvy, _nvz=nvz,
        _tvx=tvx, _tvy=tvy,
        _uc=element_def.get("use_case", 1),
        _e_avg=element_def.get("energy_eV", 10000),
        _ang_roll=element_def.get("diffraction_angle_rad", 0),
    )
    return crystal


def _build_crl(element_def: dict) -> Any:
    """Build a compound refractive lens element.

    Uses srwl_opt_setup_CRL when full CRL parameters are available (tip_radius_m,
    delta, etc.) to get proper aperture clipping, absorption profile, and phase.
    Falls back to thin-lens approximation when only focal lengths are given.
    """
    # Prefer native SRW CRL construction when full parameters are available
    if (srwl_opt_setup_CRL is not None
            and "tip_radius_m" in element_def
            and "delta" in element_def):
        foc_plane = element_def.get("foc_plane", 3)
        return srwl_opt_setup_CRL(
            _foc_plane=foc_plane,
            _delta=element_def["delta"],
            _atten_len=element_def.get("attenuation_length_m", 1.0),
            _shape=element_def.get("shape", 1),
            _apert_h=element_def.get("aperture_h_m", 0.001),
            _apert_v=element_def.get("aperture_v_m", 0.001),
            _r_min=element_def["tip_radius_m"],
            _n=element_def.get("n_lenses", 1),
            _wall_thick=element_def.get("wall_thickness_m", 0.0),
            _xc=element_def.get("offset_x_m", 0.0),
            _yc=element_def.get("offset_y_m", 0.0),
        )

    # Fallback: thin-lens approximation
    fx = element_def.get("fx")
    fy = element_def.get("fy")

    if fx is not None and fy is not None:
        return create_lens(fx, fy)

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
            if "object_distance_m" in element_def or "image_distance_m" in element_def:
                subtype = "elliptical"
            elif "radius_of_curvature_m" in element_def:
                subtype = "cylindrical"
            else:
                subtype = "flat"
        key_params["subtype"] = subtype
        key_params["grazing_angle_mrad"] = element_def.get("grazing_angle_mrad")
        key_params["tangential_size_m"] = element_def.get("tangential_size_m")
        key_params["sagittal_size_m"] = element_def.get("sagittal_size_m")
        if subtype == "elliptical":
            key_params["object_distance_m"] = element_def.get("object_distance_m")
            key_params["image_distance_m"] = element_def.get("image_distance_m")
        elif subtype == "cylindrical":
            key_params["radius_of_curvature_m"] = element_def.get("radius_of_curvature_m")
            key_params["focusing_plane"] = element_def.get("focusing_plane", "tangential")
    elif elem_type == "aperture":
        key_params["shape"] = element_def.get("shape")
        key_params["size_x_m"] = element_def.get("size_x_m")
        key_params["size_y_m"] = element_def.get("size_y_m")
    elif elem_type == "crystal":
        key_params["d_spacing_A"] = element_def.get("d_spacing_A")
        key_params["energy_eV"] = element_def.get("energy_eV")
        key_params["thickness_m"] = element_def.get("thickness_m")
        key_params["grazing_angle_rad"] = element_def.get("grazing_angle_rad")
        key_params["diffraction_angle_rad"] = element_def.get("diffraction_angle_rad")
    elif elem_type == "crl":
        key_params["n_lenses"] = element_def.get("n_lenses")
        key_params["focal_length_m"] = element_def.get("focal_length_m")
        key_params["fx"] = element_def.get("fx")
        key_params["fy"] = element_def.get("fy")
        key_params["aperture_h_m"] = element_def.get("aperture_h_m")
        key_params["aperture_v_m"] = element_def.get("aperture_v_m")
    elif elem_type == "lens":
        key_params["fx"] = element_def.get("fx")
        key_params["fy"] = element_def.get("fy")
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
