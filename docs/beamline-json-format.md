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
| `sampling_factor`    | float | 1.0     | Mesh sampling density (higher = finer).    |

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
