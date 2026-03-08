"""Tests for propagation parameter management."""

import pytest

from srw_pp_agent.session import TuningSession
from srw_pp_agent.propagation_params import set_propagation_params, generate_warnings, get_default_params
from srw_pp_agent.srw_interface.propagation import expand_5_to_12_params


class TestSetPropagationParams:
    def test_set_params(self):
        session = TuningSession()
        session._loaded = True
        session.propagation_params = {"D1": get_default_params()}
        session.working_beamline = {"elements": [{"label": "D1", "type": "drift"}]}

        result = set_propagation_params(session, {
            "D1": {"mode": 1, "range_x": 2.0, "range_y": 2.0, "resolution_x": 1.5, "resolution_y": 1.5}
        })

        assert result["applied_params"]["D1"]["mode"] == 1
        assert result["applied_params"]["D1"]["range_x"] == 2.0
        assert session.propagation_params["D1"]["mode"] == 1

    def test_invalid_mode_warning(self):
        session = TuningSession()
        session._loaded = True
        session.propagation_params = {"D1": get_default_params()}
        session.working_beamline = {"elements": [{"label": "D1", "type": "drift"}]}

        result = set_propagation_params(session, {
            "D1": {"mode": 99}
        })

        assert any("invalid mode" in w for w in result["warnings"])
        assert session.propagation_params["D1"]["mode"] == 0  # falls back to 0

    def test_unknown_label_warning(self):
        session = TuningSession()
        session._loaded = True
        session.working_beamline = {"elements": []}
        session.propagation_params = {}

        result = set_propagation_params(session, {
            "UNKNOWN": {"mode": 0}
        })

        assert any("Unknown element label" in w for w in result["warnings"])


class TestGenerateWarnings:
    def test_high_resolution_warning(self):
        warnings = generate_warnings("D1", 0, 1.0, 1.0, 5.0, 1.0)
        assert any("resolution factor > 4" in w for w in warnings)

    def test_very_high_resolution_warning(self):
        warnings = generate_warnings("D1", 0, 1.0, 1.0, 15.0, 1.0)
        assert any("resolution factor > 10" in w for w in warnings)

    def test_mode_3_4_inversion_warning(self):
        warnings = generate_warnings("D1", 3, 2.0, 1.0, 1.0, 1.0)
        assert any("range controls point density" in w for w in warnings)

    def test_no_warnings_for_default(self):
        warnings = generate_warnings("D1", 0, 1.0, 1.0, 1.0, 1.0)
        assert warnings == []


class TestExpand5To12Params:
    def test_mode_0_defaults(self):
        result = expand_5_to_12_params(0, 1.0, 1.0, 1.0, 1.0)
        assert len(result) == 12
        assert result[3] == 0  # mode
        assert result[8] == 1.0  # range_x after
        assert result[9] == 1.0  # resolution_x after
        assert result[10] == 1.0  # range_y after
        assert result[11] == 1.0  # resolution_y after

    def test_mode_2_with_custom_params(self):
        result = expand_5_to_12_params(2, 3.0, 2.5, 1.5, 2.0)
        assert result[3] == 2
        assert result[8] == 3.0
        assert result[9] == 1.5
        assert result[10] == 2.5
        assert result[11] == 2.0

    def test_mode_3(self):
        result = expand_5_to_12_params(3, 2.0, 2.0, 1.5, 1.5)
        assert result[3] == 3

    def test_all_modes_produce_12_elements(self):
        for mode in range(5):
            result = expand_5_to_12_params(mode, 1.0, 1.0, 1.0, 1.0)
            assert len(result) == 12


class TestGetDefaultParams:
    def test_defaults(self):
        defaults = get_default_params()
        assert defaults["mode"] == 0
        assert defaults["range_x"] == 1.0
        assert defaults["resolution_x"] == 1.0
