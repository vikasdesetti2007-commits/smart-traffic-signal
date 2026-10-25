"""FastAPI application for Smart Traffic Signal Controller & Simulation."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.controller import IntersectionController
from app.schemas import (
    AmbulanceRequest,
    HealthResponse,
    IntersectionStateResponse,
    PedestrianRequest,
    SimulationControlRequest,
    StandardResponse,
    TrafficDensityRequest,
    VehicleTelemetryRequest,
)

# Global singleton controller instance
controller = IntersectionController()

# Background ticker task handle
_ticker_task: Optional[asyncio.Task] = None


async def background_simulation_ticker():
    """Background task advancing the controller simulation clock every 500ms."""
    while True:
        try:
            if controller.simulation_running:
                controller.tick(delta=0.5)
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            # Prevent background loop crash
            print(f"[Simulation Ticker Error] {e}")
            await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to manage background simulation clock."""
    global _ticker_task
    _ticker_task = asyncio.create_task(background_simulation_ticker())
    yield
    if _ticker_task:
        _ticker_task.cancel()
        try:
            await _ticker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Smart Traffic Signal API",
    description="Deterministic multi-phase traffic signal controller with emergency preemption and formal logic evaluation.",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    """Enforce strict no-cache headers across all API endpoints, static assets, and HTML."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Static file paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check API server health and simulation status."""
    return HealthResponse(
        status="healthy",
        service="Smart Traffic Signal Controller",
        version=__version__,
        simulation_running=controller.simulation_running,
        timestamp=datetime.now().isoformat(),
    )


@app.get("/api/state", response_model=IntersectionStateResponse)
async def get_state():
    """Retrieve full intersection snapshot: signal aspects, phase, logic evaluation, and truth table."""
    return controller.get_state()


@app.post("/api/control/ambulance", response_model=StandardResponse)
async def control_ambulance(payload: AmbulanceRequest):
    """Trigger emergency vehicle preemption from specified approach."""
    try:
        msg = controller.request_ambulance(
            approach=payload.approach.value,
            route=payload.route,
            active=payload.active,
            caller=payload.caller,
            reason=payload.reason,
        )
        return StandardResponse(
            success=True,
            message=msg,
            state=controller.get_state(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process ambulance request: {str(e)}",
        )


@app.post("/api/control/pedestrian", response_model=StandardResponse)
async def control_pedestrian(payload: PedestrianRequest):
    """Request pedestrian crosswalk walk phase."""
    try:
        msg = controller.request_pedestrian(
            active=payload.active,
            crosswalk=payload.crosswalk,
        )
        return StandardResponse(
            success=True,
            message=msg,
            state=controller.get_state(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process pedestrian request: {str(e)}",
        )


@app.post("/api/control/simulation", response_model=StandardResponse)
async def control_simulation(payload: SimulationControlRequest):
    """Control simulation state: start, pause, reset, or step."""
    try:
        msg = controller.set_simulation_state(payload.action.value)
        return StandardResponse(
            success=True,
            message=msg,
            state=controller.get_state(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set simulation state: {str(e)}",
        )


@app.post("/api/control/traffic", response_model=StandardResponse)
async def control_traffic(payload: TrafficDensityRequest):
    """Set traffic density level (low, medium, high), optionally for a specific approach."""
    try:
        approach_val = payload.approach.value if payload.approach else None
        msg = controller.set_traffic_density(payload.density, approach=approach_val)
        return StandardResponse(
            success=True,
            message=msg,
            state=controller.get_state(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set traffic density: {str(e)}",
        )


@app.post("/api/telemetry/vehicles", response_model=StandardResponse)
async def sync_vehicle_telemetry(payload: VehicleTelemetryRequest):
    """Synchronize live client-side vehicle counts per approach with controller."""
    try:
        if payload.counts:
            controller.traffic_generator.sync_from_frontend_counts(payload.counts)
        elif payload.approaches:
            controller.traffic_generator.sync_client_counts(payload.approaches)
        return StandardResponse(
            success=True,
            message="Vehicle telemetry synchronized.",
            state=controller.get_state(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synchronize vehicle telemetry: {str(e)}",
        )


# Mount static assets directory
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.api_route("/", methods=["GET", "HEAD"])
async def serve_index():
    """Serve the main frontend application dashboard."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Smart Traffic Signal API is active. Static files not yet generated."}
