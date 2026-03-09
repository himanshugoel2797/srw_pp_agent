"""Preview image rendering: 2D intensity map with H/V cuts through peak.

Generates PNG images for visual beam quality assessment at any beamline element.
Supports before/after comparison panels and compresses output to < 1 MB.
"""

from __future__ import annotations

import io

import numpy as np


def render_preview_image(
    snapshots: list[dict],
    element_label: str,
    max_bytes: int = 1_000_000,
) -> bytes:
    """Render 2D intensity map with H/V cuts through the peak for each snapshot.

    Args:
        snapshots: List of dicts with keys: phase, intensity_2d (np.ndarray), mesh_info (dict)
        element_label: Label of the element being previewed
        max_bytes: Maximum image size in bytes (default 1 MB)

    Returns:
        PNG image as bytes
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    from matplotlib.colors import LogNorm

    n_panels = len(snapshots)
    if n_panels == 0:
        raise ValueError("No snapshots to render")

    fig_width = 6 * n_panels
    fig = plt.figure(figsize=(fig_width, 6))

    for panel_idx, snap in enumerate(snapshots):
        intensity = snap["intensity_2d"]
        mesh = snap["mesh_info"]
        phase = snap["phase"]

        ny, nx = intensity.shape
        x = np.linspace(mesh["x_start"] * 1e3, mesh["x_fin"] * 1e3, nx)  # mm
        y = np.linspace(mesh["y_start"] * 1e3, mesh["y_fin"] * 1e3, ny)  # mm

        # Find peak position
        peak_iy, peak_ix = np.unravel_index(np.argmax(intensity), intensity.shape)
        h_cut = intensity[peak_iy, :]
        v_cut = intensity[:, peak_ix]

        # GridSpec: 2D map top-left, H cut bottom-left, V cut top-right
        gs = GridSpec(
            2, 2,
            width_ratios=[3, 1],
            height_ratios=[3, 1],
            left=panel_idx / n_panels + 0.08 / n_panels,
            right=(panel_idx + 1) / n_panels - 0.04 / n_panels,
            bottom=0.12,
            top=0.88,
            wspace=0.05,
            hspace=0.05,
        )

        ax_map = fig.add_subplot(gs[0, 0])
        ax_hcut = fig.add_subplot(gs[1, 0], sharex=ax_map)
        ax_vcut = fig.add_subplot(gs[0, 1], sharey=ax_map)

        # 2D intensity map (log scale)
        i_pos = np.where(intensity > 0, intensity, np.nan)
        vmin = np.nanmin(i_pos) if np.any(intensity > 0) else 1e-10
        vmax = np.nanmax(intensity) if np.any(intensity > 0) else 1.0
        if vmin >= vmax:
            vmin = vmax * 1e-6

        ax_map.pcolormesh(
            x, y, intensity,
            norm=LogNorm(vmin=vmin, vmax=vmax),
            cmap="inferno",
            shading="auto",
        )
        ax_map.axhline(y[peak_iy], color="cyan", lw=0.5, alpha=0.5)
        ax_map.axvline(x[peak_ix], color="cyan", lw=0.5, alpha=0.5)
        ax_map.set_ylabel("y [mm]")
        ax_map.tick_params(labelbottom=False)
        ax_map.set_title(f"{element_label} — {phase}")

        # Horizontal cut
        ax_hcut.plot(x, h_cut, color="tab:blue", lw=0.8)
        ax_hcut.set_xlabel("x [mm]")
        ax_hcut.set_ylabel("I")
        ax_hcut.ticklabel_format(axis="y", style="scientific", scilimits=(-2, 2))

        # Vertical cut (rotated: intensity on x-axis, y on y-axis)
        ax_vcut.plot(v_cut, y, color="tab:red", lw=0.8)
        ax_vcut.set_xlabel("I")
        ax_vcut.tick_params(labelleft=False)
        ax_vcut.ticklabel_format(axis="x", style="scientific", scilimits=(-2, 2))

    # Compression loop: reduce DPI until under max_bytes
    for dpi in (150, 120, 100, 80, 60):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
        if buf.tell() <= max_bytes:
            break
    plt.close(fig)

    return buf.getvalue()
