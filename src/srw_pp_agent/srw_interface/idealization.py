"""Element idealization: replace realistic elements with thin-lens + aperture equivalents.

Deterministic mappings per element type, as specified in DESIGN.MD:
- Mirror (curved) → thin lens (same f) + rectangular aperture
- Zone plate → thin lens (same f) + circular aperture (ZP diameter)
- CRL stack → single thin lens (effective f) + circular aperture
- Compound/multilayer mirror → thin lens (same f) + appropriate aperture
"""

from __future__ import annotations

import math


def idealize_element(element_def: dict) -> list[dict]:
    """Replace a realistic element with its ideal equivalent(s).

    Returns a list of simplified element definitions (typically
    [aperture, thin_lens] or just [thin_lens]).
    """
    elem_type = element_def.get("type", "").lower()

    dispatch = {
        "mirror": _idealize_mirror,
        "crl": _idealize_crl,
        "zone_plate": _idealize_zone_plate,
    }

    handler = dispatch.get(elem_type)
    if handler is None:
        # Not a focusing element — return as-is
        return [element_def]

    return handler(element_def)


def compute_ideal_focal_length(element_def: dict) -> float | None:
    """Compute the focal length for idealization of a focusing element.

    For elliptical mirrors: f = p*q / (p+q)  (from conjugate relation).
    For cylindrical mirrors: f = R * sin(theta) / 2  (tangential focusing).
    """
    elem_type = element_def.get("type", "").lower()

    if elem_type == "mirror":
        return _compute_mirror_focal_length(element_def)
    elif elem_type == "crl":
        effective_f = element_def.get("focal_length_m")
        if effective_f is None:
            single_f = element_def.get("single_lens_focal_length_m")
            n = element_def.get("n_lenses", 1)
            if single_f is not None:
                effective_f = single_f / n
        return effective_f
    elif elem_type == "zone_plate":
        return element_def.get("focal_length_m")

    return None


def compute_ideal_aperture(element_def: dict) -> dict:
    """Compute the ideal aperture for a focusing element."""
    elem_type = element_def.get("type", "").lower()

    if elem_type == "mirror":
        return _mirror_aperture(element_def)
    elif elem_type == "crl":
        return _crl_aperture(element_def)
    elif elem_type == "zone_plate":
        return _zone_plate_aperture(element_def)

    return {"shape": "circular", "size_x_m": 1.0, "size_y_m": 1.0}


def get_idealization_info(element_def: dict) -> dict:
    """Get a summary of the idealization for reporting."""
    focal_length = compute_ideal_focal_length(element_def)
    aperture = compute_ideal_aperture(element_def)

    info = {
        "element_label": element_def.get("label", "unknown"),
        "original_type": element_def.get("type", "unknown"),
        "ideal_focal_length_m": focal_length,
        "ideal_aperture_type": aperture["shape"],
        "ideal_aperture_size_m": (
            [aperture["size_x_m"], aperture["size_y_m"]]
            if aperture["shape"] == "rectangular"
            else aperture["size_x_m"]
        ),
    }

    if element_def.get("type", "").lower() == "mirror":
        subtype = element_def.get("subtype", "")
        if not subtype:
            if "object_distance_m" in element_def or "image_distance_m" in element_def:
                subtype = "elliptical"
            elif "radius_of_curvature_m" in element_def:
                subtype = "cylindrical"
            else:
                subtype = "flat"
        info["mirror_subtype"] = subtype
        info["focusing_plane"] = element_def.get("focusing_plane", "tangential")

    return info


def _compute_mirror_focal_length(element_def: dict) -> float | None:
    """Compute effective focal length for a curved mirror.

    Elliptical: f = p*q / (p+q) from the conjugate relation.
    Cylindrical: f = R * sin(theta) / 2 for tangential focusing.
    Flat mirrors have no focal length.
    """
    subtype = element_def.get("subtype", "").lower()
    if not subtype:
        if "object_distance_m" in element_def or "image_distance_m" in element_def:
            subtype = "elliptical"
        elif "radius_of_curvature_m" in element_def:
            subtype = "cylindrical"
        else:
            return None  # flat

    if subtype == "elliptical":
        p = element_def.get("object_distance_m")
        q = element_def.get("image_distance_m")
        if p is not None and q is not None and (p + q) > 0:
            return p * q / (p + q)
        return element_def.get("focal_length_m")

    if subtype == "cylindrical":
        R = element_def.get("radius_of_curvature_m")
        if R is not None:
            theta = element_def.get("grazing_angle_mrad", 3.0) * 1e-3
            return R * math.sin(theta) / 2
        return element_def.get("focal_length_m")

    return None


