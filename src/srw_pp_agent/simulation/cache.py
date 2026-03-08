"""Intermediate wavefront cache with invalidation logic.

Stores serialized wavefronts by element label. When any change occurs at
element N, all cached wavefronts from N onward are invalidated.
"""

from __future__ import annotations

from ..srw_interface.wavefront import copy_wavefront, deserialize_wavefront, serialize_wavefront


class WavefrontCache:
    """Cache for intermediate wavefronts during propagation.

    The agent doesn't know about the cache — it just calls tools and gets
    correct results. This is purely a server-side optimization.
    """

    def __init__(self) -> None:
        self._cache: dict[str, bytes] = {}
        self._element_order: list[str] = []

    def set_element_order(self, labels: list[str]) -> None:
        """Update the element ordering (call after beamline rebuild)."""
        self._element_order = list(labels)

    def get(self, label: str):
        """Get a cached wavefront copy, or None if not cached."""
        data = self._cache.get(label)
        if data is None:
            return None
        return deserialize_wavefront(data)

    def put(self, label: str, wfr) -> None:
        """Cache a wavefront (deep copy is serialized)."""
        self._cache[label] = serialize_wavefront(wfr)

    def invalidate_from(self, label: str) -> None:
        """Invalidate this label and all downstream cached wavefronts."""
        if label not in self._element_order:
            # Label not in order (might be a probe label); invalidate all
            self.invalidate_all()
            return

        idx = self._element_order.index(label)
        labels_to_remove = self._element_order[idx:]
        for lbl in labels_to_remove:
            self._cache.pop(lbl, None)

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
