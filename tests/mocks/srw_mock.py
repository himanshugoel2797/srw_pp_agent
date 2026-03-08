"""Mock implementations of srw_interface functions for testing.

Returns plausible wavefront metrics without needing srwpy installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import numpy as np


@dataclass
class MockMesh:
    nx: int = 256
    ny: int = 256
    xStart: float = -0.0005
    xFin: float = 0.0005
    yStart: float = -0.0005
    yFin: float = 0.0005
    eStart: float = 12000.0
    eFin: float = 12000.0
    zStart: float = 0.0


@dataclass
class MockWavefront:
    """Mock SRWLWfr object."""
    mesh: MockMesh = field(default_factory=MockMesh)

    def allocate(self, ne: int, nx: int, ny: int):
        self.mesh.nx = nx
        self.mesh.ny = ny


def create_mock_wavefront(
    nx: int = 256, ny: int = 256,
    range_x_m: float = 0.001, range_y_m: float = 0.001,
    energy_eV: float = 12000.0,
) -> MockWavefront:
    """Create a mock wavefront with specified mesh parameters."""
    wfr = MockWavefront()
    wfr.mesh.nx = nx
    wfr.mesh.ny = ny
    wfr.mesh.xStart = -range_x_m / 2
    wfr.mesh.xFin = range_x_m / 2
    wfr.mesh.yStart = -range_y_m / 2
    wfr.mesh.yFin = range_y_m / 2
    wfr.mesh.eStart = energy_eV
    wfr.mesh.eFin = energy_eV
    return wfr


def create_gaussian_intensity_2d(
    nx: int = 256, ny: int = 256,
    sigma_x: float = 50e-6, sigma_y: float = 30e-6,
    range_x_m: float = 0.001, range_y_m: float = 0.001,
    peak: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """Create a 2D Gaussian intensity profile for testing metrics."""
    x = np.linspace(-range_x_m / 2, range_x_m / 2, nx)
    y = np.linspace(-range_y_m / 2, range_y_m / 2, ny)
    X, Y = np.meshgrid(x, y)

    intensity = peak * np.exp(-X**2 / (2 * sigma_x**2) - Y**2 / (2 * sigma_y**2))

    mesh_info = {
        "nx": nx, "ny": ny,
        "x_start": -range_x_m / 2, "x_fin": range_x_m / 2,
        "y_start": -range_y_m / 2, "y_fin": range_y_m / 2,
    }

    return intensity, mesh_info


SAMPLE_BEAMLINE = {
    "source": {
        "type": "gaussian",
        "energy_eV": 12000,
        "waist_x_m": 50e-6,
        "waist_y_m": 10e-6,
    },
    "elements": [
        {"type": "drift", "length_m": 10.0, "label": "D1"},
        {
            "type": "mirror",
            "orientation": "vertical",
            "grazing_angle_mrad": 3.0,
            "tangential_size_m": 0.4,
            "sagittal_size_m": 0.02,
            "focal_length_m": 5.0,
            "label": "M1",
        },
        {"type": "drift", "length_m": 5.0, "label": "D2"},
        {
            "type": "mirror",
            "subtype": "cylindrical",
            "orientation": "horizontal",
            "focusing_plane": "tangential",
            "grazing_angle_mrad": 3.0,
            "tangential_size_m": 0.3,
            "sagittal_size_m": 0.02,
            "focal_length_m": 3.0,
            "label": "M2_cyl",
        },
        {"type": "drift", "length_m": 2.0, "label": "D2b"},
        {
            "type": "lens",
            "focal_length_m": 2.0,
            "label": "L1",
        },
        {"type": "drift", "length_m": 3.0, "label": "D3"},
    ],
}
