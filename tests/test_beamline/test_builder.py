"""Tests for working beamline builder."""

import pytest

from srw_pp_agent.beamline.builder import rebuild_working_beamline


class TestRebuildWorkingBeamline:
    def _make_canonical(self):
        return {
            "source": {"type": "gaussian", "energy_eV": 12000},
            "elements": [
                {"type": "drift", "length_m": 10.0, "label": "D1"},
                {"type": "mirror", "focal_length_m": 5.0, "label": "M1",
                 "grazing_angle_mrad": 3.0, "tangential_size_m": 0.4, "sagittal_size_m": 0.02},
                {"type": "drift", "length_m": 5.0, "label": "D2"},
            ],
        }

    def test_no_modifications(self):
        canonical = self._make_canonical()
        result = rebuild_working_beamline(canonical, {}, {}, {})
        assert len(result["elements"]) == 3
        assert result["elements"][0]["label"] == "D1"

    def test_with_probe(self):
        canonical = self._make_canonical()
        probes = {
            "p1": {
                "at_element": "M1",
                "aperture_params": {"shape": "circular", "size_x_m": 0.01, "size_y_m": 0.01},
            }
        }
        result = rebuild_working_beamline(canonical, probes, {}, {})
        # Probe should be inserted before M1
        labels = [e["label"] for e in result["elements"]]
        assert "probe_p1" in labels
        probe_idx = labels.index("probe_p1")
        m1_idx = labels.index("M1")
        assert probe_idx < m1_idx

    def test_with_truncation(self):
        canonical = self._make_canonical()
        # Mark D1 for truncation
        canonical["elements"][0]["_truncated_length_m"] = 3.0
        truncated = {"D1": 10.0}  # original length

        result = rebuild_working_beamline(canonical, {}, {}, truncated)
        d1 = result["elements"][0]
        assert d1["length_m"] == 3.0

    def test_with_idealization(self):
        canonical = self._make_canonical()
        # Mark M1 as idealized (store original for tracking)
        idealized = {"M1": canonical["elements"][1].copy()}

        result = rebuild_working_beamline(canonical, {}, idealized, {})
        # M1 should be replaced with aperture + lens
        labels = [e["label"] for e in result["elements"]]
        assert "M1" in labels  # the lens keeps the label
        # Should have an aperture added
        assert any("aperture" in e.get("label", "") for e in result["elements"])

    def test_cumulative_distances_recomputed(self):
        canonical = self._make_canonical()
        result = rebuild_working_beamline(canonical, {}, {}, {})
        # D1=10m, M1@10m, D2@15m
        assert result["elements"][0]["cumulative_distance_m"] == 10.0
        assert result["elements"][2]["cumulative_distance_m"] == 15.0

    def test_probe_and_truncation_combined(self):
        canonical = self._make_canonical()
        canonical["elements"][0]["_truncated_length_m"] = 5.0
        truncated = {"D1": 10.0}
        probes = {
            "p1": {
                "at_element": "D2",
                "aperture_params": {"shape": "rectangular", "size_x_m": 0.005, "size_y_m": 0.005},
            }
        }
        result = rebuild_working_beamline(canonical, probes, {}, truncated)
        labels = [e["label"] for e in result["elements"]]
        assert "probe_p1" in labels
        assert result["elements"][0]["length_m"] == 5.0
