"""Ollama agent loop: drives an LLM that calls domain functions as tools.

Streams LLM reasoning and tool invocations to the dashboard frontend
via WebSocket messages.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import traceback
from typing import Any

import httpx

from ..resources import read_resource
from ..session import TuningSession

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 50


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    tuning = read_resource("tuning_heuristics.md")
    diagnostic = read_resource("diagnostic_patterns.md")
    idealization = read_resource("idealization_guide.md")
    return f"""You are an expert SRW beamline propagation parameter tuning agent.

Your goal is to iteratively tune propagation parameters for a synchrotron beamline simulation until the results are physically consistent and computationally efficient.

You have access to tools for loading beamlines, running simulations, analyzing results, and generating visualizations. Follow this workflow:

1. Load the beamline definition
2. Compute analytical estimates to understand expected beam behavior
3. Set initial propagation parameters based on physics heuristics
4. Run propagation and compare to estimates
5. Diagnose any discrepancies and adjust parameters
6. Use preview_intensity to visualize beam profiles at key elements
7. Run convergence tests to verify parameter adequacy
8. Repeat until results are physically consistent

Always call preview_intensity after running propagation so the user can see the beam profiles.

## Propagation Parameter Heuristics

{tuning}

## Diagnostic Patterns

{diagnostic}

## Idealization Test Guide

{idealization}
"""


# ---------------------------------------------------------------------------
# Ollama tool schemas (matching the 16 MCP tools)
# ---------------------------------------------------------------------------

def build_tool_schemas() -> list[dict]:
    """Return Ollama-format tool definitions for all MCP tools."""
    return [
        _tool("parse_srw_native_script",
              "Parse an SRW-native Python script into simplified beamline JSON without loading.",
              {"script_path": {"type": "string", "description": "Path to the SRW-native Python script"}}),
        _tool("load_beamline",
              "Parse and load a beamline definition, cache source wavefront, return structured summary.",
              {"beamline_definition": {"type": "string", "description": "Path to beamline JSON/Python file, or inline JSON dict"}}),
        _tool("edit_beamline",
              "Make permanent corrections to the beamline definition (insert/remove/edit elements).",
              {"action": {"type": "string", "enum": ["insert", "remove", "edit"]},
               "target_label": {"type": "string", "description": "Element label to act on"},
               "insert_before": {"type": "string", "description": "For insert: place before this label"},
               "element_definition": {"type": "object", "description": "Element dict for insert/edit"}},
              required=["action"]),
        _tool("probe_aperture",
              "Temporarily insert or remove a diagnostic aperture.",
              {"action": {"type": "string", "enum": ["insert", "remove", "remove_all"]},
               "probe_id": {"type": "string"},
               "at_element": {"type": "string"},
               "aperture_params": {"type": "object"}},
              required=["action"]),
        _tool("truncate_drift",
              "Temporarily shorten a drift element to inspect beam at intermediate point.",
              {"drift_label": {"type": "string"}, "truncated_length_m": {"type": "number"}},
              required=["drift_label", "truncated_length_m"]),
        _tool("restore_drift",
              "Restore a previously truncated drift to its original length.",
              {"drift_label": {"type": "string"}},
              required=["drift_label"]),
        _tool("idealize_element",
              "Replace focusing elements with ideal thin-lens equivalents for validation.",
              {"element_labels": {"type": "array", "items": {"type": "string"}, "description": "Element labels to idealize, or the string 'all'"}},
              required=["element_labels"]),
        _tool("restore_elements",
              "Revert idealized elements back to their original definitions.",
              {"element_labels": {"type": "array", "items": {"type": "string"}}},
              required=["element_labels"]),
        _tool("get_beamline_state",
              "Return current beamline state: elements, params, probes, idealizations.",
              {}),
        _tool("set_propagation_params",
              "Set the 5 propagation parameters (mode, range_x/y, resolution_x/y) for elements. Mode 0=standard, 1=quadratic phase subtraction, 2=fixed grid, 3=from-waist far-field, 4=to-waist far-field.",
              {"params": {"type": "object", "description": "element_label -> {mode, range_x, range_y, resolution_x, resolution_y}"}},
              required=["params"]),
        _tool("run_propagation",
              "Run wavefront propagation through the beamline with current parameters. Returns per-element metrics.",
              {"up_to_element": {"type": "string", "description": "Stop after this element (null=full)"},
               "at_element": {"type": "string", "description": "Return intermediates only for this element"},
               "mesh_params": {"type": "object", "description": "Override source mesh"}}),
        _tool("run_convergence_test",
              "Run simulation at multiple scaling levels to check convergence.",
              {"element_label": {"type": "string"},
               "scaling_factors": {"type": "array", "items": {"type": "number"}},
               "axis": {"type": "string", "enum": ["x", "y", "both"]}}),
        _tool("preview_intensity",
              "Generate a 2D intensity map with H/V cuts at a beamline element. Returns a PNG image.",
              {"element_label": {"type": "string", "description": "Which element to preview"},
               "phase": {"type": "string", "enum": ["before", "after", "both"], "description": "Default: both"}},
              required=["element_label"]),
        _tool("compute_analytical_estimates",
              "Compute expected beam parameters using Gaussian beam / ABCD matrices.",
              {"at_element": {"type": "string", "description": "Compute at this element only (null=all)"}}),
        _tool("compare_to_estimates",
              "Compare simulation results against analytical estimates.",
              {"run_id": {"type": "string", "description": "Compare this run (null=latest)"}}),
        _tool("test_hypothesis",
              "Test parameter changes without permanently modifying active parameters.",
              {"hypothesis": {"type": "string"},
               "param_changes": {"type": "object"},
               "compare_to_run_id": {"type": "string"}},
              required=["hypothesis", "param_changes"]),
        _tool("get_report_data",
              "Return all structured data for composing a validity report.",
              {"include_history": {"type": "boolean"}}),
    ]


def _tool(name: str, description: str, properties: dict,
          required: list[str] | None = None) -> dict:
    """Build an Ollama tool schema entry."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema,
        },
    }


