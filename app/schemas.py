"""Data schemas and request/response models for the Smart Traffic Signal API."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DirectionEnum(str, Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class TrafficDensityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalColor(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class PedestrianSignal(str, Enum):
    DONT_WALK = "DONT_WALK"
    WALK = "WALK"
    FLASHING_DONT_WALK = "FLASHING_DONT_WALK"


class SimulationAction(str, Enum):
    START = "start"
    PAUSE = "pause"
    RESET = "reset"
    STEP = "step"


class AmbulanceRequest(BaseModel):
    approach: DirectionEnum = Field(
        default=DirectionEnum.SOUTH,
        description="Approach direction from which the ambulance is arriving"
    )
    route: str = Field(
        default="straight",
        description="Ambulance movement route: straight, left, or right"
    )
    active: bool = Field(
        default=True,
        description="True to dispatch or keep active, False to clear emergency"
    )
    caller: Optional[str] = Field(
        default="api",
        description="Component or caller initiating or clearing the emergency state"
    )
    reason: Optional[str] = Field(
        default="operator_dispatch",
        description="Reason for activating or deactivating emergency priority"
    )


class PedestrianRequest(BaseModel):
    active: bool = Field(
        default=True,
        description="True to request crossing, False to cancel"
    )
    crosswalk: str = Field(
        default="all",
        description="Crosswalk identifier or 'all'"
    )


class SimulationControlRequest(BaseModel):
    action: SimulationAction = Field(
        ...,
        description="Simulation command: start, pause, reset, or step"
    )


class TrafficDensityRequest(BaseModel):
    density: TrafficDensityEnum = Field(
        ...,
        description="Traffic density level: low, medium, or high"
    )
    approach: Optional[DirectionEnum] = Field(
        default=None,
        description="Optional approach to set density for, or None for all"
    )


class VehicleTelemetryRequest(BaseModel):
    approaches: Optional[Dict[str, int]] = Field(
        default=None,
        description="Observed vehicle queues per approach: { approach: queue_count }"
    )
    counts: Optional[Dict[str, Dict[str, int]]] = Field(
        default=None,
        description="Observed vehicle counts per approach: { approach: { queue: int, total: int } }"
    )


class ApproachMetrics(BaseModel):
    approach: str
    density: TrafficDensityEnum
    vehicle_count: int
    queue_length: int
    signal_color: SignalColor
    countdown: float
    is_active: bool
    green_extended: bool
    lane_queues: Dict[str, int] = Field(default_factory=dict)


class SignalState(BaseModel):
    vehicle: SignalColor
    pedestrian: PedestrianSignal


class TruthTableRow(BaseModel):
    row_id: int
    p: bool
    q: bool
    r: bool
    p_or_q: bool
    not_r: bool
    g: bool
    description: str
    safety_context: str


class LogicEvaluation(BaseModel):
    p: bool
    q: bool
    r: bool
    g: bool
    p_or_q: bool
    not_r: bool
    active_row: int
    formula: str
    description: str
    safety_note: str


class LogEvent(BaseModel):
    id: str
    timestamp: str
    level: str  # "INFO", "WARN", "EMERGENCY", "PEDESTRIAN"
    message: str


class IntersectionStateResponse(BaseModel):
    phase: str
    phase_display: str
    time_in_phase: float
    phase_duration: float
    signals: Dict[str, SignalState]
    active_approach: Optional[str] = "north"
    green_extended: bool = False
    current_high_demand_approach: str = "south"
    approach_metrics: Dict[str, ApproachMetrics] = Field(default_factory=dict)
    countdowns: Dict[str, float] = Field(default_factory=dict)
    min_green_duration: float = 6.0
    base_green_duration: float = 8.0
    extension_per_vehicle: float = 1.5
    normal_green_duration: float = 12.0
    max_green_duration: float = 22.0
    emergency_active: bool
    emergency_approach: Optional[str]
    emergency_route: Optional[str] = "straight"
    pedestrian_active: bool
    pedestrian_remaining: float
    pedestrian_crosswalk: str = "all"
    traffic_density: TrafficDensityEnum
    simulation_running: bool
    logic: LogicEvaluation
    truth_table: List[TruthTableRow]
    recent_events: List[LogEvent]
    server_time: str


class StandardResponse(BaseModel):
    success: bool
    message: str
    state: Optional[IntersectionStateResponse] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    simulation_running: bool
    timestamp: str
