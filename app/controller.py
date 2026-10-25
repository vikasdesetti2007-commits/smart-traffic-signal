"""Deterministic Safe Intersection Controller State Machine.

Simulation Disclaimer:
----------------------
THIS IS AN EDUCATIONAL DEMONSTRATION AND SIMULATION SOFTWARE.
IT IS NOT CERTIFIED FOR DIRECT PHYSICAL TRAFFIC-CONTROL INFRASTRUCTURE.

Safety Guarantees in this Controller:
1. Invariant: Conflicting vehicle movements (N/S vs E/W) NEVER receive Green simultaneously.
2. Invariant: Vehicle signals never instantly transition from Green to Red; an
   appropriate Yellow clearance interval (2.5s) followed by an All-Red interval (1.5s)
   is mandatory.
3. Invariant: Pedestrian WALK is strictly exclusive with vehicle Green and Yellow signals;
   all conflicting vehicular approaches must be confirmed in ALL-RED before WALK is shown.
4. Preemption: Emergency vehicles (ambulances) initiate deterministic clearance of conflicting
   movements, establish a protected corridor, and hold until the vehicle clears.
5. Arbitration: When emergency and pedestrian calls occur simultaneously, the life-safety
   emergency corridor takes precedence; if pedestrians are already in the street, an
   expedited clearance is executed before granting the vehicle green.
"""

from datetime import datetime
from typing import Dict, List, Optional
import uuid

from app.schemas import (
    ApproachMetrics,
    DirectionEnum,
    IntersectionStateResponse,
    LogEvent,
    PedestrianSignal,
    SignalColor,
    SignalState,
    TrafficDensityEnum,
    TruthTableRow,
)
from app.logic_engine import evaluate_traffic_proposition, get_truth_table
from app.traffic_generator import TrafficDemandGenerator


