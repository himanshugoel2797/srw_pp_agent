# Beamline JSON Format

The SRW Propagation Parameter Tuning server accepts beamline definitions in a
simplified JSON format. This document describes the schema.

## Top-Level Structure

```json
{
  "source": { ... },
  "elements": [ ... ]
}
```

| Field      | Type   | Required | Description                           |
|------------|--------|----------|---------------------------------------|
| `source`   | object | No       | Photon source parameters. Defaults to a 12 keV Gaussian source. |
| `elements` | array  | No       | Ordered list of optical elements.     |

---

## Source Definition

### Gaussian Source

```json
{
  "type": "gaussian",
  "energy_eV": 12000,
  "waist_x_m": 50e-6,
  "waist_y_m": 10e-6
}
```

| Field        | Type  | Default | Description                    |
|--------------|-------|---------|--------------------------------|
| `type`       | str   | `"gaussian"` | Source type identifier.   |
| `energy_eV`  | float | 12000   | Photon energy in eV.           |
| `waist_x_m`  | float | 50e-6   | Horizontal beam waist (sigma). |
| `waist_y_m`  | float | 10e-6   | Vertical beam waist (sigma).   |

### Undulator Source

```json
{
  "type": "undulator",
  "energy_eV": 12000,
  "electron_energy_GeV": 6.0,
  "beam_current_A": 0.2,
  "undulator_period_m": 0.021,
  "num_periods": 72,
  "K_vertical": 1.5,
  "sampling_factor": 1.0
}
```

| Field                | Type  | Default | Description                                |
|----------------------|-------|---------|--------------------------------------------|
| `type`               | str   |         | `"undulator"`                              |
| `energy_eV`          | float | 12000   | Photon energy in eV.                       |
| `electron_energy_GeV`| float | 6.0     | Electron beam energy in GeV.               |
| `beam_current_A`     | float | 0.2     | Electron beam current in Amperes.          |
| `undulator_period_m` | float | 0.021   | Undulator period in meters.                |
| `num_periods`        | int   | 72      | Number of undulator periods.               |
| `K_vertical`         | float | 1.5     | Vertical deflection parameter.             |
| `K_horizontal`       | float | 0.0     | Horizontal deflection parameter (0 for planar). |
| `sampling_factor`    | float | 1.0     | Mesh sampling density (higher = finer).    |

#### Extended Electron Beam Parameters

These parameters are optional and provide full control over the electron beam
definition. They are automatically populated when loading from SRW-native
Python scripts.

| Field                     | Type  | Default | Description                                   |
|---------------------------|-------|---------|-----------------------------------------------|
| `energy_spread`           | float | 0.0     | Relative RMS energy spread.                   |
| `emittance_x_m`           | float | 0.0     | Horizontal emittance [m].                     |
| `emittance_y_m`           | float | 0.0     | Vertical emittance [m].                       |
| `beam_size_x_m`           | float | 0.0     | Horizontal RMS beam size [m].                 |
| `beam_size_y_m`           | float | 0.0     | Vertical RMS beam size [m].                   |
| `beam_divergence_x_rad`   | float | 0.0     | Horizontal RMS angular divergence [rad].      |
| `beam_divergence_y_rad`   | float | 0.0     | Vertical RMS angular divergence [rad].        |
| `beam_center_x_m`         | float | 0.0     | Horizontal beam center position [m].          |
| `beam_center_y_m`         | float | 0.0     | Vertical beam center position [m].            |
| `beam_angle_x_rad`        | float | 0.0     | Horizontal beam angle [rad].                  |
| `beam_angle_y_rad`        | float | 0.0     | Vertical beam angle [rad].                    |
| `mixed_moment_xxp`        | float | 0.0     | Horizontal position-angle mixed 2nd moment.   |
| `mixed_moment_yyp`        | float | 0.0     | Vertical position-angle mixed 2nd moment.     |
| `longitudinal_drift_m`    | float | 0.0     | Longitudinal drift before calculation [m].    |
| `energy_deviation_GeV`    | float | 0.0     | Average energy deviation [GeV].               |
| `first_optic_distance_m`  | float | None    | First optical element distance [m] (`op_r`).  |

### Bending Magnet Source