# ---------------------------------------------------------------------------
# Tool dispatch — calls domain functions directly
# ---------------------------------------------------------------------------

async def tool_dispatch(session: TuningSession, tool_name: str, args: dict) -> dict:
    """Execute a tool by calling the corresponding domain function.

    Returns the tool result as a JSON-serializable dict.
    """
    if tool_name == "parse_srw_native_script":
        from pathlib import Path
        from ..beamline.srw_script_parser import parse_srw_script
        return parse_srw_script(Path(args["script_path"]))

    elif tool_name == "load_beamline":
        from ..beamline.manager import load_beamline
        defn = args.get("beamline_definition", args.get("beamline_path", ""))
        return await load_beamline(session, defn)

    elif tool_name == "edit_beamline":
        from ..beamline.manager import edit_beamline
        return edit_beamline(
            session, args["action"],
            args.get("target_label", ""),
            args.get("insert_before"),
            args.get("element_definition"),
        )

    elif tool_name == "probe_aperture":
        from ..beamline.manager import probe_aperture
        return probe_aperture(
            session, args["action"],
            args.get("probe_id"),
            args.get("at_element"),
            args.get("aperture_params"),
        )

    elif tool_name == "truncate_drift":
        from ..beamline.manager import truncate_drift
        return truncate_drift(session, args["drift_label"], args["truncated_length_m"])

    elif tool_name == "restore_drift":
        from ..beamline.manager import restore_drift
        return restore_drift(session, args["drift_label"])

    elif tool_name == "idealize_element":
        from ..beamline.manager import idealize_elements
        return idealize_elements(session, args["element_labels"])

    elif tool_name == "restore_elements":
        from ..beamline.manager import restore_elements
        return restore_elements(session, args["element_labels"])

    elif tool_name == "get_beamline_state":
        from ..beamline.manager import get_beamline_state
        return get_beamline_state(session)

    elif tool_name == "set_propagation_params":
        from ..propagation_params import set_propagation_params
        return set_propagation_params(session, args["params"])

    elif tool_name == "run_propagation":
        from ..simulation.runner import run_propagation
        return await run_propagation(
            session,
            args.get("up_to_element"),
            args.get("at_element"),
            args.get("mesh_params"),
        )

    elif tool_name == "run_convergence_test":
        from ..simulation.convergence import run_convergence_test
        return await run_convergence_test(
            session,
            args.get("element_label"),
            args.get("scaling_factors"),
            args.get("axis", "both"),
        )

    elif tool_name == "preview_intensity":
        from ..simulation.runner import run_preview
        return await run_preview(
            session,
            args["element_label"],
            args.get("phase", "both"),
        )

    elif tool_name == "compute_analytical_estimates":
        from ..analysis.estimator import compute_analytical_estimates
        return compute_analytical_estimates(session, args.get("at_element"))

    elif tool_name == "compare_to_estimates":
        from ..analysis.comparison import compare_to_estimates
        return compare_to_estimates(session, args.get("run_id"))

    elif tool_name == "test_hypothesis":
        from ..analysis.hypothesis import test_hypothesis
        return await test_hypothesis(
            session,
            args["hypothesis"],
            args["param_changes"],
            args.get("compare_to_run_id"),
        )

    elif tool_name == "get_report_data":
        from ..report import get_report_data
        return get_report_data(session, args.get("include_history", False))

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# WebSocket message helpers
# ---------------------------------------------------------------------------

