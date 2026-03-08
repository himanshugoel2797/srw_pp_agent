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
  "num_periods": 72,
  "undulator_period_m": 0.021
}
```

| Field               | Type  | Default | Description                   |
|---------------------|-------|---------|-------------------------------|
| `type`              | str   |         | `"undulator"`                 |
| `energy_eV`         | float | 12000   | Photon energy in eV.          |
| `num_periods`       | int   | 72      | Number of undulator periods.  |
| `undulator_period_m`| float | 0.021   | Undulator period in meters.   |

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
**elliptical**, and **cylindrical**.

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

A mirror without `focal_length_m` is automatically treated as flat even if
`subtype` is omitted.

#### Elliptical Mirror

Focuses in both the tangential and sagittal planes. This is the default
subtype when `focal_length_m` is present.

```json
{
  "type": "mirror",
  "label": "M2_ell",
  "subtype": "elliptical",
  "orientation": "vertical",
  "grazing_angle_mrad": 3.0,
  "tangential_size_m": 0.4,
  "sagittal_size_m": 0.02,
  "focal_length_m": 5.0,
  "object_distance_m": 30.0,
  "image_distance_m": 5.0
}
```

#### Cylindrical Mirror

Focuses in **one plane only**. The `focusing_plane` field specifies which
direction is curved.

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
  "focal_length_m": 3.0,
  "object_distance_m": 25.0,
  "image_distance_m": 3.0
}
```

#### Common Mirror Parameters

| Field               | Type  | Default      | Description                                                |
|---------------------|-------|--------------|------------------------------------------------------------|
| `subtype`           | str   | auto         | `"flat"`, `"elliptical"`, or `"cylindrical"`. Auto-detected from `focal_length_m` if omitted. |
| `orientation`       | str   | `"vertical"` | `"vertical"` or `"horizontal"` — deflection plane.        |
| `grazing_angle_mrad`| float | 3.0          | Grazing angle in milliradians.                             |
| `tangential_size_m` | float | 0.4          | Mirror length along the beam direction.                    |
| `sagittal_size_m`   | float | 0.02         | Mirror width perpendicular to the beam.                    |
| `focal_length_m`    | float | None         | Effective focal length (required for elliptical/cylindrical). |
| `object_distance_m` | float | 1e23         | Source-to-mirror distance for curved mirrors.              |
| `image_distance_m`  | float | `focal_length_m` | Mirror-to-focus distance for curved mirrors.           |
| `focusing_plane`    | str   | `"tangential"` | For cylindrical only: `"tangential"` or `"sagittal"`.    |

**Cylindrical vs elliptical:** A Kirkpatrick-Baez (KB) system typically uses
two cylindrical mirrors at right angles, each focusing one axis. A single
elliptical mirror focuses both axes simultaneously.

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

A KB microscopy beamline with an undulator source:

```json
{
  "source": {
    "type": "undulator",
    "energy_eV": 12000,
    "num_periods": 72,
    "undulator_period_m": 0.021
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
      "subtype": "cylindrical",
      "orientation": "vertical",
      "focusing_plane": "tangential",
      "grazing_angle_mrad": 3.0,
      "tangential_size_m": 0.3,
      "sagittal_size_m": 0.02,
      "focal_length_m": 2.5,
      "object_distance_m": 35.0,
      "image_distance_m": 2.5,
      "label": "M2_KB_V"
    },
    {"type": "drift", "length_m": 1.0, "label": "D3"},
    {
      "type": "mirror",
      "subtype": "cylindrical",
      "orientation": "horizontal",
      "focusing_plane": "tangential",
      "grazing_angle_mrad": 3.0,
      "tangential_size_m": 0.2,
      "sagittal_size_m": 0.02,
      "focal_length_m": 2.0,
      "object_distance_m": 36.0,
      "image_distance_m": 2.0,
      "label": "M3_KB_H"
    },
    {"type": "drift", "length_m": 2.0, "label": "D4_to_sample"}
  ]
}
```