```json
{
  "type": "bending_magnet",
  "energy_eV": 12000,
  "magnetic_field_T": 0.85
}
```

| Field             | Type  | Default | Description                         |
|-------------------|-------|---------|-------------------------------------|
| `type`            | str   |         | `"bending_magnet"`                  |
| `energy_eV`       | float | 12000   | Photon energy in eV.                |
| `magnetic_field_T` | float | 0.85   | Magnetic field strength in Tesla.   |

---

## Element Types

Every element must have a `type` field. A `label` field is strongly
recommended (auto-generated as `"<type>_<index>"` if omitted). Labels must be
unique across the beamline.

### Drift

Free-space propagation.

```json
{
  "type": "drift",
  "label": "D1",
  "length_m": 10.0
}
```

| Field      | Type  | Required | Description              |
|------------|-------|----------|--------------------------|
| `length_m` | float | Yes      | Drift length in meters.  |

### Lens (Thin Lens)

Ideal thin lens with independent horizontal/vertical focal lengths.

```json
{
  "type": "lens",
  "label": "L1",
  "focal_length_m": 2.0
}
```

| Field            | Type  | Default         | Description                       |
|------------------|-------|-----------------|-----------------------------------|
| `focal_length_m` | float |                 | Focal length (both planes).       |
| `fx`             | float | `focal_length_m`| Horizontal focal length.          |
| `fy`             | float | `fx`            | Vertical focal length.            |

Use `fx`/`fy` when horizontal and vertical focal lengths differ. If
`focal_length_m` is provided, it sets both planes.

### Aperture

Beam-limiting aperture.

```json
{
  "type": "aperture",
  "label": "A1",
  "shape": "rectangular",
  "size_x_m": 0.001,
  "size_y_m": 0.002
}
```

| Field      | Type  | Default       | Description                                |
|------------|-------|---------------|--------------------------------------------|
| `shape`    | str   | `"rectangular"`| `"rectangular"` or `"circular"`.          |
| `size_x_m` | float |               | Horizontal full size (or diameter if circular). |
| `size_y_m` | float | `size_x_m`    | Vertical full size (ignored for circular). |
| `diameter_m`| float|               | Alternative to `size_x_m` for circular.   |

### Mirror

Grazing-incidence mirror. Three subtypes are supported: **flat**,
**elliptical**, and **cylindrical**. Both elliptical and cylindrical mirrors
focus in **one plane only** (the tangential plane).

#### Flat Mirror

No focusing. Used for beam deflection or as a thermal/harmonic filter.

```json
{
  "type": "mirror",
  "label": "M1_flat",
  "subtype": "flat",
  "orientation": "vertical",
  "grazing_angle_mrad": 3.0,
  "tangential_size_m": 0.4,
  "sagittal_size_m": 0.02
}
```

A mirror without `object_distance_m`/`image_distance_m` or
`radius_of_curvature_m` is automatically treated as flat.

#### Elliptical Mirror

Focuses in the **tangential plane only**. Defined by the object distance (p)
and image distance (q). The effective focal length is `f = p*q / (p+q)`.

```json
{
  "type": "mirror",
  "label": "M2_ell",
  "subtype": "elliptical",
  "orientation": "vertical",
  "focusing_plane": "tangential",
  "grazing_angle_mrad": 3.0,
  "tangential_size_m": 0.4,
  "sagittal_size_m": 0.02,
  "object_distance_m": 30.0,
  "image_distance_m": 5.0
}
```

#### Cylindrical Mirror

Focuses in **one plane only**. Defined by its radius of curvature. The
effective focal length is `f = R * sin(theta) / 2`.

```json
{
  "type": "mirror",
  "label": "M3_cyl",
  "subtype": "cylindrical",
  "orientation": "horizontal",
  "focusing_plane": "tangential",
  "grazing_angle_mrad": 3.0,
  "tangential_size_m": 0.3,
  "sagittal_size_m": 0.02,
  "radius_of_curvature_m": 1000.0
}
```

#### Common Mirror Parameters

