"""Structured error types for simulation failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SimulationError:
    """Structured error response for simulation failures.

    The agent uses these to reason about what went wrong:
    - timeout: resolution too high, reduce it
    - segfault: propagator mode inappropriate for beam state
    - nan_inf: propagator mode or parameters inappropriate
    - memory_limit: mesh too large
    - srw_error: SRW internal error
    """

    error: bool = True
    error_type: Literal["timeout", "segfault", "nan_inf", "memory_limit", "srw_error"] = "srw_error"
    message: str = ""
    element_label: str | None = None
    params_at_failure: dict | None = None
    wall_time_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "error": self.error,
            "error_type": self.error_type,
            "message": self.message,
            "element_label": self.element_label,
            "params_at_failure": self.params_at_failure,
            "wall_time_s": self.wall_time_s,
        }