async def _ws_send(ws, msg: dict) -> None:
    """Send a JSON message over WebSocket, silently ignoring errors."""
    try:
        await ws.send_json(msg)
    except Exception:
        pass


def _safe_json(obj: Any) -> Any:
    """Make an object JSON-serializable (convert numpy, bytes, etc.)."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("ascii")
    elif isinstance(obj, float) and (obj != obj or obj == float('inf') or obj == float('-inf')):
        return str(obj)
    else:
        return obj


def _truncate_result(result: dict, max_len: int = 4000) -> dict:
    """Truncate large result dicts for display in the agent log."""
    text = json.dumps(result, default=str)
    if len(text) <= max_len:
        return result
    return {"_truncated": True, "_preview": text[:max_len] + "..."}


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

async def run_agent_loop(
    session: TuningSession,
    ws: Any,
    beamline_input: str,
    user_message: str,
    model: str,
    ollama_base_url: str = "http://localhost:11434",
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run the Ollama agent loop, streaming events to the WebSocket.

    Args:
        session: TuningSession instance
        ws: WebSocket connection (FastAPI)
        beamline_input: Path to beamline file or inline JSON
        user_message: User's instruction/question
        model: Ollama model name
        ollama_base_url: Ollama API base URL
        stop_event: Set this to stop the loop early
    """
    system_prompt = _build_system_prompt()
    tool_schemas = build_tool_schemas()

    # Build initial user message
    if beamline_input:
        full_user_msg = f"Please tune the beamline defined in: {beamline_input}\n\n{user_message}" if user_message else f"Please tune the beamline defined in: {beamline_input}"
    else:
        full_user_msg = user_message or "Please describe what you'd like to do with the beamline."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_user_msg},
    ]

    await _ws_send(ws, {"type": "status", "message": f"Starting agent with model {model}..."})

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
        for iteration in range(MAX_ITERATIONS):
            if stop_event and stop_event.is_set():
                await _ws_send(ws, {"type": "status", "message": "Stopped by user"})
                break

            await _ws_send(ws, {"type": "status", "message": f"Iteration {iteration + 1}/{MAX_ITERATIONS}"})

            # Call Ollama
            try:
                response_data = await _call_ollama(
                    client, ollama_base_url, model, messages, tool_schemas, ws
                )
            except httpx.ConnectError:
                await _ws_send(ws, {"type": "error", "message": f"Cannot connect to Ollama at {ollama_base_url}. Is Ollama running?"})
                break
            except Exception as e:
                await _ws_send(ws, {"type": "error", "message": f"Ollama error: {e}"})
                break

            if response_data is None:
                await _ws_send(ws, {"type": "error", "message": "Empty response from Ollama"})
                break

            assistant_message = response_data.get("message", {})
            content = assistant_message.get("content", "")
            tool_calls = assistant_message.get("tool_calls", [])

            # Stream any text content
            if content:
                await _ws_send(ws, {"type": "thinking", "content": content})

            # Add assistant message to history
            messages.append(assistant_message)

            # If no tool calls, agent is done
            if not tool_calls:
                await _ws_send(ws, {"type": "status", "message": "Agent finished reasoning"})
                break

            # Execute tool calls
            for tc in tool_calls:
                if stop_event and stop_event.is_set():
                    break

                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                tool_args = func.get("arguments", {})

                # Send tool_call event
                await _ws_send(ws, {
                    "type": "tool_call",
                    "tool": tool_name,
                    "args": _safe_json(tool_args),
                })

                # Execute the tool
                try:
                    result = await tool_dispatch(session, tool_name, tool_args)
                    result = _safe_json(result)
                except Exception as e:
                    logger.exception(f"Tool {tool_name} failed")
                    result = {"error": str(e), "traceback": traceback.format_exc()}

                # Send tool_result event
                await _ws_send(ws, {
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": _truncate_result(result),
                })

                # Send specialized updates based on tool type
                await _send_state_updates(ws, session, tool_name, result)

                # Add tool result to messages for the LLM
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, default=str),
                })

    await _ws_send(ws, {"type": "done"})


