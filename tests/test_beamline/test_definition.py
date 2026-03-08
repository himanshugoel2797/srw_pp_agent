"""Tests for beamline definition parsing and validation."""

import pytest

from srw_pp_agent.beamline.definition import (
    parse_beamline_definition,
    validate_labels_unique,
    assign_cumulative_distances,
    compute_smallest_feature_sizes,
    find_element_index,
    get_total_length,
)
from tests.mocks.srw_mock import SAMPLE_BEAMLINE


class TestParseBeamlineDefinition:
    def test_parse_dict(self):
        result = parse_beamline_definition(SAMPLE_BEAMLINE)
        assert "source" in result
        assert "elements" in result
        assert len(result["elements"]) == 5
        assert result["elements"][0]["label"] == "D1"

    def test_parse_assigns_cumulative_distances(self):
        result = parse_beamline_definition(SAMPLE_BEAMLINE)
        # D1=10m, M1@10m, D2=5m@15m, L1@15m, D3=3m@18m
        assert result["elements"][0]["cumulative_distance_m"] == 10.0
        assert result["elements"][1]["cumulative_distance_m"] == 10.0  # mirror at 10m
        assert result["elements"][2]["cumulative_distance_m"] == 15.0  # D2 ends at 15m
        assert result["elements"][4]["cumulative_distance_m"] == 18.0  # D3 ends at 18m

    def test_parse_auto_labels(self):
        beamline = {
            "source": {"type": "gaussian", "energy_eV": 12000},
            "elements": [
                {"type": "drift", "length_m": 5.0},
                {"type": "lens", "focal_length_m": 2.0},
            ],
        }
        result = parse_beamline_definition(beamline)
        assert result["elements"][0]["label"] == "drift_0"
        assert result["elements"][1]["label"] == "lens_1"

    def test_parse_invalid_input(self):
        with pytest.raises(ValueError):
            parse_beamline_definition("not_a_file_and_not_json")

    def test_parse_default_source(self):
        result = parse_beamline_definition({"elements": []})
        assert result["source"]["type"] == "gaussian"


class TestValidateLabelsUnique:
    def test_unique_labels(self):
        elements = [{"label": "A"}, {"label": "B"}, {"label": "C"}]
        validate_labels_unique(elements)  # should not raise

    def test_duplicate_labels(self):
        elements = [{"label": "A"}, {"label": "B"}, {"label": "A"}]
        with pytest.raises(ValueError, match="Duplicate element label: A"):
            validate_labels_unique(elements)


class TestAssignCumulativeDistances:
    def test_drifts_only(self):
        elements = [
            {"type": "drift", "length_m": 5.0},
            {"type": "drift", "length_m": 3.0},
        ]
        result = assign_cumulative_distances(elements)
        assert result[0]["cumulative_distance_m"] == 5.0
        assert result[1]["cumulative_distance_m"] == 8.0

    def test_mixed_elements(self):
        elements = [
            {"type": "drift", "length_m": 10.0},
            {"type": "mirror"},
            {"type": "drift", "length_m": 5.0},
        ]
        result = assign_cumulative_distances(elements)
        assert result[0]["cumulative_distance_m"] == 10.0
        assert result[1]["cumulative_distance_m"] == 10.0
        assert result[2]["cumulative_distance_m"] == 15.0


class TestComputeSmallestFeatureSizes:
    def test_zone_plate(self):
        elements = [{"type": "zone_plate", "outermost_zone_width_m": 30e-9}]
        result = compute_smallest_feature_sizes(elements)
        assert result[0]["smallest_feature_size_m"] == 30e-9

    def test_drift_has_no_feature(self):
        elements = [{"type": "drift", "length_m": 5.0}]
        result = compute_smallest_feature_sizes(elements)
        assert result[0]["smallest_feature_size_m"] is None


class TestFindElementIndex:
    def test_find_existing(self):
        elements = [{"label": "A"}, {"label": "B"}, {"label": "C"}]
        assert find_element_index(elements, "B") == 1

    def test_find_nonexistent(self):
        elements = [{"label": "A"}]
        with pytest.raises(ValueError, match="Element not found"):
            find_element_index(elements, "Z")


class TestGetTotalLength:
    def test_total_length(self):
        elements = [
            {"type": "drift", "length_m": 10.0},
            {"type": "mirror"},
            {"type": "drift", "length_m": 5.0},
        ]
        assert get_total_length(elements) == 15.0
