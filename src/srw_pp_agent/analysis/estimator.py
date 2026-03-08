"""Gaussian beam / ABCD matrix analytical estimator.

Pure math using numpy — no SRW dependency. Walks the beamline element-by-element,
tracking beam waist size and location in both planes using ABCD matrices.
"""

from __future__ import annotations

import math

import numpy as np

from ..session import TuningSession


# Physical constants
HC_EV_M = 1.23984193e-6  # h*c in eV·m


def compute_analytical_estimates(session: TuningSession,
                                 at_element: str | None = None) -> dict:
    """Compute expected beam parameters using Gaussian beam propagation.

    Returns estimates per DESIGN.MD §3.4 for each element.
    """
    elements = session.working_beamline.get("elements", [])
    source = session.working_beamline.get("source", {})
    energy_eV = source.get("energy_eV", 12000)
    wavelength = HC_EV_M / energy_eV  # meters

    # Initialize beam parameters from source
    source_type = source.get("type", "gaussian")
    waist_x, waist_y = _get_source_waist(source, wavelength)

    # Gaussian beam complex parameter q = z + i*z_R
    # where z is distance from waist, z_R is Rayleigh range
    z_R_x = math.pi * waist_x**2 / wavelength
    z_R_y = math.pi * waist_y**2 / wavelength

    # Initial complex beam parameter (at source = waist, z=0)
    q_x = complex(0, z_R_x)  # q = i * z_R at waist
    q_y = complex(0, z_R_y)

    estimates = []
    cumulative_distance = 0.0
    source_size_x = 2.355 * waist_x  # FWHM = 2.355 * sigma
    source_size_y = 2.355 * waist_y

    for i, elem in enumerate(elements):
        label = elem.get("label", f"element_{i}")
        elem_type = elem.get("type", "").lower()

        if elem_type == "drift":
            length = elem.get("length_m", 0.0)
            # ABCD matrix for drift: [[1, L], [0, 1]]
            q_x = q_x + length
            q_y = q_y + length
            cumulative_distance += length

        elif elem_type in ("lens", "mirror", "crl", "zone_plate"):
            fx, fy = _get_focal_lengths_xy(elem)

            if fx is not None and fx != 0 and abs(fx) < 1e20:
                q_x = q_x / (1 - q_x / fx)
            if fy is not None and fy != 0 and abs(fy) < 1e20:
                q_y = q_y / (1 - q_y / fy)

        # Skip apertures — they don't change beam parameters in Gaussian model

        # Compute beam parameters at this element
        est = _compute_element_estimate(
            q_x, q_y, wavelength, elem, cumulative_distance,
            source_size_x, source_size_y, i, label,
        )

        if at_element is None or label == at_element:
            estimates.append(est)

    result = {"estimates": estimates}
    session.analytical_estimates = result
    return result


def _get_source_waist(source: dict, wavelength: float) -> tuple[float, float]:
    """Get source beam waist (sigma) from source definition."""
    src_type = source.get("type", "gaussian")

    if src_type == "gaussian":
        waist_x = source.get("waist_x_m", source.get("sigX", 50e-6))
        waist_y = source.get("waist_y_m", source.get("sigY", 10e-6))
        return waist_x, waist_y

    elif src_type == "undulator":
        # Approximate undulator source size
        # sigma_r = sqrt(lambda * L_u) / (4 * pi)  where L_u = N * lambda_u
        N = source.get("num_periods", 72)
        lambda_u = source.get("undulator_period_m", 0.021)
        L_u = N * lambda_u
        sigma_r = math.sqrt(wavelength * L_u) / (4 * math.pi)
        # Divergence: sigma_r' = sqrt(lambda / (2 * L_u))
        return sigma_r, sigma_r

    else:
        # Default reasonable size
        return 50e-6, 10e-6


def _get_focal_length(elem: dict) -> float | None:
    """Extract focal length from an element definition."""
    f = elem.get("focal_length_m")
    if f is not None:
        return f

    # For CRL: compute from n_lenses and single lens focal length
    if elem.get("type", "").lower() == "crl":
        single_f = elem.get("single_lens_focal_length_m")
        n = elem.get("n_lenses", 1)
        if single_f:
            return single_f / n

    return None


def _get_focal_lengths_xy(elem: dict) -> tuple[float | None, float | None]:
    """Extract per-axis focal lengths (fx, fy) from an element definition.

    For cylindrical mirrors, only one axis is focused. For all other
    focusing elements, fx == fy.
    """
    elem_type = elem.get("type", "").lower()

    if elem_type == "mirror":
        subtype = elem.get("subtype", "").lower()
        focal_length = elem.get("focal_length_m")
        if focal_length is None:
            return None, None

        if subtype == "cylindrical":
            focusing_plane = elem.get("focusing_plane", "tangential").lower()
            orientation = elem.get("orientation", "vertical").lower()
            # Vertical-deflecting mirror focusing tangentially → focuses y
            if (orientation == "vertical" and focusing_plane == "tangential") or \
               (orientation == "horizontal" and focusing_plane == "sagittal"):
                return None, focal_length
            else:
                return focal_length, None

        # Elliptical or unspecified curved mirror: focuses both planes
        return focal_length, focal_length

    elif elem_type == "lens":
        fx = elem.get("fx", elem.get("focal_length_m"))
        fy = elem.get("fy", fx)
        return fx, fy

    # CRL, zone_plate, etc. — symmetric
    f = _get_focal_length(elem)
    return f, f