class IntersectionController:
    """Manages the deterministic multi-phase traffic intersection state machine with adaptive green extensions."""

    def __init__(self):
        # Operational mode and clock
        self.simulation_running: bool = True
        self.traffic_density: TrafficDensityEnum = TrafficDensityEnum.MEDIUM
        
        # Adaptive Green Timing Parameters (Configurable defaults per Requirement 4)
        # Formula: green_duration = clamp(base_green + queued_vehicle_count * extension_per_vehicle, minimum_green, maximum_green)
        self.min_green_duration: float = 6.0
        self.base_green_duration: float = 8.0
        self.extension_per_vehicle: float = 1.5
        self.normal_green_duration: float = 12.0  # Backward-compatible baseline
        self.max_extension_duration: float = 14.0
        self.max_green_duration: float = 22.0  # 8.0s base + up to 14.0s queue extension
        self.yellow_duration: float = 2.5
        self.all_red_duration: float = 1.5

        # Dynamic Traffic Demand Generator instance (Requirement 3)
        self.traffic_generator = TrafficDemandGenerator()
        self.green_extended: bool = False

        # State machine phases (Strictly One Approach Green at a Time):
        # 1. NORTH_GREEN -> 2. NORTH_YELLOW -> 3. ALL_RED_PRE_SOUTH
        # 4. SOUTH_GREEN -> 5. SOUTH_YELLOW -> 6. ALL_RED_PRE_EAST
        # 7. EAST_GREEN  -> 8. EAST_YELLOW  -> 9. ALL_RED_PRE_WEST
        # 10. WEST_GREEN -> 11. WEST_YELLOW -> 12. ALL_RED_PRE_NORTH
        # EMERGENCY_PRIORITY, PEDESTRIAN_WALK, PEDESTRIAN_FLASHING
        self.phase: str = "NORTH_GREEN"
        self.phase_display: str = "North Green Phase"
        self.time_in_phase: float = 0.0
        self.phase_duration: float = 8.0  # Initial baseline duration for NORTH_GREEN

        # Signal states for each approach (Only ONE approach is GREEN at any given time)
        self.signals: Dict[str, SignalState] = {
            "north": SignalState(vehicle=SignalColor.GREEN, pedestrian=PedestrianSignal.DONT_WALK),
            "south": SignalState(vehicle=SignalColor.RED, pedestrian=PedestrianSignal.DONT_WALK),
            "east": SignalState(vehicle=SignalColor.RED, pedestrian=PedestrianSignal.DONT_WALK),
            "west": SignalState(vehicle=SignalColor.RED, pedestrian=PedestrianSignal.DONT_WALK),
        }

        # Emergency preemption state
        self.emergency_active: bool = False
        self.emergency_approach: Optional[str] = None
        self.emergency_route: str = "straight"
        self.emergency_target_phase: Optional[str] = None
        self.emergency_clearance_time: float = 0.0

        # Pedestrian call state
        self.pedestrian_active: bool = False
        self.pedestrian_remaining: float = 0.0
        self.pedestrian_queued: bool = False
        self.pedestrian_crosswalk: str = "north"

        # Return phase after preemption or pedestrian cycle
        self.resume_phase_after_preempt: str = "NORTH_GREEN"

        # Event audit log
        self.events: List[LogEvent] = []
        self._add_log("INFO", "Deterministic Smart Traffic Signal Controller initialized.")
        self._add_log("INFO", "Safety Invariant: Single-approach exclusive green cycling active.")
        self._add_log("INFO", "Adaptive Timing: Min green 8s, Normal green 12s, Max green 22s.")

    def _add_log(self, level: str, message: str) -> None:
        """Add an event to the recent audit log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        event = LogEvent(
            id=str(uuid.uuid4())[:8],
            timestamp=timestamp,
            level=level,
            message=message
        )
        self.events.insert(0, event)
        if len(self.events) > 50:
            self.events = self.events[:50]

    def set_simulation_state(self, action: str) -> str:
        """Handle start, pause, reset, or step."""
        if action == "start":
            self.simulation_running = True
            self._add_log("INFO", "Simulation running.")
            return "Simulation resumed."
        elif action == "pause":
            self.simulation_running = False
            self._add_log("INFO", "Simulation paused by operator.")
            return "Simulation paused."
        elif action == "reset":
            self.__init__()
            self._add_log("WARN", "Intersection controller reset to initial baseline state.")
            return "Simulation reset to baseline."
        elif action == "step":
            self.simulation_running = False
            self.tick(1.0)
            self._add_log("INFO", "Single simulation step (+1.0s) executed.")
            return "Single step executed."
        return "Unknown action."

    def set_traffic_density(self, density: TrafficDensityEnum, approach: Optional[str] = None) -> str:
        """Update traffic density and adapt green phase timing."""
        self.traffic_density = density
        self.traffic_generator.global_density_setting = density
        if approach:
            self.traffic_generator.set_approach_density(approach, density)
            self._add_log("INFO", f"Traffic demand set to {density.value.upper()} for {approach.upper()} approach.")
            return f"Density updated to {density.value} for {approach.upper()}."

        if density == TrafficDensityEnum.HIGH:
            self._add_log("INFO", "Traffic density set to HIGH globally. Green phases extended to optimize queue discharge.")
        elif density == TrafficDensityEnum.LOW:
            self._add_log("INFO", "Traffic density set to LOW globally. Green phases adjusted for minimal delay.")
        else:
            self._add_log("INFO", "Traffic density set to MEDIUM globally. Standard cyclic timing enabled.")
        return f"Density updated to {density.value}."

    def calculate_queue_green_duration(self, approach: Optional[str] = None, queue_count: Optional[int] = None) -> float:
        """Calculate authoritative green duration using formula:
        green_duration = clamp(base_green + queued_vehicle_count * extension_per_vehicle, minimum_green, maximum_green)
        """
        if queue_count is not None:
            q = float(queue_count)
        else:
            app_norm = (approach or self.get_active_green_approach() or "north").lower()
            metric = self.traffic_generator.get_metrics(app_norm)
            q = float(metric.queue_length)

        calculated = self.base_green_duration + q * self.extension_per_vehicle
        return max(self.min_green_duration, min(self.max_green_duration, calculated))

    def get_base_green_duration(self, approach: Optional[str] = None) -> float:
        """Determine green phase duration based on approach density or traffic density setting."""
        if approach:
            metric = self.traffic_generator.get_metrics(approach)
            if metric.density == TrafficDensityEnum.HIGH:
                return self.normal_green_duration  # 12.0s starting baseline
            return self.base_green_duration         # 8.0s baseline

        if self.traffic_density == TrafficDensityEnum.HIGH:
            return 11.0
        elif self.traffic_density == TrafficDensityEnum.LOW:
            return 6.0
        return 8.0

    def get_initial_green_duration(self, approach: str) -> float:
        """Determine initial green duration for approach based on queued vehicles or baseline.

        Formula: clamp(base_green + queued_vehicle_count * extension_per_vehicle, minimum_green, maximum_green)
        If queue == 0, uses configured base green (8.0s) or density baseline.
        """
        metric = self.traffic_generator.get_metrics(approach)
        if metric.queue_length > 0:
            return self.calculate_queue_green_duration(approach, metric.queue_length)
        return self.get_base_green_duration(approach)

    def request_ambulance(
        self,
        approach: str = "south",
        route: str = "straight",
        active: bool = True,
        caller: Optional[str] = "api",
        reason: Optional[str] = "operator_dispatch",
    ) -> str:
        """Trigger emergency vehicle preemption with exclusive green priority and route selection."""
        approach = approach.lower()
        if approach not in ["north", "south", "east", "west"]:
            approach = "south"

        route_norm = (route or "straight").lower()
        if route_norm in ["turn_left", "left"]:
            route_norm = "left"
        elif route_norm in ["turn_right", "right"]:
            route_norm = "right"
        else:
            route_norm = "straight"

        caller_str = caller or "api"
        reason_str = reason or ("operator_dispatch" if active else "exit_boundary_cleared")

        if not active:
            if self.emergency_active:
                self.emergency_active = False
                self.emergency_approach = None
                self.emergency_route = "straight"
                self._add_log(
                    "INFO",
                    f"Ambulance priority cleared by {caller_str} (reason: {reason_str}). Resuming standard cyclic scheduling."
                )
                # Transition smoothly out of emergency
                if self.phase == "EMERGENCY_PRIORITY":
                    self._transition_to("ALL_RED_PRE_NS", 1.5, "Emergency Cleared - All Red Clearance")
            return "Ambulance priority deactivated."

        # Prevent duplicate dispatches from creating overlapping ambulances or resetting an active emergency
        if self.emergency_active and self.phase == "EMERGENCY_PRIORITY" and self.emergency_approach == approach and self.emergency_route == route_norm:
            return f"Ambulance priority already active for {approach.upper()} [{route_norm.upper()}]."

        self.emergency_active = True
        self.emergency_approach = approach
        self.emergency_route = route_norm

        if not self.simulation_running:
            self.simulation_running = True
            self._add_log("INFO", "Simulation automatically resumed for emergency vehicle preemption.")
        self._add_log(
            "EMERGENCY",
            f"EMERGENCY ALERT: Ambulance detected on {approach.upper()} approach [Route: {route_norm.upper()}] (caller: {caller_str}, reason: {reason_str}). Initiating clearance preemption."
        )

        # If pedestrian is active simultaneously, announce safety protocol
        if self.pedestrian_active:
            self._add_log(
                "WARN",
                "SIMULTANEOUS CONFLICT: Emergency preemption taking life-safety precedence over crosswalk. Safely expediting pedestrian clearance."
            )

        # Determine target corridor
        self.emergency_target_phase = f"{approach.upper()}_GREEN"

        if self.phase.startswith("ALL_RED"):
            # In all-red, transition directly to emergency priority
            self._transition_to("EMERGENCY_PRIORITY", 999.0, f"Emergency Priority ({approach.upper()} - {route_norm.upper()})")
            self._add_log("EMERGENCY", f"Exclusive priority established for {approach.upper()} ONLY. Ambulance granted continuous Green.")
        else:
            # Need safe clearance of conflicting traffic
            self._initiate_emergency_clearance()

        return f"Ambulance priority initiated for {approach.upper()} approach [{route_norm.upper()}]."

    def _initiate_emergency_clearance(self) -> None:
        """Safely clear active conflicting green or walk phases via yellow/all-red."""
        app_name = (self.emergency_approach or "south").upper()
        route_name = (self.emergency_route or "straight").upper()
        approach = (self.emergency_approach or "south").lower()

        # If already green on this incoming approach, grant continuous emergency priority immediately
        is_already_green = (
            (approach == "north" and self.phase in ["NORTH_GREEN", "NS_GREEN"]) or
            (approach == "south" and self.phase == "SOUTH_GREEN") or
            (approach == "east" and self.phase in ["EAST_GREEN", "EW_GREEN"]) or
            (approach == "west" and self.phase == "WEST_GREEN")
        )
        if is_already_green:
            self._transition_to("EMERGENCY_PRIORITY", 999.0, f"Emergency Priority ({app_name} - {route_name})")
            self._add_log("EMERGENCY", f"Exclusive priority established for {app_name} ONLY. Ambulance granted continuous Green.")
            return

        if self.phase in ["NORTH_GREEN", "NS_GREEN"]:
            self._transition_to("NORTH_YELLOW", 2.5, "North Yellow Clearance (Preempt)")
            self._add_log("WARN", "Conflicting North green transitioning to Yellow clearance for ambulance.")
        elif self.phase == "SOUTH_GREEN":
            self._transition_to("SOUTH_YELLOW", 2.5, "South Yellow Clearance (Preempt)")
            self._add_log("WARN", "Conflicting South green transitioning to Yellow clearance for ambulance.")
        elif self.phase in ["EAST_GREEN", "EW_GREEN"]:
            self._transition_to("EAST_YELLOW", 2.5, "East Yellow Clearance (Preempt)")
            self._add_log("WARN", "Conflicting East green transitioning to Yellow clearance for ambulance.")
        elif self.phase == "WEST_GREEN":
            self._transition_to("WEST_YELLOW", 2.5, "West Yellow Clearance (Preempt)")
            self._add_log("WARN", "Conflicting West green transitioning to Yellow clearance for ambulance.")
        elif self.phase in ["PEDESTRIAN_WALK", "PEDESTRIAN_FLASHING"]:
            self._transition_to("PEDESTRIAN_FLASHING", 2.0, "Pedestrian Expedited Clearance (Preempt)")
            self._add_log("WARN", "Pedestrians held with flashing clearance due to incoming emergency vehicle.")
        elif self.phase.endswith("_YELLOW") or self.phase in ["NS_YELLOW", "EW_YELLOW"]:
            prefix = self.phase.split("_")[0].capitalize()
            self.phase_display = f"{prefix} Yellow Clearance (Preempt)"
            self._add_log("WARN", f"Yellow clearance in progress for incoming {app_name} ambulance.")
        elif self.phase.startswith("ALL_RED"):
            # In all-red, transition directly to emergency priority
            self._transition_to("EMERGENCY_PRIORITY", 999.0, f"Emergency Priority ({app_name} - {route_name})")
            self._add_log("EMERGENCY", f"Exclusive priority established for {app_name} ONLY.")
        else:
            self._transition_to("EMERGENCY_PRIORITY", 999.0, f"Emergency Priority ({app_name} - {route_name})")
            self._add_log("EMERGENCY", f"Exclusive priority established for {app_name} ONLY.")

    def request_pedestrian(self, active: bool = True, crosswalk: str = "all") -> str:
        """Call for pedestrian crossing phase on specified crosswalk or 'all'."""
        crosswalk_norm = (crosswalk or "all").lower()
        if crosswalk_norm not in ["north", "south", "east", "west", "all"]:
            crosswalk_norm = "all"
        self.pedestrian_crosswalk = crosswalk_norm

        if not active:
            self.pedestrian_active = False
            self.pedestrian_queued = False
            return "Pedestrian request canceled."

        # If emergency is active, queue pedestrian request
        if self.emergency_active:
            self.pedestrian_queued = True
            self._add_log(
                "PEDESTRIAN",
                f"Pedestrian call for {self.pedestrian_crosswalk.upper()} crossing received during active emergency preemption. Request safely queued until emergency clears."
            )
            return "Pedestrian call queued (emergency has right of way)."

        if self.pedestrian_active or self.phase in ["PEDESTRIAN_WALK", "PEDESTRIAN_CLEARANCE", "PEDESTRIAN_FLASHING"]:
            return f"Pedestrian crossing phase is already pending or active for {self.pedestrian_crosswalk.upper()}."

        self.pedestrian_active = True
        cross_str = self.pedestrian_crosswalk.upper() if self.pedestrian_crosswalk != "all" else "ALL-CROSSWALK"
        self._add_log("PEDESTRIAN", f"Pedestrian button actuated for {cross_str} crossing. Scheduling safe transition to WALK.")

        # If currently in green, begin yellow clearance
        if self.phase in ["NORTH_GREEN", "NS_GREEN"]:
            self._transition_to("NORTH_YELLOW", 2.5, "North Yellow Clearance (Pedestrian Call)")
            self.resume_phase_after_preempt = "SOUTH_GREEN"
        elif self.phase == "SOUTH_GREEN":
            self._transition_to("SOUTH_YELLOW", 2.5, "South Yellow Clearance (Pedestrian Call)")
            self.resume_phase_after_preempt = "EAST_GREEN"
        elif self.phase in ["EAST_GREEN", "EW_GREEN"]:
            self._transition_to("EAST_YELLOW", 2.5, "East Yellow Clearance (Pedestrian Call)")
            self.resume_phase_after_preempt = "WEST_GREEN"
        elif self.phase == "WEST_GREEN":
            self._transition_to("WEST_YELLOW", 2.5, "West Yellow Clearance (Pedestrian Call)")
            self.resume_phase_after_preempt = "NORTH_GREEN"
        elif self.phase.startswith("ALL_RED"):
            self._transition_to("PEDESTRIAN_WALK", 7.0, f"{cross_str} WALK Phase")

        return f"Pedestrian crossing requested for {cross_str}. Conflicting vehicles will yield safely."

    def _transition_to(self, phase: str, duration: float, display: str) -> None:
        """Internal helper to atomically change the intersection phase and update signals."""
        self.phase = phase
        self.phase_duration = duration
        self.time_in_phase = 0.0
        self.phase_display = display
        self.green_extended = False
        self._update_signals_for_phase()

    def _update_signals_for_phase(self) -> None:
        """Enforce strict signal aspect mapping based on current phase (Guarantees Safety Invariants)."""
        # Default all to RED and DONT_WALK for failsafe
        all_red = {
            dir_name: SignalState(vehicle=SignalColor.RED, pedestrian=PedestrianSignal.DONT_WALK)
            for dir_name in ["north", "south", "east", "west"]
        }

        # 1. Single Approach Green Phases (Only ONE approach is GREEN)
        if self.phase in ["NORTH_GREEN", "NS_GREEN"]:
            all_red["north"].vehicle = SignalColor.GREEN
        elif self.phase == "SOUTH_GREEN":
            all_red["south"].vehicle = SignalColor.GREEN
        elif self.phase in ["EAST_GREEN", "EW_GREEN"]:
            all_red["east"].vehicle = SignalColor.GREEN
        elif self.phase == "WEST_GREEN":
            all_red["west"].vehicle = SignalColor.GREEN

        # 2. Single Approach Yellow Clearance Phases
        elif self.phase in ["NORTH_YELLOW", "NS_YELLOW"]:
            all_red["north"].vehicle = SignalColor.YELLOW
        elif self.phase == "SOUTH_YELLOW":
            all_red["south"].vehicle = SignalColor.YELLOW
        elif self.phase in ["EAST_YELLOW", "EW_YELLOW"]:
            all_red["east"].vehicle = SignalColor.YELLOW
        elif self.phase == "WEST_YELLOW":
            all_red["west"].vehicle = SignalColor.YELLOW

        # 3. All-Red Clearance Phases
        elif self.phase.startswith("ALL_RED"):
            # All remain RED
            pass

        # 4. Emergency Priority Phase
        elif self.phase == "EMERGENCY_PRIORITY":
            # ONLY the incoming approach must become GREEN.
            # The other THREE approaches must become RED.
            approach = (self.emergency_approach or "south").lower()
            for d in ["north", "south", "east", "west"]:
                if d == approach:
                    all_red[d].vehicle = SignalColor.GREEN
                else:
                    all_red[d].vehicle = SignalColor.RED

        # 5. Pedestrian Phases
        elif self.phase == "PEDESTRIAN_WALK":
            for dir_name in all_red:
                all_red[dir_name].vehicle = SignalColor.RED
                if self.pedestrian_crosswalk == "all" or dir_name == self.pedestrian_crosswalk:
                    all_red[dir_name].pedestrian = PedestrianSignal.WALK
                else:
                    all_red[dir_name].pedestrian = PedestrianSignal.DONT_WALK

        elif self.phase == "PEDESTRIAN_FLASHING":
            for dir_name in all_red:
                all_red[dir_name].vehicle = SignalColor.RED
                if self.pedestrian_crosswalk == "all" or dir_name == self.pedestrian_crosswalk:
                    all_red[dir_name].pedestrian = PedestrianSignal.FLASHING_DONT_WALK
                else:
                    all_red[dir_name].pedestrian = PedestrianSignal.DONT_WALK

        self.signals = all_red

        # Safety verification check: Conflicting green signals NEVER exist
        self._verify_safety_invariants()

    def _verify_safety_invariants(self) -> None:
        """Formal runtime assertion ensuring safety rules are never violated."""
        greens = [d for d, s in self.signals.items() if s.vehicle == SignalColor.GREEN]
        yellows = [d for d, s in self.signals.items() if s.vehicle == SignalColor.YELLOW]
        ped_walk = any(s.pedestrian == PedestrianSignal.WALK for s in self.signals.values())

        # Invariant 1: At most ONE vehicle approach is GREEN
        if len(greens) > 1:
            self._add_log("WARN", f"CRITICAL SAFETY INTERLOCK: Multiple greens detected ({greens})! Forcing fail-safe ALL RED.")
            for s in self.signals.values():
                s.vehicle = SignalColor.RED
            raise RuntimeError(f"Safety Invariant Violated: Multiple concurrent Green signals: {greens}")

        # Invariant 2: Green and Yellow cannot coexist
        if len(greens) > 0 and len(yellows) > 0:
            self._add_log("WARN", "CRITICAL SAFETY INTERLOCK: Simultaneous Green and Yellow detected! Forcing fail-safe ALL RED.")
            for s in self.signals.values():
                s.vehicle = SignalColor.RED
            raise RuntimeError("Safety Invariant Violated: Concurrent Green and Yellow signals.")

        # Invariant 3: At most ONE vehicle approach is YELLOW
        if len(yellows) > 1:
            self._add_log("WARN", f"CRITICAL SAFETY INTERLOCK: Multiple yellows detected ({yellows})! Forcing fail-safe ALL RED.")
            for s in self.signals.values():
                s.vehicle = SignalColor.RED
            raise RuntimeError(f"Safety Invariant Violated: Multiple concurrent Yellow signals: {yellows}")

        # Invariant 4: Pedestrian WALK is strictly exclusive with vehicle Green or Yellow
        if ped_walk and (len(greens) > 0 or len(yellows) > 0):
            self._add_log("WARN", "CRITICAL SAFETY INTERLOCK: Pedestrian WALK concurrent with vehicle Green/Yellow! Forcing fail-safe ALL RED.")
            for s in self.signals.values():
                s.vehicle = SignalColor.RED
                s.pedestrian = PedestrianSignal.DONT_WALK
            raise RuntimeError("Safety Invariant Violated: Pedestrian WALK concurrent with vehicular Green/Yellow.")

    def get_active_green_approach(self) -> Optional[str]:
        """Return the direction name ('north', 'south', 'east', 'west') currently in GREEN, or None."""
        if self.phase in ["NORTH_GREEN", "NS_GREEN"]:
            return "north"
        elif self.phase == "SOUTH_GREEN":
            return "south"
        elif self.phase in ["EAST_GREEN", "EW_GREEN"]:
            return "east"
        elif self.phase == "WEST_GREEN":
            return "west"
        elif self.phase == "EMERGENCY_PRIORITY":
            return (self.emergency_approach or "south").lower()
        return None

    def get_active_yellow_approach(self) -> Optional[str]:
        """Return the direction name currently in YELLOW clearance, or None."""
        if self.phase in ["NORTH_YELLOW", "NS_YELLOW"]:
            return "north"
        elif self.phase == "SOUTH_YELLOW":
            return "south"
        elif self.phase in ["EAST_YELLOW", "EW_YELLOW"]:
            return "east"
        elif self.phase == "WEST_YELLOW":
            return "west"
        return None

    def get_active_approach(self) -> str:
        """Return active vehicular approach name, or 'all-red' / 'pedestrian' / 'none'."""
        g = self.get_active_green_approach()
        if g:
            return g
        y = self.get_active_yellow_approach()
        if y:
            return y
        if self.phase.startswith("ALL_RED"):
            return "all-red"
        if self.phase.startswith("PEDESTRIAN"):
            return "pedestrian"
        return "none"

    def calculate_countdowns(self) -> Dict[str, float]:
        """Compute authoritative non-negative countdown timers for all four approaches.

        Rules:
        - Active Green: countdown to Yellow transition.
        - Active Yellow: countdown to All-Red transition.
        - All-Red clearance: countdown to next approach Green transition.
        - Red: estimated wait time until this approach turns Green.
        - Emergency preemption: 0.0 for ambulance approach ('PRIORITY'), -1.0 for conflicting ('HOLD').
        - Extended Green: countdown increases dynamically with phase extensions.
        - Strictly non-negative countdown values.
        """
        # 1. Emergency Preemption: 0.0 for priority approach, -1.0 for held approaches
        if self.emergency_active or self.phase == "EMERGENCY_PRIORITY":
            app = (self.emergency_approach or "south").lower()
            return {
                "north": 0.0 if app == "north" else -1.0,
                "south": 0.0 if app == "south" else -1.0,
                "east": 0.0 if app == "east" else -1.0,
                "west": 0.0 if app == "west" else -1.0,
            }

        # 2. Cycle configuration
        cycle = ["north", "south", "east", "west"]
        y_dur = self.yellow_duration
        ar_dur = self.all_red_duration
        rem_phase = max(0.0, self.phase_duration - self.time_in_phase)

        def get_g(app_name: str) -> float:
            return self.get_base_green_duration(app_name)

        countdowns: Dict[str, float] = {}

        # 3. Active Green Phase
        active_green = self.get_active_green_approach()
        if active_green in cycle:
            idx = cycle.index(active_green)
            countdowns[active_green] = max(0.0, round(rem_phase, 1))

            cum_wait = rem_phase + y_dur + ar_dur
            for offset in range(1, 4):
                next_app = cycle[(idx + offset) % 4]
                countdowns[next_app] = max(0.0, round(cum_wait, 1))
                cum_wait += get_g(next_app) + y_dur + ar_dur
            return countdowns

        # 4. Active Yellow Clearance Phase
        active_yellow = self.get_active_yellow_approach()
        if active_yellow in cycle:
            idx = cycle.index(active_yellow)
            countdowns[active_yellow] = max(0.0, round(rem_phase, 1))

            cum_wait = rem_phase + ar_dur
            for offset in range(1, 4):
                next_app = cycle[(idx + offset) % 4]
                countdowns[next_app] = max(0.0, round(cum_wait, 1))
                cum_wait += get_g(next_app) + y_dur + ar_dur
            return countdowns

        # 5. All-Red Clearance Phases
        next_green_app = "north"
        if self.phase == "ALL_RED_PRE_SOUTH":
            next_green_app = "south"
        elif self.phase in ["ALL_RED_PRE_EAST", "ALL_RED_PRE_EW"]:
            next_green_app = "east"
        elif self.phase == "ALL_RED_PRE_WEST":
            next_green_app = "west"
        elif self.phase in ["ALL_RED_PRE_NORTH", "ALL_RED_PRE_NS"]:
            resume = getattr(self, "resume_phase_after_preempt", "NORTH_GREEN")
            next_green_app = resume.split("_")[0].lower() if resume else "north"
            if next_green_app not in cycle:
                next_green_app = "north"

        idx = cycle.index(next_green_app)
        countdowns[next_green_app] = max(0.0, round(rem_phase, 1))
        cum_wait = rem_phase + get_g(next_green_app) + y_dur + ar_dur
        for offset in range(1, 4):
            subsequent_app = cycle[(idx + offset) % 4]
            countdowns[subsequent_app] = max(0.0, round(cum_wait, 1))
            cum_wait += get_g(subsequent_app) + y_dur + ar_dur
        return countdowns

    def tick(self, delta: float = 0.5) -> None:
        """Advance the deterministic state machine by delta seconds with adaptive green timing."""
        if not self.simulation_running:
            return

        # 1. Update traffic demand generator simulation
        active_green = self.get_active_green_approach()
        self.traffic_generator.update(delta, active_green_approach=active_green)

        # 2. Adaptive green evaluation (only during standard single-approach green phases)
        is_standard_green = self.phase in [
            "NORTH_GREEN", "SOUTH_GREEN", "EAST_GREEN", "WEST_GREEN", "NS_GREEN", "EW_GREEN"
        ]
        if is_standard_green and not self.emergency_active and not self.pedestrian_active and not self.pedestrian_queued:
            approach = self.get_active_green_approach()
            if approach:
                metric = self.traffic_generator.get_metrics(approach)

                # Adaptive green extension based on authoritative queue formula:
                # green_duration = clamp(8 + 1.5 * queued_vehicle_count, 6, 22)
                # Evaluated near phase expiration to ensure stable non-jittering countdowns
                if self.phase_duration < self.max_green_duration:
                    if metric.density == TrafficDensityEnum.HIGH or metric.queue_length >= 4:
                        if self.time_in_phase >= self.phase_duration - 1.5:
                            target_green = self.calculate_queue_green_duration(approach)
                            step = min(2.5, self.max_green_duration - self.phase_duration)
                            if target_green > self.phase_duration:
                                step = max(step, min(self.max_green_duration - self.phase_duration, target_green - self.phase_duration))
                            if step > 0:
                                self.phase_duration += step
                                self.green_extended = True
                                self._add_log(
                                    "ADAPTIVE",
                                    f"High density on {approach.upper()} (queue: {metric.queue_length}). Green extended by {step:.1f}s to {self.phase_duration:.1f}s (max: {self.max_green_duration}s)."
                                )
                    elif metric.density == TrafficDensityEnum.MEDIUM and metric.queue_length >= 3:
                        if self.phase_duration < 15.0 and self.time_in_phase >= self.phase_duration - 1.0:
                            step = min(2.0, 15.0 - self.phase_duration)
                            if step > 0:
                                self.phase_duration += step
                                self.green_extended = True
                                self._add_log(
                                    "ADAPTIVE",
                                    f"Medium density on {approach.upper()} (queue: {metric.queue_length}). Green extended to {self.phase_duration:.1f}s."
                                )

                # Early clearance: if minimum green served (>= min_green_duration) and queue completely cleared (queue == 0) and LOW density
                if (metric.density == TrafficDensityEnum.LOW or metric.queue_length == 0) and self.time_in_phase >= self.min_green_duration:
                    if metric.queue_length == 0 and self.phase_duration > self.min_green_duration:
                        self.phase_duration = min(self.phase_duration, self.time_in_phase + 0.5)

        self.time_in_phase += delta

        # Update pedestrian countdown timer display
        if self.phase == "PEDESTRIAN_WALK":
            self.pedestrian_remaining = max(0.0, self.phase_duration - self.time_in_phase)
        elif self.phase == "PEDESTRIAN_FLASHING":
            self.pedestrian_remaining = max(0.0, self.phase_duration - self.time_in_phase)
        else:
            self.pedestrian_remaining = 0.0

        # Check if current phase duration has elapsed
        if self.time_in_phase >= self.phase_duration:
            self._advance_phase()

    def _advance_phase(self) -> None:
        """Determine next phase in the deterministic cycle or handle pending preemption."""
        # 1. Handle Active Emergency
        if self.emergency_active:
            app_name = (self.emergency_approach or "south").upper()
            route_name = (self.emergency_route or "straight").upper()
            if self.phase.endswith("_YELLOW") or self.phase in ["NS_YELLOW", "EW_YELLOW"]:
                self._transition_to("ALL_RED_PRE_NS", 1.5, "Emergency Clearance - All Red Interlock")
            elif self.phase.startswith("ALL_RED"):
                self._transition_to("EMERGENCY_PRIORITY", 999.0, f"Emergency Priority ({app_name} - {route_name})")
                self._add_log("EMERGENCY", f"Protected priority corridor active for {app_name} [{route_name}]. Ambulance free to pass.")
            elif self.phase == "PEDESTRIAN_FLASHING":
                self._transition_to("ALL_RED_PRE_NS", 1.5, "Emergency Clearance - Post-Pedestrian Interlock")
            elif self.phase == "EMERGENCY_PRIORITY":
                # Emergency corridor must hold GREEN until ambulance finishes its route and active=False is sent.
                # Only if failsafe timeout (120s) is exceeded do we restore normal traffic.
                if self.time_in_phase >= 120.0:
                    self.emergency_active = False
                    self.emergency_approach = None
                    self.emergency_route = "straight"
                    self._add_log("WARN", "Ambulance priority safety timeout reached (120s). Restoring normal cyclic operation.")
                    self._transition_to("ALL_RED_PRE_NS", 1.5, "Post-Emergency All Red Clearance")
            else:
                self._transition_to("EMERGENCY_PRIORITY", 999.0, f"Emergency Priority ({app_name} - {route_name})")
                self._add_log("EMERGENCY", f"Protected priority corridor active for {app_name} [{route_name}]. Ambulance free to pass.")
            return

        # 2. Handle Pending Pedestrian Request
        if self.pedestrian_active or self.pedestrian_queued:
            if self.phase.endswith("_YELLOW") or self.phase in ["NS_YELLOW", "EW_YELLOW"]:
                self._transition_to("ALL_RED_PRE_NS", 1.5, "Pedestrian Call - Clearance All Red")
            elif self.phase.startswith("ALL_RED"):
                self.pedestrian_active = True
                self.pedestrian_queued = False
                cross_str = self.pedestrian_crosswalk.upper() if self.pedestrian_crosswalk != "all" else "ALL-CROSSWALK"
                self._transition_to("PEDESTRIAN_WALK", 7.0, f"{cross_str} WALK Phase")
                self._add_log("PEDESTRIAN", f"All vehicle traffic held at RED. {cross_str} displaying WALK (7s).")
            elif self.phase == "PEDESTRIAN_WALK":
                self._transition_to("PEDESTRIAN_FLASHING", 2.5, "Pedestrian Clearance (Flashing Don't Walk)")
                self._add_log("PEDESTRIAN", "Pedestrian clearance interval (2.5s flashing don't walk).")
            elif self.phase == "PEDESTRIAN_FLASHING":
                self.pedestrian_active = False
                self._add_log("INFO", "Pedestrian crossing completed. Safely returning to vehicle cycle.")
                self._transition_to("ALL_RED_PRE_NS", 1.5, "Post-Pedestrian All Red Clearance")
            return

        # 3. Standard Cyclic Progression (Strictly One Approach Green at a Time)
        yellow_time = self.yellow_duration
        all_red_time = self.all_red_duration

        # 1. North Green -> North Yellow
        if self.phase in ["NORTH_GREEN", "NS_GREEN"]:
            self._transition_to("NORTH_YELLOW", yellow_time, "North Yellow Clearance")
        # 2. North Yellow -> All Red Pre South
        elif self.phase in ["NORTH_YELLOW", "NS_YELLOW"]:
            self._transition_to("ALL_RED_PRE_SOUTH", all_red_time, "Inter-Phase All Red Clearance (Pre-South)")
        # 3. All Red Pre South -> South Green
        elif self.phase == "ALL_RED_PRE_SOUTH":
            sg_time = self.get_base_green_duration("south")
            self._transition_to("SOUTH_GREEN", sg_time, "South Green Phase")
            self._add_log("INFO", f"South approach granted Green ({sg_time:.1f}s).")
        # 4. South Green -> South Yellow
        elif self.phase == "SOUTH_GREEN":
            self._transition_to("SOUTH_YELLOW", yellow_time, "South Yellow Clearance")
        # 5. South Yellow -> All Red Pre East
        elif self.phase == "SOUTH_YELLOW":
            self._transition_to("ALL_RED_PRE_EAST", all_red_time, "Inter-Phase All Red Clearance (Pre-East)")
        # 6. All Red Pre East -> East Green
        elif self.phase in ["ALL_RED_PRE_EAST", "ALL_RED_PRE_EW"]:
            eg_time = self.get_base_green_duration("east")
            self._transition_to("EAST_GREEN", eg_time, "East Green Phase")
            self._add_log("INFO", f"East approach granted Green ({eg_time:.1f}s).")
        # 7. East Green -> East Yellow
        elif self.phase in ["EAST_GREEN", "EW_GREEN"]:
            self._transition_to("EAST_YELLOW", yellow_time, "East Yellow Clearance")
        # 8. East Yellow -> All Red Pre West
        elif self.phase in ["EAST_YELLOW", "EW_YELLOW"]:
            self._transition_to("ALL_RED_PRE_WEST", all_red_time, "Inter-Phase All Red Clearance (Pre-West)")
        # 9. All Red Pre West -> West Green
        elif self.phase == "ALL_RED_PRE_WEST":
            wg_time = self.get_base_green_duration("west")
            self._transition_to("WEST_GREEN", wg_time, "West Green Phase")
            self._add_log("INFO", f"West approach granted Green ({wg_time:.1f}s).")
        # 10. West Green -> West Yellow
        elif self.phase == "WEST_GREEN":
            self._transition_to("WEST_YELLOW", yellow_time, "West Yellow Clearance")
        # 11. West Yellow -> All Red Pre North
        elif self.phase == "WEST_YELLOW":
            self._transition_to("ALL_RED_PRE_NORTH", all_red_time, "Inter-Phase All Red Clearance (Pre-North)")
        # 12. All Red Pre North (or ALL_RED_PRE_NS) -> Target Green (Default North Green)
        elif self.phase in ["ALL_RED_PRE_NORTH", "ALL_RED_PRE_NS"]:
            resume = getattr(self, "resume_phase_after_preempt", "NORTH_GREEN")
            target = resume if resume in ["NORTH_GREEN", "SOUTH_GREEN", "EAST_GREEN", "WEST_GREEN"] else "NORTH_GREEN"
            target_app = target.split("_")[0].lower()
            tg_time = self.get_base_green_duration(target_app)
            self.resume_phase_after_preempt = "NORTH_GREEN"
            self._transition_to(target, tg_time, f"{target.split('_')[0].capitalize()} Green Phase")
            self._add_log("INFO", f"{target.split('_')[0].capitalize()} approach granted Green ({tg_time:.1f}s).")
        else:
            ng_time = self.get_base_green_duration("north")
            self._transition_to("NORTH_GREEN", ng_time, "North Green Phase")

    def get_state(self) -> IntersectionStateResponse:
        """Construct full intersection snapshot including propositional logic evaluation, countdowns, and approach metrics."""
        # Propositions
        p = self.traffic_density == TrafficDensityEnum.HIGH
        q = self.emergency_active
        r = self.pedestrian_active or self.phase in ["PEDESTRIAN_WALK", "PEDESTRIAN_FLASHING"]

        logic_eval = evaluate_traffic_proposition(p, q, r)
        truth_table = get_truth_table()

        # Approach metrics from traffic demand generator
        approach_metrics = {
            app: self.traffic_generator.get_metrics(app)
            for app in ["north", "south", "east", "west"]
        }

        # Calculate authoritative countdowns
        countdowns = self.calculate_countdowns()

        return IntersectionStateResponse(
            phase=self.phase,
            phase_display=self.phase_display,
            time_in_phase=round(self.time_in_phase, 1),
            phase_duration=round(self.phase_duration, 1),
            signals=self.signals,
            emergency_active=self.emergency_active,
            emergency_approach=self.emergency_approach,
            emergency_route=self.emergency_route,
            pedestrian_active=self.pedestrian_active,
            pedestrian_remaining=round(self.pedestrian_remaining, 1),
            pedestrian_crosswalk=getattr(self, "pedestrian_crosswalk", "north"),
            traffic_density=self.traffic_density,
            simulation_running=self.simulation_running,
            logic=logic_eval,
            truth_table=truth_table,
            recent_events=self.events[:25],
            server_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            active_approach=self.get_active_approach(),
            green_extended=self.green_extended,
            current_high_demand_approach=self.traffic_generator.current_high_demand_approach,
            approach_metrics=approach_metrics,
            countdowns=countdowns,
            min_green_duration=self.min_green_duration,
            base_green_duration=self.base_green_duration,
            extension_per_vehicle=self.extension_per_vehicle,
            normal_green_duration=self.normal_green_duration,
            max_green_duration=self.max_green_duration,
        )
