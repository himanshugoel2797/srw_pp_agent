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
    try:
        from srwpy.srwlib import (
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
                            K_horizontal: float = 0.0,
                            energy_spread: float = 0.0,
                            emittance_x_m: float = 0.0,
                            emittance_y_m: float = 0.0,
                            beam_size_x_m: float = 0.0,
                            beam_size_y_m: float = 0.0,
                            beam_divergence_x_rad: float = 0.0,
                            beam_divergence_y_rad: float = 0.0,
                            beam_center_x_m: float = 0.0,
                            beam_center_y_m: float = 0.0,
                            beam_angle_x_rad: float = 0.0,
                            beam_angle_y_rad: float = 0.0,
                            mixed_moment_xxp: float = 0.0,
                            mixed_moment_yyp: float = 0.0,
                            longitudinal_drift_m: float = 0.0,
                            energy_deviation_GeV: float = 0.0,
                            initial_z_m: float = 0.0,
                            symmetry_vertical: int = -1,
                            symmetry_horizontal: int = 1,
                            first_optic_distance_m: float | None = None,
                            mesh_params: dict | None = None) -> Any:
    """Create a single-electron undulator source wavefront.

    Args:
        energy_eV: Photon energy in eV.
        undulator_period_m: Undulator period in meters.
        num_periods: Number of undulator periods.
        K_vertical: Vertical deflection parameter.
        electron_energy_GeV: Electron beam energy in GeV.
        beam_current_A: Electron beam current in Amperes.
        sampling_factor: Controls mesh density (higher = finer sampling).
        K_horizontal: Horizontal deflection parameter (0 for planar undulator).
        energy_spread: Relative energy spread (RMS).
        emittance_x_m: Horizontal emittance in meters.
        emittance_y_m: Vertical emittance in meters.
        beam_size_x_m: Horizontal RMS beam size in meters.
        beam_size_y_m: Vertical RMS beam size in meters.
        beam_divergence_x_rad: Horizontal RMS angular divergence in radians.
        beam_divergence_y_rad: Vertical RMS angular divergence in radians.
        beam_center_x_m: Horizontal beam center position in meters.
        beam_center_y_m: Vertical beam center position in meters.
        beam_angle_x_rad: Horizontal beam angle in radians.
        beam_angle_y_rad: Vertical beam angle in radians.
        mixed_moment_xxp: Horizontal position-angle mixed 2nd order moment.
        mixed_moment_yyp: Vertical position-angle mixed 2nd order moment.
        longitudinal_drift_m: Longitudinal drift before calculation.
        energy_deviation_GeV: Average energy deviation in GeV.
        initial_z_m: Initial electron longitudinal position (ebm_z). Default 0.
        symmetry_vertical: Vertical field symmetry: 1=cos (symmetric), -1=sin (anti-symmetric).
        symmetry_horizontal: Horizontal field symmetry: 1=cos, -1=sin.
        first_optic_distance_m: Distance from source to first optical element (op_r).
            Sets wfr.mesh.zStart. Defaults to 2 * undulator length if not provided.
        mesh_params: Optional mesh override {nx, ny, range_x_m, range_y_m}.

    Returns:
        SRWLWfr wavefront object.
    """
    mp = {**DEFAULT_SOURCE_MESH, **(mesh_params or {})}

    # Magnetic field: undulator harmonics
    # SRWLMagFldH expects B in Tesla, convert K back to B:
    # K = 0.9338 * B[T] * lambda_u[cm]  =>  B = K / (0.9338 * lambda_u[cm])
    lambda_u_cm = undulator_period_m * 100
    B_vertical = K_vertical / (0.9338 * lambda_u_cm)
    harmonics = [SRWLMagFldH(_n=1, _h_or_v="v", _B=B_vertical, _s=symmetry_vertical)]
    if K_horizontal:
        B_horizontal = K_horizontal / (0.9338 * lambda_u_cm)
        harmonics.append(SRWLMagFldH(_n=1, _h_or_v="h", _B=B_horizontal, _s=symmetry_horizontal))
    undulator = SRWLMagFldU(harmonics, undulator_period_m, num_periods)
    mag_field = SRWLMagFldC(
        [undulator],
        [0], [0], [0],  # center position
    )

    # Electron beam
    electron_beam = SRWLPartBeam()
    electron_beam.Iavg = beam_current_A
    electron_beam.partStatMom1.x = beam_center_x_m
    electron_beam.partStatMom1.y = beam_center_y_m
    electron_beam.partStatMom1.z = initial_z_m
    electron_beam.partStatMom1.xp = beam_angle_x_rad
    electron_beam.partStatMom1.yp = beam_angle_y_rad
    electron_beam.partStatMom1.gamma = (electron_energy_GeV + energy_deviation_GeV) * 1e9 / 0.51099895e6

    # Set 2nd order statistical moments if beam size info is provided
    if beam_size_x_m:
        electron_beam.arStatMom2[0] = beam_size_x_m ** 2       # <x^2>
    if beam_divergence_x_rad:
        electron_beam.arStatMom2[1] = mixed_moment_xxp         # <x*x'>
        electron_beam.arStatMom2[2] = beam_divergence_x_rad ** 2  # <x'^2>
    if beam_size_y_m:
        electron_beam.arStatMom2[3] = beam_size_y_m ** 2       # <y^2>
    if beam_divergence_y_rad:
        electron_beam.arStatMom2[4] = mixed_moment_yyp         # <y*y'>
        electron_beam.arStatMom2[5] = beam_divergence_y_rad ** 2  # <y'^2>
    if energy_spread:
        electron_beam.arStatMom2[10] = energy_spread ** 2      # <(dE/E)^2>

    # Apply longitudinal drift if specified
    if longitudinal_drift_m:
        electron_beam.drift(longitudinal_drift_m)

    # Wavefront mesh
    wfr = SRWLWfr()
    wfr.allocate(1, mp["nx"], mp["ny"])
    wfr.mesh.zStart = first_optic_distance_m if first_optic_distance_m is not None else undulator_period_m * num_periods * 2
    wfr.mesh.eStart = energy_eV
    wfr.mesh.eFin = energy_eV
    wfr.mesh.xStart = -mp["range_x_m"] / 2
    wfr.mesh.xFin = mp["range_x_m"] / 2
    wfr.mesh.yStart = -mp["range_y_m"] / 2
    wfr.mesh.yFin = mp["range_y_m"] / 2
    wfr.partBeam = electron_beam

    # Calculate SR
    # Precision: [method, relPrec, zStartInteg, zEndInteg, nPtTraj, useTermin, sampFact]
    # method=1 (auto-undulator), relPrec=0.01, zStart/zEnd=0 (auto),
    # nPtTraj=50000 (trajectory points), useTermin=1 (terminating terms),
    # sampFact controls automatic mesh adjustment to properly sample the radiation
    srwl_main.CalcElecFieldSR(wfr, 0, mag_field, [1, 0.01, 0, 0, 50000, 1, sampling_factor])

    return wfr


