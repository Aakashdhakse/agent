"""
Meta Agent CX — FastAPI Application

A Meta Agent system that creates and configures CX (Customer Experience)
phone agents through natural language. Non-technical users describe what
they need, and the system generates a complete, deployable agent config.

Endpoints:
  POST /api/create-agent     — Create a new CX agent from natural language
  GET  /api/health           — Health check
  GET  /api/example          — Returns a pre-built example
  GET  /                     — Serves the web UI
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from meta_agent.models import (
    AgentCreateRequest,
    AgentCreateResponse,
    HealthResponse,
)
from meta_agent.orchestrator import MetaOrchestrator

load_dotenv()

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)
logger = logging.getLogger("meta_agent_cx")

# ── Orchestrator (singleton) ──
orchestrator: MetaOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the orchestrator on startup."""
    global orchestrator
    api_key = os.getenv("OPENAI_API_KEY")
    orchestrator = MetaOrchestrator(openai_api_key=api_key)
    mode = "LLM-powered (GPT-4o)" if api_key else "Rule-based (no API key)"
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   Meta Agent CX — Ready!                    ║")
    logger.info("║   Mode: %-36s ║", mode)
    logger.info("╚══════════════════════════════════════════════╝")
    yield
    logger.info("Shutting down Meta Agent CX...")


# ── FastAPI App ──
app = FastAPI(
    title="Meta Agent CX",
    description=(
        "A Meta Agent that creates and configures CX phone agents "
        "through natural language descriptions."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files ──
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━ ROUTES ━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the web UI."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Meta Agent CX</h1><p>Static files not found.</p>")


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/api/create-agent", response_model=AgentCreateResponse)
async def create_agent(request: AgentCreateRequest):
    """
    Create a new CX phone agent from a natural language description.

    The Meta Agent will:
    1. Analyze the request to understand requirements
    2. Generate persona, voice, and intent configurations
    3. Define function calls with API endpoint mappings
    4. Build a conversation flow graph
    5. Return the complete agent configuration
    """
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    logger.info("Received agent creation request: %s", request.user_prompt[:80])
    result = await orchestrator.process_request(request)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return result


@app.get("/api/example")
async def get_example():
    """
    Returns a pre-built example showing the full input → output flow.
    Useful for understanding the system without making a real request.
    """
    example_request = AgentCreateRequest(
        user_prompt=(
            "Create a support bot for appointment booking. It should greet, "
            "ask for name and date, and confirm availability via an API."
        ),
        language="en-US",
        platform="voiceowl",
    )

    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    result = await orchestrator.process_request(example_request)
    return {
        "input": {
            "user_prompt": example_request.user_prompt,
            "language": example_request.language,
            "platform": example_request.platform,
        },
        "output": result.model_dump(),
    }


# ── Run ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
