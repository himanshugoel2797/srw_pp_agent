"""Static resource files for MCP resources."""

from pathlib import Path

_RESOURCES_DIR = Path(__file__).parent


def read_resource(name: str) -> str:
    """Read a resource file by name."""
    path = _RESOURCES_DIR / name
    return path.read_text()