def create_gaussian_source(energy_eV: float, waist_x_m: float, waist_y_m: float,
                           first_optic_distance_m: float | None = None,
                           mesh_params: dict | None = None) -> Any:
    """Create a Gaussian beam source wavefront.

    Args:
        energy_eV: Photon energy in eV
        waist_x_m: Horizontal waist size (RMS) in meters
        waist_y_m: Vertical waist size (RMS) in meters
        first_optic_distance_m: Distance from source to first optical element (op_r).
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
    wfr.mesh.zStart = first_optic_distance_m if first_optic_distance_m is not None else 0.0
    wfr.mesh.eStart = energy_eV
    wfr.mesh.eFin = energy_eV
    wfr.mesh.xStart = -mp["range_x_m"] / 2
    wfr.mesh.xFin = mp["range_x_m"] / 2
    wfr.mesh.yStart = -mp["range_y_m"] / 2
    wfr.mesh.yFin = mp["range_y_m"] / 2

    srwl_main.CalcElecFieldGaussian(wfr, gsn_beam, [0])

    return wfr


def create_bending_magnet_source(energy_eV: float, magnetic_field_T: float = 0.85,
                                 first_optic_distance_m: float | None = None,
                                 mesh_params: dict | None = None) -> Any:
    """Create a bending magnet source wavefront.

    Args:
        energy_eV: Photon energy in eV
        magnetic_field_T: Magnetic field strength in Tesla
        first_optic_distance_m: Distance from source to first optical element (op_r).
        mesh_params: Optional mesh override
    """
    mp = {**DEFAULT_SOURCE_MESH, **(mesh_params or {})}

    electron_beam = SRWLPartBeam()
    electron_beam.Iavg = 0.2
    electron_beam.partStatMom1.gamma = energy_eV / 0.51099895e6 * 2

    wfr = SRWLWfr()
    wfr.allocate(1, mp["nx"], mp["ny"])
    wfr.mesh.zStart = first_optic_distance_m if first_optic_distance_m is not None else 10.0
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

    first_optic_distance_m = source_def.get("first_optic_distance_m")

    if src_type == "undulator":
        return create_undulator_source(
            energy_eV=source_def.get("energy_eV", 12000),
            undulator_period_m=source_def.get("undulator_period_m", 0.021),
            num_periods=source_def.get("num_periods", 72),
            K_vertical=source_def.get("K_vertical", 1.5),
            electron_energy_GeV=source_def.get("electron_energy_GeV", 6.0),
            beam_current_A=source_def.get("beam_current_A", 0.2),
            sampling_factor=source_def.get("sampling_factor", 1.0),
            K_horizontal=source_def.get("K_horizontal", 0.0),
            energy_spread=source_def.get("energy_spread", 0.0),
            emittance_x_m=source_def.get("emittance_x_m", 0.0),
            emittance_y_m=source_def.get("emittance_y_m", 0.0),
            beam_size_x_m=source_def.get("beam_size_x_m", 0.0),
            beam_size_y_m=source_def.get("beam_size_y_m", 0.0),
            beam_divergence_x_rad=source_def.get("beam_divergence_x_rad", 0.0),
            beam_divergence_y_rad=source_def.get("beam_divergence_y_rad", 0.0),
            beam_center_x_m=source_def.get("beam_center_x_m", 0.0),
            beam_center_y_m=source_def.get("beam_center_y_m", 0.0),
            beam_angle_x_rad=source_def.get("beam_angle_x_rad", 0.0),
            beam_angle_y_rad=source_def.get("beam_angle_y_rad", 0.0),
            mixed_moment_xxp=source_def.get("mixed_moment_xxp", 0.0),
            mixed_moment_yyp=source_def.get("mixed_moment_yyp", 0.0),
            longitudinal_drift_m=source_def.get("longitudinal_drift_m", 0.0),
            energy_deviation_GeV=source_def.get("energy_deviation_GeV", 0.0),
            initial_z_m=source_def.get("initial_z_m", 0.0),
            symmetry_vertical=source_def.get("symmetry_vertical", -1),
            symmetry_horizontal=source_def.get("symmetry_horizontal", 1),
            first_optic_distance_m=first_optic_distance_m,
            mesh_params=mesh_params or source_def.get("_mesh_params"),
        )
    elif src_type == "gaussian":
        return create_gaussian_source(
            energy_eV=source_def.get("energy_eV", 12000),
            waist_x_m=source_def.get("waist_x_m", 50e-6),
            waist_y_m=source_def.get("waist_y_m", 10e-6),
            first_optic_distance_m=first_optic_distance_m,
            mesh_params=mesh_params,
        )
    elif src_type == "bending_magnet":
        return create_bending_magnet_source(
            energy_eV=source_def.get("energy_eV", 12000),
            magnetic_field_T=source_def.get("magnetic_field_T", 0.85),
            first_optic_distance_m=first_optic_distance_m,
            mesh_params=mesh_params,
        )
    else:
        raise ValueError(f"Unknown source type: {src_type}")
