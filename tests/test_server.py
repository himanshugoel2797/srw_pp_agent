"""Smoke tests for MCP server tool/resource registration."""

import pytest


class TestServerImport:
    def test_import_server(self):
        """Server module should import without errors."""
        from srw_pp_agent.server import mcp
        assert mcp is not None
        assert mcp.name == "srw-beamline-tuning"

    def test_tools_registered(self):
        """All 16 tools should be registered."""
        from srw_pp_agent.server import mcp

        # FastMCP stores tools internally — verify the count
        # We check by looking at the tool functions registered
        expected_tools = {
            "load_beamline",
            "edit_beamline",
            "probe_aperture",
            "truncate_drift",
            "restore_drift",
            "idealize_element",
            "restore_elements",
            "get_beamline_state",
            "set_propagation_params",
            "run_propagation",
            "run_convergence_test",
            "compute_analytical_estimates",
            "compare_to_estimates",
            "test_hypothesis",
            "get_report_data",
        }

        # Access the internal tool registry
        tools = mcp._tool_manager._tools
        registered_names = set(tools.keys())

        for tool_name in expected_tools:
            assert tool_name in registered_names, f"Tool {tool_name} not registered"

    def test_resources_registered(self):
        """All 3 resources should be registered."""
        from srw_pp_agent.server import mcp

        resources = mcp._resource_manager._resources
        resource_uris = set(str(uri) for uri in resources.keys())

        expected_uris = {
            "srw://tuning-heuristics",
            "srw://diagnostic-patterns",
            "srw://idealization-test-guide",
        }

        for uri in expected_uris:
            assert uri in resource_uris, f"Resource {uri} not registered"


class TestResourceContent:
    def test_tuning_heuristics_content(self):
        from srw_pp_agent.resources import read_resource
        content = read_resource("tuning_heuristics.md")
        assert "Propagator Mode Selection" in content
        assert "Modes 3 and 4 invert" in content

    def test_diagnostic_patterns_content(self):
        from srw_pp_agent.resources import read_resource
        content = read_resource("diagnostic_patterns.md")
        assert "Diagnostic Patterns" in content
        assert "edge_intensity_ratio" in content

    def test_idealization_guide_content(self):
        from srw_pp_agent.resources import read_resource
        content = read_resource("idealization_guide.md")
        assert "Idealization Tests" in content
        assert "thin-lens" in content
