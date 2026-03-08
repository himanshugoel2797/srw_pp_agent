"""Source wavefront creation: undulator, bending magnet, Gaussian."""

from __future__ import annotations

from typing import Any

try:
    from srwlib import (
        SRWLGsnBm,
        SRWLMagFldU,
        SRWLMagFldH,
        SRWLMagFldC,
        SRWLPartBeam,
        SRWLRadMesh,
        SRWLWfr,
        srwl as srwl_main,
    )
except ImportError:
    SRWLGsnBm = None
    SRWLMagFldU = None
    SRWLMagFldH = None
    SRWLMagFldC = None
    SRWLPartBeam = None
    SRWLRadMesh = None
    SRWLWfr = None
    srwl_main = None

# Default mesh parameters for source wavefront calculation
DEFAULT_SOURCE_MESH = {
    "nx": 256,
    "ny": 256,
    "range_x_m": 0.001,
    "range_y_m": 0.001,
}


def create_undulator_source(energy_eV: float, undulator_period_m: float,
                            num_periods: int, K_vertical: float,
                            electron_energy_GeV: float = 6.0,
                            beam_current_A: float = 0.2,
                            sampling_factor: float = 1.0,
                            mesh_params: dict | None = None) -> Any:
    """Create a single-electron undulator source wavefront.

    Args:
        energy_eV: Photon energy in eV
        undulator_period_m: Undulator period in meters
        num_periods: Number of undulator periods
        K_vertical: Vertical deflection parameter
        electron_energy_GeV: Electron beam energy in GeV
        beam_current_A: Electron beam current in Amperes
        sampling_factor: Controls mesh density (higher = finer sampling)
        mesh_params: Optional mesh override {nx, ny, range_x_m, range_y_m}

    Returns:
        SRWLWfr wavefront object
    """
    mp = {**DEFAULT_SOURCE_MESH, **(mesh_params or {})}

    # Magnetic field: planar undulator
    harmonic = SRWLMagFldH(1, "v", K_vertical)
    undulator = SRWLMagFldU([harmonic], undulator_period_m, num_periods)
    mag_field = SRWLMagFldC(
        [undulator],
        [0], [0], [0],  # center position
    )

    # Electron beam
    electron_beam = SRWLPartBeam()
    electron_beam.Iavg = beam_current_A
    electron_beam.partStatMom1.x = 0.0
    electron_beam.partStatMom1.y = 0.0
    electron_beam.partStatMom1.z = -(undulator_period_m * num_periods / 2)
    electron_beam.partStatMom1.xp = 0.0
    electron_beam.partStatMom1.yp = 0.0
    electron_beam.partStatMom1.gamma = electron_energy_GeV * 1e9 / 0.51099895e6

    # Wavefront mesh
    wfr = SRWLWfr()
    wfr.allocate(1, mp["nx"], mp["ny"])
    wfr.mesh.zStart = undulator_period_m * num_periods * 2  # observation distance
    wfr.mesh.eStart = energy_eV
    wfr.mesh.eFin = energy_eV
    wfr.mesh.xStart = -mp["range_x_m"] / 2
    wfr.mesh.xFin = mp["range_x_m"] / 2
    wfr.mesh.yStart = -mp["range_y_m"] / 2
    wfr.mesh.yFin = mp["range_y_m"] / 2
    wfr.partBeam = electron_beam

    # Calculate SR
    # Precision parameters: [1=method, step, relPrec, zStartInteg, zEndInteg, nPtInteg, useTermin, sampFact]
    srwl_main.CalcElecFieldSR(wfr, 0, mag_field, [1, 0.01, 0, 0, 50000, 1, sampling_factor])

    return wfr


