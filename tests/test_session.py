"""Tests for TuningSession state management."""

import pytest

from srw_pp_agent.session import TuningSession, SimRun


class TestTuningSession:
    def test_initial_state(self):
        session = TuningSession()
        assert not session.is_loaded
        assert session.simulation_history == []
        assert session.propagation_params == {}
        assert session.active_probes == {}
        assert session.idealized_elements == {}
        assert session.truncated_drifts == {}

    def test_record_run(self):
        session = TuningSession()
        session._loaded = True

        run_id = session.record_run(
            results={"final": {"fwhm_x_um": 10.0}},
            params={"D1": {"mode": 0, "range_x": 1.0, "range_y": 1.0, "resolution_x": 1.0, "resolution_y": 1.0}},
            up_to_element=None,
            mesh_params=None,
            wall_time_s=2.5,
        )

        assert run_id.startswith("run_000_")
        assert len(session.simulation_history) == 1
        assert session.simulation_history[0].wall_time_s == 2.5

    def test_get_latest_run(self):
        session = TuningSession()
        assert session.get_latest_run() is None

        session.record_run({"final": {}}, {}, None, None, 1.0)
        session.record_run({"final": {}}, {}, None, None, 2.0)

        latest = session.get_latest_run()
        assert latest is not None
        assert latest.wall_time_s == 2.0

    def test_get_run_by_id(self):
        session = TuningSession()
        run_id = session.record_run({"final": {}}, {}, None, None, 3.0)

        found = session.get_run_by_id(run_id)
        assert found is not None
        assert found.wall_time_s == 3.0

        assert session.get_run_by_id("nonexistent") is None

    def test_get_element_labels(self):
        session = TuningSession()
        session.working_beamline = {
            "elements": [
                {"label": "D1", "type": "drift"},
                {"label": "M1", "type": "mirror"},
            ]
        }

        labels = session.get_element_labels()
        assert labels == ["D1", "M1"]

    def test_get_element_labels_empty(self):
        session = TuningSession()
        assert session.get_element_labels() == []