def _compute_element_estimate(
    q_x: complex, q_y: complex, wavelength: float,
    elem: dict, cumulative_distance: float,
    source_size_x: float, source_size_y: float,
    index: int, label: str,
) -> dict:
    """Compute all analytical estimates at a single element."""
    # Extract beam parameters from complex beam parameter q
    # q = z + i*z_R, beam size w(z) = w_0 * sqrt(1 + (z/z_R)^2)
    # 1/q = 1/R - i*lambda/(pi*w^2) where R = radius of curvature

    inv_qx = 1.0 / q_x if q_x != 0 else 0
    inv_qy = 1.0 / q_y if q_y != 0 else 0

    # Beam size (sigma): w = sqrt(-lambda / (pi * Im(1/q)))
    w_x = _beam_size_from_q(q_x, wavelength)
    w_y = _beam_size_from_q(q_y, wavelength)

    # Rayleigh range
    z_R_x = math.pi * _waist_from_q(q_x, wavelength)**2 / wavelength
    z_R_y = math.pi * _waist_from_q(q_y, wavelength)**2 / wavelength

    # Distance from waist
    dist_from_waist_x = q_x.real
    dist_from_waist_y = q_y.real

    # Wavefront radius of curvature
    roc_x = 1.0 / inv_qx.real if inv_qx.real != 0 else float('inf')
    roc_y = 1.0 / inv_qy.real if inv_qy.real != 0 else float('inf')

    # FWHM = 2.355 * sigma
    fwhm_x = 2.355 * w_x
    fwhm_y = 2.355 * w_y

    # Element-specific calculations
    focal_length = _get_focal_length(elem)
    element_na_x = 0.0
    element_na_y = 0.0
    beam_na_x = 0.0
    beam_na_y = 0.0
    object_distance = 0.0
    image_distance = 0.0
    demag_x = 0.0
    demag_y = 0.0
    diff_limit_x = 0.0
    diff_limit_y = 0.0
    beam_to_aperture_x = 0.0
    beam_to_aperture_y = 0.0
    limiting_aperture = ""
    object_to_focal_ratio = None

    elem_type = elem.get("type", "").lower()

    if elem_type in ("mirror", "crl", "zone_plate", "lens") and focal_length:
        # Compute NA from element geometry
        aperture_x, aperture_y = _get_element_aperture(elem)
        if aperture_x > 0:
            element_na_x = (aperture_x / 2) / max(cumulative_distance, 0.001) * 1e3  # mrad
        if aperture_y > 0:
            element_na_y = (aperture_y / 2) / max(cumulative_distance, 0.001) * 1e3  # mrad

        # Beam NA from divergence
        beam_div_x = wavelength / (math.pi * w_x) if w_x > 0 else 0
        beam_div_y = wavelength / (math.pi * w_y) if w_y > 0 else 0
        beam_na_x = beam_div_x * 1e3  # mrad
        beam_na_y = beam_div_y * 1e3

        # Effective NA
        eff_na_x = min(element_na_x, beam_na_x) if element_na_x > 0 else beam_na_x
        eff_na_y = min(element_na_y, beam_na_y) if element_na_y > 0 else beam_na_y

        # Diffraction limit: 0.44 * lambda / NA (FWHM)
        if eff_na_x > 0:
            diff_limit_x = 0.44 * wavelength / (eff_na_x * 1e-3) * 1e6  # um
        if eff_na_y > 0:
            diff_limit_y = 0.44 * wavelength / (eff_na_y * 1e-3) * 1e6  # um

        # Demagnification
        object_distance = cumulative_distance
        if focal_length > 0:
            image_distance = 1.0 / (1.0 / focal_length - 1.0 / object_distance) if object_distance != focal_length else float('inf')
        else:
            image_distance = focal_length

        if object_distance > 0:
            mag = abs(image_distance / object_distance) if object_distance != 0 else 0
            demag_x = source_size_x * mag * 1e6  # um
            demag_y = source_size_y * mag * 1e6

        # Beam-to-aperture ratio
        beam_size_x = 2.355 * w_x  # FWHM
        beam_size_y = 2.355 * w_y
        if aperture_x > 0:
            beam_to_aperture_x = beam_size_x / aperture_x
        if aperture_y > 0:
            beam_to_aperture_y = beam_size_y / aperture_y

        limiting_aperture = label if element_na_x < beam_na_x or element_na_y < beam_na_y else ""
        if focal_length > 0:
            object_to_focal_ratio = object_distance / focal_length
    elif elem_type == "aperture":
        aperture_x = elem.get("size_x_m", elem.get("diameter_m", 0.001))
        aperture_y = elem.get("size_y_m", aperture_x)
        beam_size_x = 2.355 * w_x
        beam_size_y = 2.355 * w_y
        if aperture_x > 0:
            beam_to_aperture_x = beam_size_x / aperture_x
        if aperture_y > 0:
            beam_to_aperture_y = beam_size_y / aperture_y

    # Fresnel number
    fresnel_number = 0.0
    if cumulative_distance > 0 and w_x > 0:
        fresnel_number = w_x**2 / (wavelength * cumulative_distance)

    # Expected FWHM = max(demagnification, diffraction_limit) [simplified]
    expected_fwhm_x = max(demag_x, diff_limit_x) if (demag_x > 0 or diff_limit_x > 0) else fwhm_x * 1e6
    expected_fwhm_y = max(demag_y, diff_limit_y) if (demag_y > 0 or diff_limit_y > 0) else fwhm_y * 1e6

    return {
        "element_index": index,
        "element_label": label,
        "expected_fwhm_x_um": expected_fwhm_x,
        "expected_fwhm_y_um": expected_fwhm_y,
        "source_demagnification_x_um": demag_x,
        "source_demagnification_y_um": demag_y,
        "diffraction_limit_x_um": diff_limit_x,
        "diffraction_limit_y_um": diff_limit_y,
        "element_na_x_mrad": element_na_x,
        "element_na_y_mrad": element_na_y,
        "beam_na_x_mrad": beam_na_x,
        "beam_na_y_mrad": beam_na_y,
        "effective_na_x_mrad": min(element_na_x, beam_na_x) if element_na_x > 0 else beam_na_x,
        "effective_na_y_mrad": min(element_na_y, beam_na_y) if element_na_y > 0 else beam_na_y,
        "beam_to_aperture_ratio_x": beam_to_aperture_x,
        "beam_to_aperture_ratio_y": beam_to_aperture_y,
        "limiting_aperture_element": limiting_aperture,
        "rayleigh_range_x_m": z_R_x,
        "rayleigh_range_y_m": z_R_y,
        "distance_from_waist_x_m": dist_from_waist_x,
        "distance_from_waist_y_m": dist_from_waist_y,
        "wavefront_roc_x_m": roc_x,
        "wavefront_roc_y_m": roc_y,
        "object_distance_m": object_distance,
        "image_distance_m": image_distance,
        "focal_length_m": focal_length,
        "object_to_focal_ratio": object_to_focal_ratio,
        "fresnel_number": fresnel_number,
    }