def _idealize_mirror(element_def: dict) -> list[dict]:
    """Mirror → thin lens (1D) + rectangular aperture (projected at grazing angle).

    Both elliptical and cylindrical mirrors focus in one plane only.
    The thin lens has fx or fy set to 1e23 for the non-focusing plane.
    """
    focal_length = _compute_mirror_focal_length(element_def)
    if focal_length is None:
        # Flat mirror — replace with just an aperture
        aperture = _mirror_aperture(element_def)
        aperture["label"] = element_def.get("label", "ideal_mirror")
        aperture["type"] = "aperture"
        return [aperture]

    label = element_def.get("label", "ideal_mirror")

    aperture = _mirror_aperture(element_def)
    aperture["type"] = "aperture"
    aperture["label"] = f"{label}_aperture"

    # Both elliptical and cylindrical mirrors focus in one plane only.
    # Determine which optical axis (x or y) the mirror focuses based on
    # orientation and focusing plane.
    focusing_plane = element_def.get("focusing_plane", "tangential").lower()
    orientation = element_def.get("orientation", "vertical").lower()

    # A vertical-deflecting mirror focusing tangentially focuses the
    # vertical (y) direction; a horizontal-deflecting mirror focusing
    # tangentially focuses the horizontal (x) direction.
    if (orientation == "vertical" and focusing_plane == "tangential") or \
       (orientation == "horizontal" and focusing_plane == "sagittal"):
        fx, fy = 1e23, focal_length
    else:
        fx, fy = focal_length, 1e23

    lens = {
        "type": "lens",
        "fx": fx,
        "fy": fy,
        "label": label,
    }

    return [aperture, lens]


def _idealize_crl(element_def: dict) -> list[dict]:
    """CRL stack → single thin lens (effective f) + circular aperture."""
    label = element_def.get("label", "ideal_crl")

    effective_f = element_def.get("focal_length_m")
    if effective_f is None:
        single_f = element_def.get("single_lens_focal_length_m")
        n = element_def.get("n_lenses", 1)
        if single_f is not None:
            effective_f = single_f / n
        else:
            effective_f = 1.0

    aperture = _crl_aperture(element_def)
    aperture["type"] = "aperture"
    aperture["label"] = f"{label}_aperture"

    lens = {
        "type": "lens",
        "focal_length_m": effective_f,
        "label": label,
    }

    return [aperture, lens]


def _idealize_zone_plate(element_def: dict) -> list[dict]:
    """Zone plate → thin lens (same f) + circular aperture (ZP diameter)."""
    label = element_def.get("label", "ideal_zp")
    focal_length = element_def.get("focal_length_m", 0.1)

    aperture = _zone_plate_aperture(element_def)
    aperture["type"] = "aperture"
    aperture["label"] = f"{label}_aperture"

    lens = {
        "type": "lens",
        "focal_length_m": focal_length,
        "label": label,
    }

    return [aperture, lens]


def _mirror_aperture(element_def: dict) -> dict:
    """Compute mirror aperture: tangential × sagittal, projected at grazing angle."""
    tang_size = element_def.get("tangential_size_m", 0.4)
    sag_size = element_def.get("sagittal_size_m", 0.02)
    grazing_angle_mrad = element_def.get("grazing_angle_mrad", 3.0)
    grazing_angle_rad = grazing_angle_mrad * 1e-3

    # Project tangential size at grazing angle
    projected_tang = tang_size * math.sin(grazing_angle_rad)

    orientation = element_def.get("orientation", "vertical").lower()
    if orientation == "vertical":
        size_x = sag_size
        size_y = projected_tang
    else:
        size_x = projected_tang
        size_y = sag_size

    return {
        "shape": "rectangular",
        "size_x_m": size_x,
        "size_y_m": size_y,
    }


def _crl_aperture(element_def: dict) -> dict:
    """CRL aperture: circular with the physical aperture of the CRL."""
    aperture_m = element_def.get("physical_aperture_m", element_def.get("diameter_m", 0.001))
    return {
        "shape": "circular",
        "size_x_m": aperture_m,
        "size_y_m": aperture_m,
    }


def _zone_plate_aperture(element_def: dict) -> dict:
    """Zone plate aperture: circular with ZP diameter."""
    diameter = element_def.get("diameter_m", 0.0001)
    return {
        "shape": "circular",
        "size_x_m": diameter,
        "size_y_m": diameter,
    }