| Field                  | Type  | Default        | Description                                                |
|------------------------|-------|----------------|------------------------------------------------------------|
| `subtype`              | str   | auto           | `"flat"`, `"elliptical"`, or `"cylindrical"`. Auto-detected from parameters if omitted. |
| `orientation`          | str   | `"vertical"`   | `"vertical"` or `"horizontal"` — deflection plane.        |
| `focusing_plane`       | str   | `"tangential"` | `"tangential"` or `"sagittal"` — which plane is curved.   |
| `grazing_angle_mrad`   | float | 3.0            | Grazing angle in milliradians.                             |
| `tangential_size_m`    | float | 0.4            | Mirror length along the beam direction.                    |
| `sagittal_size_m`      | float | 0.02           | Mirror width perpendicular to the beam.                    |

#### Elliptical-Specific Parameters

| Field               | Type  | Default | Description                             |
|---------------------|-------|---------|-----------------------------------------|
| `object_distance_m` | float |         | Source-to-mirror distance (p).          |
| `image_distance_m`  | float |         | Mirror-to-focus distance (q).           |

#### Cylindrical-Specific Parameters

| Field                  | Type  | Default | Description                          |
|------------------------|-------|---------|--------------------------------------|
| `radius_of_curvature_m`| float |        | Radius of curvature (R) in meters.   |

**Subtype auto-detection:** If `subtype` is omitted, the server infers it
from the parameters present:
- `object_distance_m` or `image_distance_m` present → `"elliptical"`
- `radius_of_curvature_m` present → `"cylindrical"`
- Neither → `"flat"`

**Cylindrical vs elliptical:** Both focus in one plane only. A
Kirkpatrick-Baez (KB) system uses two mirrors (typically elliptical) at right
angles, each focusing one axis. A cylindrical mirror is defined by its
radius of curvature, while an elliptical mirror is defined by its conjugate
distances (p and q).

### Crystal

Bragg-diffracting crystal, typically used in Double Crystal Monochromator (DCM)
pairs. Crystal susceptibility parameters (`psi*`) are energy-dependent and
should be computed for the specific reflection and photon energy.

```json
{
  "type": "crystal",
  "label": "DCM_C1",
  "d_spacing_A": 3.1356,
  "energy_eV": 10063,
  "psi0r": -9.64e-06,
  "psi0i": 1.46e-07,
  "psiHr": -5.09e-06,
  "psiHi": 1.02e-07,
  "psiHBr": -5.09e-06,
  "psiHBi": 1.02e-07,
  "thickness_m": 0.01,
  "asymmetry_angle_rad": 0.0,
  "use_case": 1,
  "diffraction_angle_rad": 1.5708,
  "grazing_angle_rad": 0.1978
}
```

| Field                    | Type  | Default | Description                                    |
|--------------------------|-------|---------|------------------------------------------------|
| `d_spacing_A`            | float | 3.1356  | Crystal d-spacing in Angstroms.                |
| `energy_eV`              | float | 10000   | Photon energy for susceptibility values.       |
| `psi0r`                  | float | 0       | Real part of 0th Fourier comp. of susceptibility. |
| `psi0i`                  | float | 0       | Imaginary part of 0th Fourier comp.            |
| `psiHr`                  | float | 0       | Real part of H Fourier comp. of susceptibility. |
| `psiHi`                  | float | 0       | Imaginary part of H Fourier comp.              |
| `psiHBr`                 | float | 0       | Real part of H-bar Fourier comp.               |
| `psiHBi`                 | float | 0       | Imaginary part of H-bar Fourier comp.          |
| `thickness_m`            | float | 0.01    | Crystal thickness in meters.                   |
| `asymmetry_angle_rad`    | float | 0.0     | Asymmetry angle in radians.                    |
| `use_case`               | int   | 1       | SRW use case flag (1 = Bragg, 2 = Laue).       |
| `diffraction_angle_rad`  | float | 0       | Diffraction plane roll angle in radians.       |
| `grazing_angle_rad`      | float | 0.2     | Bragg/grazing angle in radians.                |
| `orientation`            | str   | `"horizontal"` | `"horizontal"` or `"vertical"`.         |

**Orientation vectors:** For DCM crystal pairs (where the two crystals have
opposite normal vector signs), explicit orientation vectors (`nvx`, `nvy`,
`nvz`, `tvx`, `tvy`) can be provided instead of `grazing_angle_rad` +
`orientation`. These are preserved exactly when loading from SRW-native scripts.

