"""Session state management for the tuning server."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SimRun:
    """Record of a single simulation run."""

    run_id: str
    timestamp: datetime
    propagation_params: dict[str, dict]
    up_to_element: str | None
    mesh_params: dict | None
    results: dict
    wall_time_s: float
    beamline_state_hash: str = ""


@dataclass
class TuningSession:
    """Persists across tool calls within a conversation.

    Key distinction:
    - canonical_definition: accumulates permanent edits (edit_beamline), returned to user
    - working_beamline: canonical + probes + idealizations + truncations, used for simulation
    """

    original_definition: dict = field(default_factory=dict)
    canonical_definition: dict = field(default_factory=dict)
    working_beamline: dict = field(default_factory=dict)
    propagation_params: dict[str, dict] = field(default_factory=dict)
    source_wavefront: Any = None  # SRWLWfr when loaded
    simulation_history: list[SimRun] = field(default_factory=list)
    analytical_estimates: dict = field(default_factory=dict)
    edit_log: list[str] = field(default_factory=list)
    active_probes: dict[str, dict] = field(default_factory=dict)
    idealized_elements: dict[str, dict] = field(default_factory=dict)
    truncated_drifts: dict[str, float] = field(default_factory=dict)
    convergence_tests: list[dict] = field(default_factory=list)
    idealization_tests: list[dict] = field(default_factory=list)
    _loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def record_run(self, results: dict, params: dict[str, dict],
                   up_to_element: str | None, mesh_params: dict | None,
                   wall_time_s: float) -> str:
        """Record a simulation run and return its run_id."""
        run_id = f"run_{len(self.simulation_history):03d}_{uuid.uuid4().hex[:6]}"
        run = SimRun(
            run_id=run_id,
            timestamp=datetime.now(),
            propagation_params={k: dict(v) for k, v in params.items()},
            up_to_element=up_to_element,
            mesh_params=mesh_params,
            results=results,
            wall_time_s=wall_time_s,
        )
        self.simulation_history.append(run)
        return run_id

    def get_latest_run(self) -> SimRun | None:
        return self.simulation_history[-1] if self.simulation_history else None

    def get_run_by_id(self, run_id: str) -> SimRun | None:
        for run in self.simulation_history:
            if run.run_id == run_id:
                return run
        return None

    def get_element_labels(self) -> list[str]:
        """Return ordered list of element labels from the working beamline."""
        elements = self.working_beamline.get("elements", [])
        return [e["label"] for e in elements]