def create_gaussian_source(energy_eV: float, waist_x_m: float, waist_y_m: float,
                           mesh_params: dict | None = None) -> Any:
    """Create a Gaussian beam source wavefront.

    Args:
        energy_eV: Photon energy in eV
        waist_x_m: Horizontal waist size (RMS) in meters
        waist_y_m: Vertical waist size (RMS) in meters
        mesh_params: Optional mesh override
    """
    mp = {**DEFAULT_SOURCE_MESH, **(mesh_params or {})}

    # Gaussian beam
    gsn_beam = SRWLGsnBm()
    gsn_beam.x = 0
    gsn_beam.y = 0
    gsn_beam.z = 0
    gsn_beam.xp = 0
    gsn_beam.yp = 0
    gsn_beam.avgPhotEn = energy_eV
    gsn_beam.pulseEn = 1e-3
    gsn_beam.repRate = 1
    gsn_beam.polar = 1  # linear horizontal
    gsn_beam.sigX = waist_x_m
    gsn_beam.sigY = waist_y_m
    gsn_beam.sigT = 1e-14
    gsn_beam.mx = 0  # TEM00
    gsn_beam.my = 0

    # Wavefront
    wfr = SRWLWfr()
    wfr.allocate(1, mp["nx"], mp["ny"])
    wfr.mesh.zStart = 0.0
    wfr.mesh.eStart = energy_eV
    wfr.mesh.eFin = energy_eV
    wfr.mesh.xStart = -mp["range_x_m"] / 2
    wfr.mesh.xFin = mp["range_x_m"] / 2
    wfr.mesh.yStart = -mp["range_y_m"] / 2
    wfr.mesh.yFin = mp["range_y_m"] / 2

    srwl_main.CalcElecFieldGaussian(wfr, gsn_beam, [0])

    return wfr


def create_bending_magnet_source(energy_eV: float, magnetic_field_T: float = 0.85,
                                 mesh_params: dict | None = None) -> Any:
    """Create a bending magnet source wavefront.

    Args:
        energy_eV: Photon energy in eV
        magnetic_field_T: Magnetic field strength in Tesla
        mesh_params: Optional mesh override
    """
    mp = {**DEFAULT_SOURCE_MESH, **(mesh_params or {})}

    electron_beam = SRWLPartBeam()
    electron_beam.Iavg = 0.2
    electron_beam.partStatMom1.gamma = energy_eV / 0.51099895e6 * 2

    wfr = SRWLWfr()
    wfr.allocate(1, mp["nx"], mp["ny"])
    wfr.mesh.zStart = 10.0
    wfr.mesh.eStart = energy_eV
    wfr.mesh.eFin = energy_eV
    wfr.mesh.xStart = -mp["range_x_m"] / 2
    wfr.mesh.xFin = mp["range_x_m"] / 2
    wfr.mesh.yStart = -mp["range_y_m"] / 2
    wfr.mesh.yFin = mp["range_y_m"] / 2
    wfr.partBeam = electron_beam

    return wfr


def detect_source_type(source_def: dict) -> str:
    """Detect source type from definition."""
    src_type = source_def.get("type", "").lower()
    if src_type in ("undulator", "bending_magnet", "gaussian"):
        return src_type
    # Try to infer from keys
    if "undulator_period_m" in source_def or "K_vertical" in source_def or "electron_energy_GeV" in source_def:
        return "undulator"
    if "waist_x_m" in source_def or "waist_y_m" in source_def:
        return "gaussian"
    if "magnetic_field_T" in source_def:
        return "bending_magnet"
    return "gaussian"  # default fallback


def create_source_wavefront(source_def: dict, mesh_params: dict | None = None) -> Any:
    """Create a source wavefront based on the source definition."""
    src_type = detect_source_type(source_def)

    if src_type == "undulator":
        return create_undulator_source(
            energy_eV=source_def.get("energy_eV", 12000),
            undulator_period_m=source_def.get("undulator_period_m", 0.021),
            num_periods=source_def.get("num_periods", 72),
            K_vertical=source_def.get("K_vertical", 1.5),
            electron_energy_GeV=source_def.get("electron_energy_GeV", 6.0),
            beam_current_A=source_def.get("beam_current_A", 0.2),
            sampling_factor=source_def.get("sampling_factor", 1.0),
            mesh_params=mesh_params,
        )
    elif src_type == "gaussian":
        return create_gaussian_source(
            energy_eV=source_def.get("energy_eV", 12000),
            waist_x_m=source_def.get("waist_x_m", 50e-6),
            waist_y_m=source_def.get("waist_y_m", 10e-6),
            mesh_params=mesh_params,
        )
    elif src_type == "bending_magnet":
        return create_bending_magnet_source(
            energy_eV=source_def.get("energy_eV", 12000),
            magnetic_field_T=source_def.get("magnetic_field_T", 0.85),
            mesh_params=mesh_params,
        )
    else:
        raise ValueError(f"Unknown source type: {src_type}")
