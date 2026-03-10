"""Per-element intensity thumbnail renderer for the dashboard.

Generates small heatmap thumbnails from 2D intensity arrays,
reusing the inferno colormap and LogNorm scaling from plotting.py.
"""

from __future__ import annotations

import base64
import io

import numpy as np


def render_element_thumbnail(
    intensity_2d: np.ndarray,
    mesh_info: dict,
    size_px: int = 150,
) -> str:
    """Render a small intensity heatmap thumbnail (no axes/labels).

    Args:
        intensity_2d: 2D numpy array of intensity values
        mesh_info: Dict with x_start, x_fin, y_start, y_fin keys
        size_px: Output image size in pixels (square)

    Returns:
        Base64-encoded PNG string
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    fig_size = size_px / 100  # matplotlib uses inches at 100 dpi
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))

    i_pos = np.where(intensity_2d > 0, intensity_2d, np.nan)
    vmin = np.nanmin(i_pos) if np.any(intensity_2d > 0) else 1e-10
    vmax = np.nanmax(intensity_2d) if np.any(intensity_2d > 0) else 1.0
    if vmin >= vmax:
        vmin = vmax * 1e-6

    ax.imshow(
        intensity_2d,
        norm=LogNorm(vmin=vmin, vmax=vmax),
        cmap="inferno",
        aspect="auto",
        origin="lower",
    )
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    return base64.b64encode(buf.getvalue()).decode("ascii")


def render_thumbnails_from_intermediates(intermediates: list[dict]) -> dict[str, str]:
    """Render intensity thumbnails from run_propagation intermediates.

    Only works if the intermediates contain intensity_2d data (from preview runs).
    Standard run_propagation returns metrics only, not raw intensity arrays.

    Args:
        intermediates: List of per-element intermediate dicts

    Returns:
        Dict mapping element_label -> base64 PNG string
    """
    thumbnails = {}
    for inter in intermediates:
        label = inter.get("element_label", "")
        # Check after-phase first, then before
        for phase in ("after", "before"):
            phase_data = inter.get(phase, {})
            if "intensity_2d" in phase_data and "mesh_info" in phase_data:
                thumbnails[label] = render_element_thumbnail(
                    phase_data["intensity_2d"],
                    phase_data["mesh_info"],
                )
                break
    return thumbnails