async def _call_ollama(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    ws: Any,
) -> dict | None:
    """Call Ollama chat API with streaming.

    Streams text content tokens to the WebSocket as they arrive.
    Returns the complete response message.
    """
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": True,
    }

    full_content = ""
    tool_calls = []
    done_response = None

    async with client.stream(
        "POST",
        f"{base_url}/api/chat",
        json=payload,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = chunk.get("message", {})

            # Stream text content
            content_piece = msg.get("content", "")
            if content_piece:
                full_content += content_piece
                await _ws_send(ws, {"type": "token", "content": content_piece})

            # Collect tool calls
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])

            if chunk.get("done"):
                done_response = chunk

    # Build the complete assistant message
    assistant_msg: dict[str, Any] = {"role": "assistant"}
    if full_content:
        assistant_msg["content"] = full_content
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls

    return {"message": assistant_msg, "done_response": done_response}


# ---------------------------------------------------------------------------
# State update helpers
# ---------------------------------------------------------------------------

async def _send_state_updates(
    ws: Any,
    session: TuningSession,
    tool_name: str,
    result: dict,
) -> None:
    """Send beamline/intensity/metrics updates after tool execution."""

    # After load_beamline or edit_beamline: send beamline update
    if tool_name in ("load_beamline", "edit_beamline", "probe_aperture",
                     "truncate_drift", "restore_drift", "idealize_element",
                     "restore_elements"):
        elements = result.get("elements") or result.get("updated_elements", [])
        source = {}
        if tool_name == "load_beamline":
            source = {
                "source_type": result.get("source_type", ""),
                "photon_energy_eV": result.get("photon_energy_eV", 0),
                "source_mesh": result.get("source_mesh", {}),
                "total_length_m": result.get("total_length_m", 0),
            }
        await _ws_send(ws, {
            "type": "beamline_update",
            "elements": elements,
            "source": source,
        })

    # After run_propagation: send metrics update
    elif tool_name == "run_propagation":
        if "error" not in result:
            await _ws_send(ws, {
                "type": "metrics_update",
                "intermediates": result.get("intermediates", []),
                "final": result.get("final", {}),
                "run_id": result.get("run_id", ""),
                "wall_time_s": result.get("wall_time_s", 0),
            })

    # After preview_intensity: send intensity image
    elif tool_name == "preview_intensity":
        if "image_base64" in result:
            await _ws_send(ws, {
                "type": "intensity_update",
                "element_label": result.get("element_label", ""),
                "image_base64": result["image_base64"],
                "phase": result.get("phase", "both"),
            })

    # After convergence test: send convergence data
    elif tool_name == "run_convergence_test":
        await _ws_send(ws, {
            "type": "convergence_update",
            "results": result.get("results", []),
            "parameter_scaled": result.get("parameter_scaled", ""),
        })

    # After analytical estimates: send estimates
    elif tool_name == "compute_analytical_estimates":
        await _ws_send(ws, {
            "type": "estimates_update",
            "estimates": result.get("estimates", []),
        })
