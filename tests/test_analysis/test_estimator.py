"""Tests for the Gaussian beam / ABCD matrix analytical estimator.

Tests use known optics configurations where exact answers are computable.
"""

import math

import pytest

from srw_pp_agent.session import TuningSession
from srw_pp_agent.analysis.estimator import compute_analytical_estimates, HC_EV_M


def _make_session_with_beamline(beamline: dict) -> TuningSession:
    """Create a session with a parsed beamline (no SRW needed)."""
    from srw_pp_agent.beamline.definition import parse_beamline_definition

    session = TuningSession()
    definition = parse_beamline_definition(beamline)
    session.canonical_definition = definition
    session.working_beamline = definition
    session._loaded = True
    return session


class TestAnalyticalEstimator:
    def test_single_drift(self):
        """Gaussian beam through a drift should expand."""
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000, "waist_x_m": 50e-6, "waist_y_m": 50e-6},
            "elements": [
                {"type": "drift", "length_m": 10.0, "label": "D1"},
            ],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session)

        assert "estimates" in result
        assert len(result["estimates"]) == 1

        est = result["estimates"][0]
        assert est["element_label"] == "D1"
        assert est["rayleigh_range_x_m"] > 0
        assert est["distance_from_waist_x_m"] == 10.0

    def test_single_lens_focusing(self):
        """Gaussian beam through drift + lens: check focal properties."""
        f = 2.0  # 2m focal length
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000, "waist_x_m": 50e-6, "waist_y_m": 50e-6},
            "elements": [
                {"type": "drift", "length_m": 10.0, "label": "D1"},
                {"type": "lens", "focal_length_m": f, "label": "L1"},
                {"type": "drift", "length_m": 5.0, "label": "D2"},
            ],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session)

        assert len(result["estimates"]) == 3

        # The lens should have a focal_length_m entry
        lens_est = result["estimates"][1]
        assert lens_est["element_label"] == "L1"
        assert lens_est["focal_length_m"] == f

    def test_wavelength_from_energy(self):
        """Check wavelength computation."""
        energy = 12000  # 12 keV
        wavelength = HC_EV_M / energy
        expected_angstrom = 1.0332  # roughly 1.03 Å for 12 keV
        assert abs(wavelength * 1e10 - expected_angstrom) < 0.01

    def test_rayleigh_range(self):
        """Verify Rayleigh range computation for known parameters."""
        energy = 12000
        wavelength = HC_EV_M / energy
        waist = 50e-6  # 50 um

        z_R = math.pi * waist**2 / wavelength

        beamline = {
            "source": {"type": "gaussian", "energy_eV": energy, "waist_x_m": waist, "waist_y_m": waist},
            "elements": [{"type": "drift", "length_m": 1.0, "label": "D1"}],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session)

        est = result["estimates"][0]
        # Rayleigh range should match our calculation
        assert abs(est["rayleigh_range_x_m"] - z_R) / z_R < 0.01

    def test_at_element_filter(self):
        """Test filtering estimates to a specific element."""
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000, "waist_x_m": 50e-6, "waist_y_m": 50e-6},
            "elements": [
                {"type": "drift", "length_m": 10.0, "label": "D1"},
                {"type": "drift", "length_m": 5.0, "label": "D2"},
            ],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session, at_element="D2")

        assert len(result["estimates"]) == 1
        assert result["estimates"][0]["element_label"] == "D2"

    def test_estimates_cached_in_session(self):
        """Results should be cached in session.analytical_estimates."""
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000, "waist_x_m": 50e-6, "waist_y_m": 50e-6},
            "elements": [{"type": "drift", "length_m": 5.0, "label": "D1"}],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session)

        assert session.analytical_estimates == result

    def test_fresnel_number_positive(self):
        """Fresnel number should be positive for any real beamline."""
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000, "waist_x_m": 50e-6, "waist_y_m": 50e-6},
            "elements": [{"type": "drift", "length_m": 10.0, "label": "D1"}],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session)
        assert result["estimates"][0]["fresnel_number"] > 0

    def test_mirror_element_estimates(self):
        """Test estimates with a mirror element."""
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000, "waist_x_m": 50e-6, "waist_y_m": 50e-6},
            "elements": [
                {"type": "drift", "length_m": 20.0, "label": "D1"},
                {"type": "mirror", "focal_length_m": 5.0, "label": "M1",
                 "grazing_angle_mrad": 3.0, "tangential_size_m": 0.4, "sagittal_size_m": 0.02,
                 "orientation": "vertical"},
            ],
        }
        session = _make_session_with_beamline(beamline)
        result = compute_analytical_estimates(session)

        mirror_est = result["estimates"][1]
        assert mirror_est["element_label"] == "M1"
        assert mirror_est["focal_length_m"] == 5.0
        assert mirror_est["element_na_x_mrad"] > 0 or mirror_est["element_na_y_mrad"] > 0
        assert mirror_est["diffraction_limit_x_um"] > 0 or mirror_est["diffraction_limit_y_um"] > 0
