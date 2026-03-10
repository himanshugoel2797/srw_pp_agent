"""FastAPI dashboard server: serves the visualization UI and WebSocket endpoint.

Provides a browser-based interface for interacting with the SRW beamline
tuning agent. The frontend connects via WebSocket to stream agent activity
and beamline visualization updates in real-time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..session import TuningSession
from .agent_loop import run_agent_loop

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="SRW Beamline Tuning Dashboard")

# Global config (set by main())
_config = {
    "model": os.environ.get("OLLAMA_MODEL", "qwen2.5"),
    "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the dashboard HTML."""
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text())


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Handle WebSocket connections from the dashboard frontend.

    Protocol:
        Client sends: {"type": "start", "beamline_path": "...", "user_message": "...", "model": "..."}
                   or {"type": "stop"}
        Server sends: streamed events (thinking, tool_call, tool_result, beamline_update, etc.)
    """
    await ws.accept()

    session = TuningSession()
    stop_event = asyncio.Event()
    agent_task: asyncio.Task | None = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "start":
                # Cancel any running agent
                if agent_task and not agent_task.done():
                    stop_event.set()
                    try:
                        await asyncio.wait_for(agent_task, timeout=5.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        agent_task.cancel()

                # Reset for new run
                session = TuningSession()
                stop_event = asyncio.Event()

                beamline_path = msg.get("beamline_path", "")
                user_message = msg.get("user_message", "")
                model = msg.get("model", _config["model"])

                agent_task = asyncio.create_task(
                    run_agent_loop(
                        session=session,
                        ws=ws,
                        beamline_input=beamline_path,
                        user_message=user_message,
                        model=model,
                        ollama_base_url=_config["ollama_base_url"],
                        stop_event=stop_event,
                    )
                )

            elif msg_type == "stop":
                stop_event.set()
                await ws.send_json({"type": "status", "message": "Stop requested"})

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if agent_task and not agent_task.done():
            stop_event.set()
            agent_task.cancel()
    except Exception as e:
        logger.exception("WebSocket error")
        if agent_task and not agent_task.done():
            stop_event.set()
            agent_task.cancel()


def main():
    """CLI entry point for the dashboard server."""
    parser = argparse.ArgumentParser(description="SRW Beamline Tuning Dashboard")
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "qwen2.5"),
                        help="Ollama model name (default: qwen2.5, env: OLLAMA_MODEL)")
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                        help="Ollama API base URL (env: OLLAMA_BASE_URL)")
    parser.add_argument("--host", default="0.0.0.0", help="Dashboard host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8050, help="Dashboard port (default: 8050)")
    args = parser.parse_args()

    _config["model"] = args.model
    _config["ollama_base_url"] = args.ollama_url

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