def _beam_size_from_q(q: complex, wavelength: float) -> float:
    """Compute beam size (sigma) from complex beam parameter."""
    inv_q = 1.0 / q if q != 0 else 0
    imag_part = inv_q.imag
    if imag_part >= 0:
        return 0.0  # unphysical
    w_squared = -wavelength / (math.pi * imag_part)
    return math.sqrt(max(w_squared, 0))


def _waist_from_q(q: complex, wavelength: float) -> float:
    """Compute waist size (sigma_0) from complex beam parameter."""
    z_R = q.imag  # Rayleigh range
    if z_R <= 0:
        return 0.0
    w0_sq = z_R * wavelength / math.pi
    return math.sqrt(max(w0_sq, 0))


def _get_element_aperture(elem: dict) -> tuple[float, float]:
    """Get physical aperture dimensions for an element."""
    elem_type = elem.get("type", "").lower()

    if elem_type == "mirror":
        tang_size = elem.get("tangential_size_m", 0.4)
        sag_size = elem.get("sagittal_size_m", 0.02)
        grazing_mrad = elem.get("grazing_angle_mrad", 3.0)
        grazing_rad = grazing_mrad * 1e-3
        projected_tang = tang_size * math.sin(grazing_rad)

        orientation = elem.get("orientation", "vertical").lower()
        if orientation == "vertical":
            return sag_size, projected_tang
        else:
            return projected_tang, sag_size

    elif elem_type == "crl":
        aperture = elem.get("physical_aperture_m", elem.get("diameter_m", 0.001))
        return aperture, aperture

    elif elem_type == "zone_plate":
        diameter = elem.get("diameter_m", 0.0001)
        return diameter, diameter

    elif elem_type == "aperture":
        size_x = elem.get("size_x_m", elem.get("diameter_m", 0.001))
        size_y = elem.get("size_y_m", size_x)
        return size_x, size_y

    elif elem_type == "lens":
        # Ideal thin lens has no aperture constraint
        return 1.0, 1.0  # effectively infinite

    return 0.0, 0.0
