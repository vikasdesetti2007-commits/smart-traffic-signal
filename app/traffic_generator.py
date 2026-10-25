"""Modular Dynamic Traffic Demand Generator for Smart Traffic Signal.

Simulates and manages dynamic traffic demands, arrival rates, queue accumulation,
and queue discharge across all four approaches (North, South, East, West).

Key Requirements:
- At least one approach exhibits HIGH traffic density during normal simulation.
- The high-density approach dynamically rotates/shifts across directions over time
  (e.g., South -> East -> North -> West).
- Other approaches experience LOW and MEDIUM traffic density.
- Density classifications (LOW, MEDIUM, HIGH) directly correspond to actual
  measured vehicle counts and queue lengths.
- Fully decoupled from the signal controller state machine for modularity and testing.
"""

from typing import Dict, List, Optional
from app.schemas import DirectionEnum, TrafficDensityEnum, ApproachMetrics, SignalColor


class TrafficDemandGenerator:
    """Deterministic and testable traffic demand and queue simulation generator."""

    def __init__(
        self,
        rotation_interval: float = 30.0,
        initial_high_demand: str = "south",
    ):
        # High-demand sequence order: South -> East -> North -> West -> South
        self.rotation_sequence: List[str] = ["south", "east", "north", "west"]
        self.rotation_interval: float = rotation_interval
        self.time_in_current_demand: float = 0.0

        # Current high demand index
        if initial_high_demand.lower() in self.rotation_sequence:
            self.current_high_index = self.rotation_sequence.index(initial_high_demand.lower())
        else:
            self.current_high_index = 0

        # State per approach:
        # vehicle_count: active vehicles approaching or near stop line
        # queue_length: vehicles stopped in queue at stop line
        # discharge_accumulator: fractional time for queue clearance
        self.queues: Dict[str, float] = {
            "north": 1.0,
            "south": 6.0,  # Starts with high density (>= 5)
            "east": 3.0,   # Medium
            "west": 1.0,   # Low
        }
        self.vehicle_counts: Dict[str, int] = {
            "north": 2,
            "south": 7,
            "east": 4,
            "west": 2,
        }
        self.lane_queues: Dict[str, Dict[str, int]] = {
            "north": {"lane1": 1, "lane2": 0},
            "south": {"lane1": 3, "lane2": 3},
            "east": {"lane1": 2, "lane2": 1},
            "west": {"lane1": 1, "lane2": 0},
        }
        self.discharge_accumulators: Dict[str, float] = {d: 0.0 for d in self.rotation_sequence}
        self.arrival_accumulators: Dict[str, float] = {d: 0.0 for d in self.rotation_sequence}

        # Global demand multiplier
        self.global_density_setting: TrafficDensityEnum = TrafficDensityEnum.MEDIUM

    @property
    def current_high_demand_approach(self) -> str:
        """Return the direction currently assigned HIGH demand focus."""
        return self.rotation_sequence[self.current_high_index]

    def set_high_demand_approach(self, approach: str) -> None:
        """Programmatically set the high-demand focus approach (for tests and scenarios)."""
        app_norm = approach.lower()
        if app_norm in self.rotation_sequence:
            self.current_high_index = self.rotation_sequence.index(app_norm)
            self.time_in_current_demand = 0.0
            # Ensure the targeted approach immediately has a significant queue
            self.queues[app_norm] = max(self.queues[app_norm], 6.0)
            self.vehicle_counts[app_norm] = max(self.vehicle_counts[app_norm], 7)

    def set_approach_density(self, approach: str, density: TrafficDensityEnum) -> None:
        """Set traffic density explicitly for an approach."""
        app_norm = approach.lower()
        if app_norm not in self.queues:
            return
        if density == TrafficDensityEnum.HIGH:
            self.set_high_demand_approach(app_norm)
            self.queues[app_norm] = max(self.queues[app_norm], 6.0)
            self.vehicle_counts[app_norm] = max(self.vehicle_counts[app_norm], 8)
        elif density == TrafficDensityEnum.MEDIUM:
            self.queues[app_norm] = 3.0
            self.vehicle_counts[app_norm] = 4
        else:
            self.queues[app_norm] = 1.0
            self.vehicle_counts[app_norm] = 2

    def set_approach_queue(self, approach: str, queue_length: int, vehicle_count: Optional[int] = None) -> None:
        """Explicitly set queue and vehicle count for an approach (testing & telemetry injection)."""
        app_norm = approach.lower()
        if app_norm in self.queues:
            self.queues[app_norm] = float(queue_length)
            self.vehicle_counts[app_norm] = vehicle_count if vehicle_count is not None else max(queue_length, queue_length + 1)
            l1 = int(round(queue_length / 2.0))
            l2 = int(queue_length - l1)
            self.lane_queues[app_norm] = {"lane1": l1, "lane2": l2}

    def sync_client_counts(self, counts: Dict[str, int]) -> None:
        """Synchronize approach queue counts from client-side visual simulation or telemetry."""
        for app, count in counts.items():
            app_norm = app.lower()
            if app_norm in self.queues:
                self.set_approach_queue(app_norm, queue_length=count, vehicle_count=max(count, count + 1))

    def classify_density(self, queue: float, count: int) -> TrafficDensityEnum:
        """Classify traffic density based on measured queue length and vehicle count.
        
        LOW: 0 - 2 vehicles queued
        MEDIUM: 3 - 4 vehicles queued
        HIGH: 5+ vehicles queued
        """
        effective = max(queue, count * 0.75)
        if effective >= 5.0:
            return TrafficDensityEnum.HIGH
        elif effective >= 3.0:
            return TrafficDensityEnum.MEDIUM
        return TrafficDensityEnum.LOW

    def update(self, delta: float, active_green_approach: Optional[str] = None) -> None:
        """Advance traffic generation by delta seconds."""
        self.time_in_current_demand += delta

        # Rotate high-demand direction periodically
        if self.time_in_current_demand >= self.rotation_interval:
            self.time_in_current_demand = 0.0
            self.current_high_index = (self.current_high_index + 1) % len(self.rotation_sequence)
            new_high = self.current_high_demand_approach
            # Boost arrivals for the new high-demand approach
            self.queues[new_high] = max(self.queues[new_high], 5.0)
            self.vehicle_counts[new_high] = max(self.vehicle_counts[new_high], 6)

        high_app = self.current_high_demand_approach

        for approach in self.rotation_sequence:
            is_green = (active_green_approach is not None and approach == active_green_approach.lower())

            # 1. Vehicle Arrivals (Adding to queue if not moving freely)
            # Base arrival intervals:
            # High-demand direction: 1 vehicle every ~2.5s
            # Medium: 1 vehicle every ~5.0s
            # Low: 1 vehicle every ~9.0s
            if approach == high_app:
                arrival_interval = 2.4
                target_max_queue = 8.0
            else:
                # Other approaches alternate between low and medium
                idx_diff = (self.rotation_sequence.index(approach) - self.current_high_index) % len(self.rotation_sequence)
                if idx_diff == 1:
                    arrival_interval = 4.5  # Medium
                    target_max_queue = 4.0
                else:
                    arrival_interval = 8.0  # Low
                    target_max_queue = 2.0

            # Scale by global density setting if operator overrode
            if self.global_density_setting == TrafficDensityEnum.HIGH:
                arrival_interval *= 0.75
                target_max_queue += 2.0
            elif self.global_density_setting == TrafficDensityEnum.LOW:
                arrival_interval *= 1.5
                target_max_queue = max(1.0, target_max_queue - 1.0)

            self.arrival_accumulators[approach] += delta
            if self.arrival_accumulators[approach] >= arrival_interval:
                self.arrival_accumulators[approach] -= arrival_interval
                if self.queues[approach] < target_max_queue:
                    self.queues[approach] = min(target_max_queue, self.queues[approach] + 1.0)
                self.vehicle_counts[approach] = int(self.queues[approach] + 1)

            # 2. Queue Discharge during GREEN phase
            if is_green:
                # Saturation flow rate: ~1 vehicle discharges every 1.6 seconds of green
                discharge_rate = 1.6
                self.discharge_accumulators[approach] += delta
                if self.discharge_accumulators[approach] >= discharge_rate:
                    discharged = int(self.discharge_accumulators[approach] // discharge_rate)
                    self.discharge_accumulators[approach] %= discharge_rate
                    self.queues[approach] = max(0.0, self.queues[approach] - discharged)
                    self.vehicle_counts[approach] = max(0, int(self.queues[approach]))
            else:
                self.discharge_accumulators[approach] = 0.0

    def get_metrics(
        self,
        approach: str,
        signal_color: SignalColor = SignalColor.RED,
        countdown: float = 0.0,
        is_active: bool = False,
        green_extended: bool = False,
    ) -> ApproachMetrics:
        """Construct ApproachMetrics for a given approach."""
        app_norm = approach.lower()
        q = int(round(self.queues.get(app_norm, 0.0)))
        vc = self.vehicle_counts.get(app_norm, q)
        density = self.classify_density(self.queues.get(app_norm, 0.0), vc)

        l_queues = self.lane_queues.get(app_norm)
        if not l_queues:
            l1 = int(round(q / 2.0))
            l2 = int(q - l1)
            l_queues = {"lane1": l1, "lane2": l2}

        return ApproachMetrics(
            approach=app_norm,
            density=density,
            vehicle_count=vc,
            queue_length=q,
            signal_color=signal_color,
            countdown=round(max(0.0, countdown), 1),
            is_active=is_active,
            green_extended=green_extended,
            lane_queues=l_queues,
        )

    def sync_from_frontend_counts(self, counts: Dict[str, Dict[str, int]]) -> None:
        """Incorporate client-observed 3D vehicle counts and per-lane queues."""
        for app, data in counts.items():
            app_norm = app.lower()
            if app_norm in self.queues:
                if "queue" in data:
                    self.queues[app_norm] = float(data["queue"])
                if "total" in data:
                    self.vehicle_counts[app_norm] = int(data["total"])

                # Support either {lane0, lane1} or {lane1, lane2}
                if "lane0" in data and "lane1" in data:
                    l1 = int(data["lane0"])
                    l2 = int(data["lane1"])
                elif "lane1" in data and "lane2" in data:
                    l1 = int(data["lane1"])
                    l2 = int(data["lane2"])
                else:
                    l1 = int(round(self.queues[app_norm] / 2.0))
                    l2 = int(self.queues[app_norm] - l1)
                self.lane_queues[app_norm] = {"lane1": l1, "lane2": l2}