### Compound Refractive Lens (CRL)

```json
{
  "type": "crl",
  "label": "CRL1",
  "n_lenses": 10,
  "single_lens_focal_length_m": 20.0,
  "physical_aperture_m": 0.001
}
```

| Field                       | Type  | Default | Description                          |
|-----------------------------|-------|---------|--------------------------------------|
| `n_lenses`                  | int   | 1       | Number of individual lenses.         |
| `single_lens_focal_length_m`| float |         | Focal length of one lens.            |
| `focal_length_m`            | float | computed| Effective f = single_f / n_lenses.   |
| `physical_aperture_m`       | float | 0.001   | Physical aperture diameter.          |
| `diameter_m`                | float | 0.001   | Alternative to `physical_aperture_m`.|

### Zone Plate

```json
{
  "type": "zone_plate",
  "label": "ZP1",
  "focal_length_m": 0.05,
  "diameter_m": 0.0002,
  "outermost_zone_width_m": 30e-9
}
```

| Field                   | Type  | Default | Description                         |
|-------------------------|-------|---------|-------------------------------------|
| `focal_length_m`        | float | 0.1     | Focal length.                       |
| `diameter_m`            | float | 0.0001  | Zone plate diameter.                |
| `outermost_zone_width_m`| float |         | Outermost zone width (resolution).  |

---

## Complete Example

A KB microscopy beamline with an undulator source, using two elliptical
mirrors for vertical and horizontal focusing:

```json
{
  "source": {
    "type": "undulator",
    "energy_eV": 12000,
    "electron_energy_GeV": 6.0,
    "beam_current_A": 0.2,
    "undulator_period_m": 0.021,
    "num_periods": 72,
    "K_vertical": 1.5,
    "sampling_factor": 1.0
  },
  "elements": [
    {"type": "drift", "length_m": 28.0, "label": "D1"},
    {
      "type": "mirror",
      "subtype": "flat",
      "orientation": "vertical",
      "grazing_angle_mrad": 3.0,
      "tangential_size_m": 0.4,
      "sagittal_size_m": 0.04,
      "label": "M1_flat"
    },
    {"type": "drift", "length_m": 7.0, "label": "D2"},
    {
      "type": "mirror",
      "subtype": "elliptical",
      "orientation": "vertical",
      "focusing_plane": "tangential",
      "grazing_angle_mrad": 3.0,
      "tangential_size_m": 0.3,
      "sagittal_size_m": 0.02,
      "object_distance_m": 35.0,
      "image_distance_m": 2.5,
      "label": "M2_KB_V"
    },
    {"type": "drift", "length_m": 1.0, "label": "D3"},
    {
      "type": "mirror",
      "subtype": "elliptical",
      "orientation": "horizontal",
      "focusing_plane": "tangential",
      "grazing_angle_mrad": 3.0,
      "tangential_size_m": 0.2,
      "sagittal_size_m": 0.02,
      "object_distance_m": 36.0,
      "image_distance_m": 2.0,
      "label": "M3_KB_H"
    },
    {"type": "drift", "length_m": 2.0, "label": "D4_to_sample"}
  ]
}
```

---

## Loading from SRW-Native Python Scripts

The server can load beamlines directly from SRW-native Python scripts
(e.g. those generated by Sirepo). These scripts use the standard `varParam`
list format with `set_optics()` functions.

Pass the `.py` file path to `load_beamline` — the parser will:

1. Extract the `varParam` list and convert it to simplified JSON
2. Map electron beam (`ebm_*`) and undulator (`und_*`) parameters to the
   undulator source definition
3. Detect element types from parameter patterns (`op_*` prefixes):
   - `op_X_L` → drift
   - `op_X_shape` → aperture
   - `op_X_d_sp` → crystal
   - `op_X_p` + `op_X_q` → elliptical mirror
4. Preserve propagation parameters (`op_*_pp` arrays) as
   `_propagation_params` for automatic initialization
5. Preserve crystal orientation vectors exactly (important for DCM pairs)

The original SRW 17-element propagation parameter arrays are also stored
in `_raw_propagation_params` for lossless round-tripping.
