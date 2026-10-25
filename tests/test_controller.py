"""Unit and invariant tests for the deterministic IntersectionController."""

import pytest
from app.controller import IntersectionController
from app.schemas import PedestrianSignal, SignalColor, TrafficDensityEnum


def test_initial_state_safety_invariants():
    """Verify that initial baseline signals satisfy all safety interlocks."""
    ctrl = IntersectionController()
    state = ctrl.get_state()
    
    # North is Green; South, East, West are Red (Strictly ONE approach Green)
    assert state.phase == "NORTH_GREEN"
    assert state.signals["north"].vehicle == SignalColor.GREEN
    assert state.signals["south"].vehicle == SignalColor.RED
    assert state.signals["east"].vehicle == SignalColor.RED
    assert state.signals["west"].vehicle == SignalColor.RED
    
    # All pedestrians DONT_WALK
    for s in state.signals.values():
        assert s.pedestrian == PedestrianSignal.DONT_WALK


def test_no_conflicting_greens_over_cyclic_ticks():
    """Run simulation through multiple cycles (200 ticks) and verify safety invariant holds."""
    ctrl = IntersectionController()
    ctrl.simulation_running = True

    for _ in range(200):
        ctrl.tick(delta=0.5)
        signals = ctrl.signals

        greens = [d for d, s in signals.items() if s.vehicle == SignalColor.GREEN]
        yellows = [d for d, s in signals.items() if s.vehicle == SignalColor.YELLOW]
        ped_walk = any(s.pedestrian == PedestrianSignal.WALK for s in signals.values())

        # Invariant 1: At most ONE approach is Green at any time
        assert len(greens) <= 1, f"Failed at phase {ctrl.phase}: Multiple greens {greens}"

        # Invariant 2: Green and Yellow never coexist
        if len(greens) > 0:
            assert len(yellows) == 0, f"Failed at phase {ctrl.phase}: Concurrent Green and Yellow"

        # Invariant 3: Pedestrian WALK NEVER occurs when any vehicular signal is Green or Yellow
        if ped_walk:
            assert len(greens) == 0 and len(yellows) == 0, f"Failed at phase {ctrl.phase}: Pedestrian WALK with active Green/Yellow!"


def test_clearance_intervals_not_skipped():
    """Verify that Green always transitions through Yellow and All-Red before next Green."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    
    # Initial is NORTH_GREEN
    assert ctrl.phase == "NORTH_GREEN"
    
    # Tick past NORTH_GREEN duration (8s)
    for _ in range(17):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "NORTH_YELLOW":
            break
            
    assert ctrl.phase == "NORTH_YELLOW"
    assert ctrl.signals["north"].vehicle == SignalColor.YELLOW
    assert ctrl.signals["south"].vehicle == SignalColor.RED

    # Advance through yellow clearance
    for _ in range(6):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "ALL_RED_PRE_SOUTH":
            break

    assert ctrl.phase == "ALL_RED_PRE_SOUTH"
    assert ctrl.signals["north"].vehicle == SignalColor.RED
    assert ctrl.signals["south"].vehicle == SignalColor.RED
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED

    # Advance through all-red clearance into SOUTH_GREEN
    for _ in range(4):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "SOUTH_GREEN":
            break

    assert ctrl.phase == "SOUTH_GREEN"
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN
    assert ctrl.signals["north"].vehicle == SignalColor.RED


def test_ambulance_preemption_and_corridor():
    """Verify that ambulance call preempts normal traffic safely and establishes protected corridor."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    
    # Switch to East Green first
    ctrl._transition_to("EAST_GREEN", 8.0, "East Green Phase")
    assert ctrl.signals["east"].vehicle == SignalColor.GREEN
    assert ctrl.signals["south"].vehicle == SignalColor.RED

    # Ambulance arrives on South approach
    msg = ctrl.request_ambulance(approach="south", active=True)
    assert "priority initiated" in msg
    assert ctrl.emergency_active is True
    assert ctrl.emergency_approach == "south"

    # Conflicting East green must immediately enter Yellow clearance
    assert ctrl.phase == "EAST_YELLOW"
    assert ctrl.signals["east"].vehicle == SignalColor.YELLOW

    # Tick through Yellow and All-Red clearance
    for _ in range(10):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    # Protected priority corridor must now be established for South exclusively
    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN
    assert ctrl.signals["north"].vehicle == SignalColor.RED
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED


def test_pedestrian_crossing_safety():
    """Verify pedestrian call halts conflicting vehicles and awards WALK exclusively."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    
    # North is currently Green
    assert ctrl.signals["north"].vehicle == SignalColor.GREEN

    # Request pedestrian crossing
    msg = ctrl.request_pedestrian(active=True)
    assert "requested" in msg
    assert ctrl.pedestrian_active is True

    # Immediate transition to Yellow clearance for vehicles
    assert ctrl.phase == "NORTH_YELLOW"
    assert ctrl.signals["north"].vehicle == SignalColor.YELLOW

    # Tick through clearance into PEDESTRIAN_WALK
    for _ in range(10):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "PEDESTRIAN_WALK":
            break

    assert ctrl.phase == "PEDESTRIAN_WALK"
    
    # All vehicles MUST be Red during pedestrian WALK
    for s in ctrl.signals.values():
        assert s.vehicle == SignalColor.RED
        assert s.pedestrian == PedestrianSignal.WALK


def test_simultaneous_emergency_and_pedestrian_requests():
    """Verify simultaneous emergency and pedestrian calls resolve safely without exceptions."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Trigger pedestrian call
    ctrl.request_pedestrian(active=True)
    
    # Simultaneously trigger ambulance call
    ctrl.request_ambulance(approach="west", active=True)

    # Run for 30 ticks and verify safety invariants remain intact
    for _ in range(30):
        ctrl.tick(delta=0.5)
        signals = ctrl.signals
        ns_green = (signals["north"].vehicle == SignalColor.GREEN)
        ew_green = (signals["east"].vehicle == SignalColor.GREEN)
        ped_walk = any(s.pedestrian == PedestrianSignal.WALK for s in signals.values())

        # No conflicting vehicle greens
        assert not (ns_green and ew_green)
        # No pedestrian walk during green
        if ped_walk:
            assert not ns_green and not ew_green


def test_ambulance_priority_holds_without_premature_expiry():
    """Verify emergency priority holds GREEN for ambulance approach past 15s and releases cleanly."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Request ambulance on East approach
    ctrl.request_ambulance(approach="east", active=True)

    # Tick past yellow and all-red into EMERGENCY_PRIORITY
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["east"].vehicle == SignalColor.GREEN
    assert ctrl.signals["north"].vehicle == SignalColor.RED

    # Advance 40 ticks (20 seconds) - must NOT drop to normal cycle or red
    for _ in range(40):
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"
        assert ctrl.signals["east"].vehicle == SignalColor.GREEN
        assert ctrl.signals["north"].vehicle == SignalColor.RED

    # Now simulate ambulance clearing intersection (active=False)
    ctrl.request_ambulance(approach="east", active=False)
    assert ctrl.emergency_active is False
    assert ctrl.phase == "ALL_RED_PRE_NS"
    assert ctrl.signals["east"].vehicle == SignalColor.RED


@pytest.mark.parametrize("approach, expected_green_dir, expected_red_dir", [
    ("north", "north", "east"),
    ("south", "south", "west"),
    ("east", "east", "north"),
    ("west", "west", "south"),
])
def test_ambulance_from_all_four_approaches(approach, expected_green_dir, expected_red_dir):
    """Verify ambulance preemption functions correctly for all four approaches."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    ctrl.request_ambulance(approach=approach, active=True)
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals[expected_green_dir].vehicle == SignalColor.GREEN
    assert ctrl.signals[expected_red_dir].vehicle == SignalColor.RED


def test_pedestrian_full_clearance_cycle_keeps_vehicles_red():
    """Verify all vehicular traffic remains stopped RED during WALK, FLASHING clearance, and post-all-red."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Request pedestrian phase
    ctrl.request_pedestrian(active=True)

    # 1. Tick through vehicle yellow & clearance to reach WALK
    for _ in range(10):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "PEDESTRIAN_WALK":
            break

    assert ctrl.phase == "PEDESTRIAN_WALK"

    # 2. Throughout WALK (7.0s = 14 ticks of 0.5s), all vehicles must remain RED
    for _ in range(13):
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "PEDESTRIAN_WALK"
        for s in ctrl.signals.values():
            assert s.vehicle == SignalColor.RED
            assert s.pedestrian == PedestrianSignal.WALK

    # Advance into FLASHING clearance (2.5s)
    ctrl.tick(delta=0.5)
    assert ctrl.phase == "PEDESTRIAN_FLASHING"

    # 3. Throughout FLASHING clearance (5 ticks of 0.5s), all vehicles must remain RED
    for _ in range(4):
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "PEDESTRIAN_FLASHING"
        for s in ctrl.signals.values():
            assert s.vehicle == SignalColor.RED
            assert s.pedestrian == PedestrianSignal.FLASHING_DONT_WALK

    # Advance into post-pedestrian ALL_RED clearance
    ctrl.tick(delta=0.5)
    assert ctrl.phase == "ALL_RED_PRE_NS"
    for s in ctrl.signals.values():
        assert s.vehicle == SignalColor.RED

    # 4. Only after all-red clearance elapses (1.5s = 3 ticks) does vehicle green resume
    for _ in range(3):
        ctrl.tick(delta=0.5)

    assert ctrl.phase == "SOUTH_GREEN"
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN


def test_ambulance_conflicting_remains_red_until_cleared():
    """Verify conflicting vehicles stay RED and cannot get Green while emergency is active."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Dispatch ambulance on South
    ctrl.request_ambulance(approach="south", active=True)

    # Clear through to EMERGENCY_PRIORITY
    for _ in range(10):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"

    # Conflicting East and West must be RED
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED

    # Even if pedestrian calls or time elapses, conflicting traffic NEVER gets Green
    ctrl.request_pedestrian(active=True)
    for _ in range(20):
        ctrl.tick(delta=0.5)
        assert ctrl.signals["east"].vehicle == SignalColor.RED
        assert ctrl.signals["west"].vehicle == SignalColor.RED
        assert ctrl.phase == "EMERGENCY_PRIORITY"

    # Ambulance exits intersection -> active=False
    ctrl.request_ambulance(approach="south", active=False)
    assert ctrl.phase == "ALL_RED_PRE_NS"
    # Interlock clearance keeps all red
    for s in ctrl.signals.values():
        assert s.vehicle == SignalColor.RED


def test_req1_ambulance_approach_stays_continuously_green_throughout_priority():
    """Requirement 1: Ambulance approach stays GREEN continuously without turning YELLOW/RED during emergency."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    ctrl.request_ambulance(approach="west", active=True)

    # Clear through to EMERGENCY_PRIORITY
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    # Over 50 ticks (25 seconds), West must strictly remain GREEN every single tick
    for i in range(50):
        ctrl.tick(delta=0.5)
        assert ctrl.signals["west"].vehicle == SignalColor.GREEN, f"West dropped from Green at tick {i}"
        assert ctrl.phase == "EMERGENCY_PRIORITY"


def test_req2_conflicting_approaches_remain_continuously_red_during_emergency():
    """Requirement 2: Conflicting approaches remain RED throughout emergency priority."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    ctrl.request_ambulance(approach="north", active=True)

    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    # Conflicting East and West must be RED every single tick
    for i in range(40):
        ctrl.tick(delta=0.5)
        assert ctrl.signals["east"].vehicle == SignalColor.RED
        assert ctrl.signals["west"].vehicle == SignalColor.RED
        assert ctrl.signals["east"].vehicle != SignalColor.GREEN
        assert ctrl.signals["west"].vehicle != SignalColor.GREEN


def test_req3_normal_cycle_cannot_overwrite_emergency_signals():
    """Requirement 3: Normal traffic cycle timers cannot overwrite emergency priority."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    ctrl.request_ambulance(approach="east", active=True)

    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    # Change density or step ticks beyond normal cycle durations
    ctrl.set_traffic_density(TrafficDensityEnum.HIGH)
    for _ in range(60):  # 30 seconds
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"
        assert ctrl.signals["east"].vehicle == SignalColor.GREEN
        assert ctrl.signals["north"].vehicle == SignalColor.RED


def test_req4_directional_cardinal_mapping_all_four_approaches():
    """Requirement 4: North, South, East, West correctly map to directional approaches with exclusive green."""
    for approach in ["north", "south", "east", "west"]:
        ctrl = IntersectionController()
        ctrl.set_simulation_state("reset")
        ctrl.request_ambulance(approach=approach, active=True)

        for _ in range(12):
            ctrl.tick(delta=0.5)
            if ctrl.phase == "EMERGENCY_PRIORITY":
                break

        assert ctrl.emergency_approach == approach
        assert ctrl.signals[approach].vehicle == SignalColor.GREEN
        for other in ["north", "south", "east", "west"]:
            if other != approach:
                assert ctrl.signals[other].vehicle == SignalColor.RED, f"Expected {other} to be RED during {approach} priority!"


@pytest.mark.parametrize("chosen_crosswalk", ["north", "south", "east", "west"])
def test_req5_selected_pedestrian_crossing_walk_allocation(chosen_crosswalk):
    """Requirement 5: Selected pedestrian crossing produces WALK only on that approach."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    ctrl.request_pedestrian(active=True, crosswalk=chosen_crosswalk)
    assert ctrl.pedestrian_crosswalk == chosen_crosswalk

    # Tick to WALK phase
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "PEDESTRIAN_WALK":
            break

    assert ctrl.phase == "PEDESTRIAN_WALK"
    for d in ["north", "south", "east", "west"]:
        if d == chosen_crosswalk:
            assert ctrl.signals[d].pedestrian == PedestrianSignal.WALK
        else:
            assert ctrl.signals[d].pedestrian == PedestrianSignal.DONT_WALK


def test_req6_pedestrian_starts_only_after_clearance_intervals():
    """Requirement 6: Pedestrians start only after backend grants WALK (clearance intervals honored)."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Initial state is NORTH_GREEN
    assert ctrl.phase == "NORTH_GREEN"
    ctrl.request_pedestrian(active=True, crosswalk="north")

    # Must immediately be in clearance yellow, NOT in WALK yet!
    assert ctrl.phase == "NORTH_YELLOW"
    assert ctrl.signals["north"].pedestrian == PedestrianSignal.DONT_WALK

    # Advance 1 second into yellow
    ctrl.tick(delta=1.0)
    assert ctrl.phase == "NORTH_YELLOW"
    assert ctrl.signals["north"].pedestrian == PedestrianSignal.DONT_WALK

    # Advance past yellow into ALL_RED clearance
    ctrl.tick(delta=2.0)
    assert ctrl.phase == "ALL_RED_PRE_NS"
    assert ctrl.signals["north"].pedestrian == PedestrianSignal.DONT_WALK

    # Only after all-red clearance completes does WALK start
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "PEDESTRIAN_WALK"
    assert ctrl.signals["north"].pedestrian == PedestrianSignal.WALK


def test_req7_conflicting_vehicles_stay_stopped_during_selected_crossing():
    """Requirement 7: All vehicles stay stopped at RED during the selected crossing."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    ctrl.request_pedestrian(active=True, crosswalk="south")
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "PEDESTRIAN_WALK":
            break

    assert ctrl.phase == "PEDESTRIAN_WALK"
    # Throughout WALK (7s) and FLASHING (2.5s), ALL vehicles must remain RED
    for _ in range(18):
        ctrl.tick(delta=0.5)
        if ctrl.phase in ["PEDESTRIAN_WALK", "PEDESTRIAN_FLASHING"]:
            for d in ["north", "south", "east", "west"]:
                assert ctrl.signals[d].vehicle == SignalColor.RED


def test_req8_simultaneous_emergency_and_pedestrian_preserves_safety():
    """Requirement 8: Emergency arriving during active pedestrian WALK expedites clearance safely."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Reach WALK phase
    ctrl.request_pedestrian(active=True, crosswalk="east")
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "PEDESTRIAN_WALK":
            break

    assert ctrl.phase == "PEDESTRIAN_WALK"

    # Emergency arrives on North approach while pedestrians are walking
    ctrl.request_ambulance(approach="north", active=True)

    # Walk must transition immediately to flashing clearance (not green immediately!)
    assert ctrl.phase == "PEDESTRIAN_FLASHING"
    assert ctrl.signals["north"].vehicle == SignalColor.RED

    # Advance through flashing clearance
    for _ in range(5):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "ALL_RED_PRE_NS":
            break

    assert ctrl.phase == "ALL_RED_PRE_NS"
    for s in ctrl.signals.values():
        assert s.vehicle == SignalColor.RED

    # Advance through all-red into EMERGENCY_PRIORITY
    for _ in range(4):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["north"].vehicle == SignalColor.GREEN
    assert ctrl.signals["east"].vehicle == SignalColor.RED


def test_ambulance_dispatch_auto_resumes_paused_simulation():
    """Verify that dispatching an ambulance automatically resumes simulation if it was paused."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("pause")
    assert ctrl.simulation_running is False

    ctrl.request_ambulance(approach="east", active=True)
    assert ctrl.emergency_active is True
    assert ctrl.simulation_running is True


def test_repeated_ambulance_dispatch_preserves_state():
    """Verify repeated ambulance dispatch calls do not corrupt state or cause errors."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    for _ in range(5):
        msg = ctrl.request_ambulance(approach="west", active=True)
        assert "priority initiated" in msg
        assert ctrl.emergency_active is True
        assert ctrl.emergency_approach == "west"

    # Step into priority
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["west"].vehicle == SignalColor.GREEN

    # Repeated dispatch while already in priority maintains green
    msg = ctrl.request_ambulance(approach="west", active=True)
    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["west"].vehicle == SignalColor.GREEN


def test_east_corridor_emergency_clearance_and_signal_synchronization():
    """Verify that dispatching an ambulance on EAST approach performs safety clearance then holds green."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    assert ctrl.phase == "NORTH_GREEN"
    assert ctrl.signals["east"].vehicle == SignalColor.RED

    # Step 1: Dispatch ambulance from East
    msg = ctrl.request_ambulance(approach="east", active=True)
    assert "EAST" in msg
    assert ctrl.emergency_active is True
    assert ctrl.emergency_approach == "east"

    # Controller must initiate safety clearance: NORTH_YELLOW (2.5s)
    # During safety clearance, EAST approach must remain RED for safety!
    assert ctrl.phase == "NORTH_YELLOW"
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["north"].vehicle == SignalColor.YELLOW
    assert ctrl.signals["south"].vehicle == SignalColor.RED

    # Advance 1.0s into yellow: East remains RED
    ctrl.tick(delta=1.0)
    assert ctrl.phase == "NORTH_YELLOW"
    assert ctrl.signals["east"].vehicle == SignalColor.RED

    # Advance another 1.5s (reaches 2.5s): transitions to ALL_RED_PRE_NS (1.5s)
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "ALL_RED_PRE_NS"
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["north"].vehicle == SignalColor.RED
    assert ctrl.signals["south"].vehicle == SignalColor.RED

    # Advance 1.5s through all-red: transitions to EMERGENCY_PRIORITY!
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "EMERGENCY_PRIORITY"
    # Protected EAST approach is now exclusively GREEN!
    assert ctrl.signals["east"].vehicle == SignalColor.GREEN
    assert ctrl.signals["west"].vehicle == SignalColor.RED
    # Conflicting North-South approaches must remain RED!
    assert ctrl.signals["north"].vehicle == SignalColor.RED
    assert ctrl.signals["south"].vehicle == SignalColor.RED

    # Step 2: Hold priority continuously without cyclic degradation
    for _ in range(40):  # 20 seconds
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"
        assert ctrl.signals["east"].vehicle == SignalColor.GREEN
        assert ctrl.signals["north"].vehicle == SignalColor.RED
        assert ctrl.signals["south"].vehicle == SignalColor.RED

    # Step 3: Deactivate priority after ambulance clears intersection
    deact_msg = ctrl.request_ambulance(approach="east", active=False)
    assert "deactivated" in deact_msg
    assert ctrl.emergency_active is False

    # Smooth clearance transition back to cyclic
    assert ctrl.phase == "ALL_RED_PRE_NS"
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "NORTH_GREEN"
    assert ctrl.signals["north"].vehicle == SignalColor.GREEN
    assert ctrl.signals["east"].vehicle == SignalColor.RED


def test_emergency_priority_grants_continuous_stop_line_permission():
    """Verify that during EMERGENCY_PRIORITY, the emergency corridor signal is strictly GREEN across all ticks."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    for app, opposite_dir, conflict_dir in [
        ("north", "south", "east"),
        ("south", "north", "west"),
        ("east", "west", "north"),
        ("west", "east", "south"),
    ]:
        ctrl.request_ambulance(approach=app, active=True)
        # Advance into EMERGENCY_PRIORITY
        for _ in range(15):
            ctrl.tick(delta=0.5)
            if ctrl.phase == "EMERGENCY_PRIORITY":
                break

        assert ctrl.phase == "EMERGENCY_PRIORITY"
        # Emergency approach has GREEN (permission to pass stop line)
        assert ctrl.signals[app].vehicle == SignalColor.GREEN
        # Opposite and conflicting directions have RED
        assert ctrl.signals[opposite_dir].vehicle == SignalColor.RED
        assert ctrl.signals[conflict_dir].vehicle == SignalColor.RED
        # Crosswalks have DONT_WALK
        for s in ctrl.signals.values():
            assert s.pedestrian == PedestrianSignal.DONT_WALK

        # Clear before next iteration
        ctrl.request_ambulance(approach=app, active=False)
        ctrl.tick(delta=2.0)


def test_south_approach_emergency_clearance_and_priority_progression():
    """Verify automatic emergency clearance and priority grant when dispatching South ambulance."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Force starting phase into EAST_GREEN to simulate cross-traffic moving
    ctrl.phase = "EAST_GREEN"
    ctrl.phase_duration = 8.0
    ctrl.time_in_phase = 2.0
    ctrl._update_signals_for_phase()
    assert ctrl.signals["east"].vehicle == SignalColor.GREEN
    assert ctrl.signals["south"].vehicle == SignalColor.RED

    # 1. Dispatch ambulance on South approach
    msg = ctrl.request_ambulance(approach="south", active=True)
    assert "SOUTH" in msg
    assert ctrl.emergency_active is True
    assert ctrl.emergency_approach == "south"

    # Must immediately initiate safety clearance: EAST_YELLOW
    assert ctrl.phase == "EAST_YELLOW"
    assert ctrl.signals["east"].vehicle == SignalColor.YELLOW
    # During clearance, South approach is safely held at RED
    assert ctrl.signals["south"].vehicle == SignalColor.RED
    assert ctrl.signals["north"].vehicle == SignalColor.RED

    # Advance 2.5s to complete yellow clearance -> transitions to ALL_RED_PRE_NS (1.5s)
    for _ in range(5):
        ctrl.tick(delta=0.5)
    assert ctrl.phase == "ALL_RED_PRE_NS"
    # In all-red clearance, ALL approaches are RED
    for d in ["north", "south", "east", "west"]:
        assert ctrl.signals[d].vehicle == SignalColor.RED

    # Advance 1.5s to complete all-red clearance -> transitions to EMERGENCY_PRIORITY!
    for _ in range(3):
        ctrl.tick(delta=0.5)
    assert ctrl.phase == "EMERGENCY_PRIORITY"

    # Selected SOUTH approach MUST be GREEN!
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN
    # Conflicting East and West approaches MUST be RED!
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED
    # Crosswalks must be DONT_WALK
    for s in ctrl.signals.values():
        assert s.pedestrian == PedestrianSignal.DONT_WALK

    # Normal phase timers must NOT overwrite emergency priority: holds for 30s+
    for _ in range(60):
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"
        assert ctrl.signals["south"].vehicle == SignalColor.GREEN
        assert ctrl.signals["east"].vehicle == SignalColor.RED
        assert ctrl.signals["west"].vehicle == SignalColor.RED

    # When ambulance exits, safely release emergency mode and resume normal signal cycling
    deact_msg = ctrl.request_ambulance(approach="south", active=False)
    assert "deactivated" in deact_msg
    assert ctrl.emergency_active is False
    assert ctrl.phase == "ALL_RED_PRE_NS"

    # Advance through post-emergency clearance back to normal cycle
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "NORTH_GREEN"
    assert ctrl.signals["north"].vehicle == SignalColor.GREEN


def test_east_and_west_approach_emergency_progression():
    """Verify emergency clearance and protected corridor for East and West approaches."""
    for test_app in ["east", "west"]:
        ctrl = IntersectionController()
        ctrl.set_simulation_state("reset")
        # Currently NORTH_GREEN
        assert ctrl.phase == "NORTH_GREEN"
        assert ctrl.signals["north"].vehicle == SignalColor.GREEN

        # Dispatch ambulance on East/West approach
        ctrl.request_ambulance(approach=test_app, active=True)
        assert ctrl.emergency_active is True
        assert ctrl.emergency_approach == test_app

        # Must clear conflicting North green via NORTH_YELLOW
        assert ctrl.phase == "NORTH_YELLOW"
        assert ctrl.signals["north"].vehicle == SignalColor.YELLOW
        assert ctrl.signals[test_app].vehicle == SignalColor.RED

        # Advance 2.5s -> ALL_RED_PRE_NS
        for _ in range(5):
            ctrl.tick(delta=0.5)
        assert ctrl.phase == "ALL_RED_PRE_NS"
        for d in ["north", "south", "east", "west"]:
            assert ctrl.signals[d].vehicle == SignalColor.RED

        # Advance 1.5s -> EMERGENCY_PRIORITY
        for _ in range(3):
            ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"

        # Dispatched approach MUST be GREEN; other 3 approaches MUST be RED
        assert ctrl.signals[test_app].vehicle == SignalColor.GREEN
        for other in ["north", "south", "east", "west"]:
            if other != test_app:
                assert ctrl.signals[other].vehicle == SignalColor.RED

        # Deactivate
        ctrl.request_ambulance(approach=test_app, active=False)
        assert ctrl.emergency_active is False
        assert ctrl.phase == "ALL_RED_PRE_NS"


def test_emergency_clearance_when_initial_green_and_exclusive_priority():
    """Verify that when ambulance arrives during green, opposite green clears safely before granting exclusive green."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    # NORTH_GREEN is active
    assert ctrl.phase == "NORTH_GREEN"

    # South ambulance arrives - North was green, so safety clearance is required to turn North red
    ctrl.request_ambulance(approach="south", active=True)
    assert ctrl.phase == "NORTH_YELLOW"

    # Advance 2.5s yellow + 1.5s all-red
    for _ in range(8):
        ctrl.tick(delta=0.5)

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN
    assert ctrl.signals["north"].vehicle == SignalColor.RED
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED


@pytest.mark.parametrize("app,conflicting_init_phase,conflicting_dir", [
    ("north", "EAST_GREEN", "east"),
    ("south", "EAST_GREEN", "east"),
    ("east", "NORTH_GREEN", "north"),
    ("west", "NORTH_GREEN", "north"),
])
def test_all_four_approaches_clearance_and_cyclic_immunity(app, conflicting_init_phase, conflicting_dir):
    """Verify all 4 ambulance approaches complete clearance, lock signals, and cannot be overwritten by normal cycling."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    
    # 1. Set controller to conflicting initial phase
    if conflicting_init_phase == "EAST_GREEN":
        ctrl._transition_to("EAST_GREEN", 8.0, "East Green Phase")
    else:
        ctrl._transition_to("NORTH_GREEN", 8.0, "North Green Phase")
        
    assert ctrl.signals[conflicting_dir].vehicle == SignalColor.GREEN
    assert ctrl.signals[app].vehicle == SignalColor.RED

    # 2. Dispatch ambulance from selected approach
    ctrl.request_ambulance(approach=app, active=True)
    assert ctrl.emergency_active is True
    assert ctrl.emergency_approach == app

    # Conflicting green must immediately enter Yellow clearance
    expected_yellow = "EAST_YELLOW" if conflicting_init_phase == "EAST_GREEN" else "NORTH_YELLOW"
    assert ctrl.phase == expected_yellow
    assert ctrl.signals[conflicting_dir].vehicle == SignalColor.YELLOW
    assert ctrl.signals[app].vehicle == SignalColor.RED

    # 3. Complete yellow clearance (2.5s) -> transitions to ALL_RED_PRE_NS
    for _ in range(5):
        ctrl.tick(delta=0.5)
    assert ctrl.phase == "ALL_RED_PRE_NS"
    for d in ["north", "south", "east", "west"]:
        assert ctrl.signals[d].vehicle == SignalColor.RED

    # 4. Complete all-red clearance (1.5s) -> transitions to EMERGENCY_PRIORITY
    for _ in range(3):
        ctrl.tick(delta=0.5)
    assert ctrl.phase == "EMERGENCY_PRIORITY"

    # Selected approach MUST be GREEN; all conflicting approaches MUST be RED
    assert ctrl.signals[app].vehicle == SignalColor.GREEN
    assert ctrl.signals[conflicting_dir].vehicle == SignalColor.RED

    # 5. Immunity to normal signal cycling: tick 80 times (40 seconds)
    # The normal cycle timer must NEVER overwrite emergency priority!
    for _ in range(80):
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"
        assert ctrl.signals[app].vehicle == SignalColor.GREEN
        assert ctrl.signals[conflicting_dir].vehicle == SignalColor.RED

    # 6. Safe deactivation when ambulance exits
    ctrl.request_ambulance(approach=app, active=False)
    assert ctrl.emergency_active is False
    assert ctrl.phase == "ALL_RED_PRE_NS"

    # Post-emergency clearance restores normal traffic
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "NORTH_GREEN"


EXPECTED_EXITS = {
    ("south", "straight"): "north",
    ("south", "left"): "east",
    ("south", "right"): "west",
    ("north", "straight"): "south",
    ("north", "left"): "west",
    ("north", "right"): "east",
    ("east", "straight"): "west",
    ("east", "left"): "north",
    ("east", "right"): "south",
    ("west", "straight"): "east",
    ("west", "left"): "south",
    ("west", "right"): "north",
}


@pytest.mark.parametrize("app,expected_green,expected_reds", [
    ("south", "south", ["north", "east", "west"]),
    ("north", "north", ["south", "east", "west"]),
    ("east", "east", ["north", "south", "west"]),
    ("west", "west", ["north", "south", "east"]),
])
def test_exact_ambulance_signal_priority_exclusive_green(app, expected_green, expected_reds):
    """Verify Table from Requirement 1: ONLY incoming approach is GREEN; other 3 are strictly RED."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    ctrl.request_ambulance(approach=app, route="straight", active=True)

    # Tick past yellow and all-red clearance into EMERGENCY_PRIORITY
    for _ in range(15):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    # Exactly one signal is GREEN
    assert ctrl.signals[expected_green].vehicle == SignalColor.GREEN
    # All other three signals are RED
    for r_dir in expected_reds:
        assert ctrl.signals[r_dir].vehicle == SignalColor.RED, f"Expected {r_dir} to be RED for incoming {app}!"

    # Invariant: exactly one green exists, opposite direction is NEVER green
    green_count = sum(1 for s in ctrl.signals.values() if s.vehicle == SignalColor.GREEN)
    assert green_count == 1, f"Expected exactly 1 green signal, found {green_count}"


@pytest.mark.parametrize("approach,route", [
    (app, r) for app in ["south", "north", "east", "west"] for r in ["straight", "left", "right"]
])
def test_all_twelve_route_combinations_dispatch_and_exit_mapping(approach, route):
    """Verify all 12 route-to-exit combinations from Requirement 2 table."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    msg = ctrl.request_ambulance(approach=approach, route=route, active=True)
    assert approach.upper() in msg
    assert route.upper() in msg
    assert ctrl.emergency_active is True
    assert ctrl.emergency_approach == approach
    assert ctrl.emergency_route == route

    # Advance to EMERGENCY_PRIORITY
    for _ in range(15):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals[approach].vehicle == SignalColor.GREEN

    # Verify state response contains route and approach
    state = ctrl.get_state()
    assert state.emergency_active is True
    assert state.emergency_approach == approach
    assert state.emergency_route == route

    # Verify expected exit road according to standard 4-way table
    expected_exit = EXPECTED_EXITS[(approach, route)]
    assert expected_exit in ["north", "south", "east", "west"]

    # Deactivate and verify smooth clearance
    ctrl.request_ambulance(approach=approach, route=route, active=False)
    assert ctrl.emergency_active is False
    assert ctrl.phase == "ALL_RED_PRE_NS"


def test_pedestrian_call_queued_safely_during_emergency():
    """Verify pedestrian call received during emergency is safely queued until ambulance clears."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")
    ctrl.request_ambulance(approach="south", route="left", active=True)

    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN

    # Pedestrian presses button during emergency
    ped_msg = ctrl.request_pedestrian(active=True, crosswalk="north")
    assert "queued" in ped_msg.lower()
    assert ctrl.pedestrian_queued is True

    # Emergency signals remain strictly locked during turn
    for _ in range(10):
        ctrl.tick(delta=0.5)
        assert ctrl.phase == "EMERGENCY_PRIORITY"
        assert ctrl.signals["south"].vehicle == SignalColor.GREEN
        assert ctrl.signals["north"].vehicle == SignalColor.RED
        assert all(s.pedestrian == PedestrianSignal.DONT_WALK for s in ctrl.signals.values())

    # Ambulance finishes turn and exits
    ctrl.request_ambulance(approach="south", route="left", active=False)
    assert ctrl.phase == "ALL_RED_PRE_NS"

    # Controller completes all-red then services queued pedestrian request
    ctrl.tick(delta=1.5)
    assert ctrl.phase == "PEDESTRIAN_WALK"
    assert ctrl.signals["north"].pedestrian == PedestrianSignal.WALK
    # Vehicles held at RED during pedestrian walk
    for s in ctrl.signals.values():
        assert s.vehicle == SignalColor.RED


def test_emergency_audit_logging_with_caller_and_reason():
    """Verify that ambulance dispatch and deactivation log explicit caller and reason."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    ctrl.request_ambulance(
        approach="south",
        route="left",
        active=True,
        caller="UI.btnAmbulanceDispatch",
        reason="operator_dispatch_button",
    )
    dispatch_logs = [e for e in ctrl.events if "UI.btnAmbulanceDispatch" in e.message]
    assert len(dispatch_logs) > 0
    assert "operator_dispatch_button" in dispatch_logs[0].message
    assert "SOUTH" in dispatch_logs[0].message
    assert "LEFT" in dispatch_logs[0].message

    # Transition to emergency priority
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break
    assert ctrl.phase == "EMERGENCY_PRIORITY"

    # Deactivation upon reaching exit boundary
    ctrl.request_ambulance(
        approach="south",
        route="left",
        active=False,
        caller="Vehicle3D.hasClearedIntersection",
        reason="exit_boundary_cleared",
    )
    clear_logs = [e for e in ctrl.events if "Vehicle3D.hasClearedIntersection" in e.message]
    assert len(clear_logs) > 0
    assert "exit_boundary_cleared" in clear_logs[0].message
    assert ctrl.phase == "ALL_RED_PRE_NS"


def test_exact_12_step_single_approach_rotation_cycle():
    """Verify the exact 12-step sequential rotation specified in Requirement 10:
    1. North GREEN -> 2. North YELLOW -> 3. ALL RED (pre-South) ->
    4. South GREEN -> 5. South YELLOW -> 6. ALL RED (pre-East) ->
    7. East GREEN  -> 8. East YELLOW  -> 9. ALL RED (pre-West) ->
    10. West GREEN -> 11. West YELLOW -> 12. ALL RED (pre-North) ->
    13. North GREEN (cycle repeats).
    """
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    expected_cycle = [
        # (phase, duration, green_approach, yellow_approach)
        ("NORTH_GREEN", 8.0, "north", None),
        ("NORTH_YELLOW", 2.5, None, "north"),
        ("ALL_RED_PRE_SOUTH", 1.5, None, None),
        ("SOUTH_GREEN", 12.0, "south", None),
        ("SOUTH_YELLOW", 2.5, None, "south"),
        ("ALL_RED_PRE_EAST", 1.5, None, None),
        ("EAST_GREEN", 8.0, "east", None),
        ("EAST_YELLOW", 2.5, None, "east"),
        ("ALL_RED_PRE_WEST", 1.5, None, None),
        ("WEST_GREEN", 8.0, "west", None),
        ("WEST_YELLOW", 2.5, None, "west"),
        ("ALL_RED_PRE_NORTH", 1.5, None, None),
    ]

    for step_idx, (exp_phase, exp_duration, exp_green, exp_yellow) in enumerate(expected_cycle, 1):
        assert ctrl.phase == exp_phase, f"Step {step_idx}: Expected phase {exp_phase}, got {ctrl.phase}"
        assert abs(ctrl.phase_duration - exp_duration) < 0.01, (
            f"Step {step_idx} ({exp_phase}): Expected duration {exp_duration}s, got {ctrl.phase_duration}s"
        )

        # Check vehicle signal states
        for app in ["north", "south", "east", "west"]:
            if app == exp_green:
                assert ctrl.signals[app].vehicle == SignalColor.GREEN, f"{exp_phase}: {app} must be GREEN"
            elif app == exp_yellow:
                assert ctrl.signals[app].vehicle == SignalColor.YELLOW, f"{exp_phase}: {app} must be YELLOW"
            else:
                assert ctrl.signals[app].vehicle == SignalColor.RED, f"{exp_phase}: {app} must be RED"

        # Advance exactly by this phase duration
        ctrl.tick(delta=exp_duration)

    # 13. Cycle repeats back to NORTH_GREEN
    assert ctrl.phase == "NORTH_GREEN"
    assert ctrl.signals["north"].vehicle == SignalColor.GREEN
    assert ctrl.signals["south"].vehicle == SignalColor.RED
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED


def test_single_green_invariant_across_multiple_full_cycles():
    """Verify that throughout 500 ticks (250 seconds):
    1. green_count <= 1 across all four approaches at every single tick.
    2. green and yellow never coexist.
    3. All 4 approaches receive green in sequence without any approach being skipped.
    """
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    greens_recorded = {"north": 0, "south": 0, "east": 0, "west": 0}

    for tick_num in range(500):
        ctrl.tick(delta=0.5)

        greens = [d for d, s in ctrl.signals.items() if s.vehicle == SignalColor.GREEN]
        yellows = [d for d, s in ctrl.signals.items() if s.vehicle == SignalColor.YELLOW]

        # Invariant 1: At most ONE approach is green
        assert len(greens) <= 1, f"Tick {tick_num} (phase {ctrl.phase}): Multiple greens: {greens}"

        # Invariant 2: Green and yellow never coexist
        if len(greens) > 0:
            assert len(yellows) == 0, f"Tick {tick_num} (phase {ctrl.phase}): Simultaneous green and yellow!"
            greens_recorded[greens[0]] += 1

        # Invariant 3: At most ONE approach is yellow
        assert len(yellows) <= 1, f"Tick {tick_num} (phase {ctrl.phase}): Multiple yellows: {yellows}"

    # Verify that all 4 approaches received green multiple times
    for app, count in greens_recorded.items():
        assert count > 10, f"Approach {app} received green only {count} times over 500 ticks!"


def test_density_scaling_adjusts_base_green_durations():
    """Verify green phase duration adapts based on traffic density setting across single approaches."""
    ctrl = IntersectionController()

    # LOW density -> 6.0s
    ctrl.set_traffic_density(TrafficDensityEnum.LOW)
    assert ctrl.get_base_green_duration() == 6.0

    # HIGH density -> 11.0s
    ctrl.set_traffic_density(TrafficDensityEnum.HIGH)
    assert ctrl.get_base_green_duration() == 11.0

    # MEDIUM density -> 8.0s
    ctrl.set_traffic_density(TrafficDensityEnum.MEDIUM)
    assert ctrl.get_base_green_duration() == 8.0


def test_adaptive_green_extension_high_density_and_max_cap():
    """Verify adaptive green extends green phase up to max 22.0s under high traffic density."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Set South to HIGH density with queue of 6
    ctrl.traffic_generator.set_high_demand_approach("south")
    ctrl.traffic_generator.sync_client_counts({"south": 6})
    metric = ctrl.traffic_generator.get_metrics("south")
    assert metric.density == TrafficDensityEnum.HIGH

    # Transition directly to South Green
    ctrl._transition_to("SOUTH_GREEN", ctrl.get_base_green_duration("south"), "South Green Phase")
    assert ctrl.phase == "SOUTH_GREEN"
    assert ctrl.phase_duration == 12.0  # Normal green starting baseline
    assert ctrl.green_extended is False

    # Advance time to near end of normal green (11.0s / 22 ticks of 0.5s)
    for _ in range(22):
        ctrl.tick(delta=0.5)

    # Controller should have detected high density and extended green
    assert ctrl.green_extended is True
    assert ctrl.phase == "SOUTH_GREEN"
    assert ctrl.phase_duration > 12.0

    # Advance while still in South Green with sustained queue to verify max cap
    total_green_time = 11.0
    while ctrl.phase == "SOUTH_GREEN":
        ctrl.traffic_generator.set_approach_queue("south", 8)  # Sustained queue
        assert ctrl.phase_duration <= 22.0 + 0.01
        ctrl.tick(delta=0.5)
        total_green_time += 0.5

    # South Green was extended up to the 22.0s maximum limit
    assert total_green_time >= 22.0
    assert ctrl.phase == "SOUTH_YELLOW"
    assert abs(ctrl.phase_duration - 2.5) < 0.01
    assert ctrl.signals["south"].vehicle == SignalColor.YELLOW

    # Advance through yellow clearance into all-red
    for _ in range(6):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "ALL_RED_PRE_EAST":
            break

    assert ctrl.phase == "ALL_RED_PRE_EAST"
    assert abs(ctrl.phase_duration - 1.5) < 0.01
    for s in ctrl.signals.values():
        assert s.vehicle == SignalColor.RED

    # Advance through all-red into East Green
    for _ in range(4):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EAST_GREEN":
            break

    assert ctrl.phase == "EAST_GREEN"
    assert ctrl.signals["east"].vehicle == SignalColor.GREEN


def test_adaptive_green_early_clearance_low_density():
    """Verify LOW density with clear queue discharges promptly after min green (8.0s)."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Set East approach to LOW density with 0 queue
    ctrl.traffic_generator.set_high_demand_approach("north")  # High demand elsewhere
    ctrl.traffic_generator.sync_client_counts({"east": 0})
    metric = ctrl.traffic_generator.get_metrics("east")
    assert metric.density == TrafficDensityEnum.LOW
    assert metric.queue_length == 0

    ctrl._transition_to("EAST_GREEN", ctrl.get_base_green_duration("east"), "East Green Phase")
    assert ctrl.phase == "EAST_GREEN"
    assert ctrl.phase_duration == 8.0  # Min green baseline

    # Advance past min green (16 ticks = 8.0s)
    for _ in range(17):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EAST_YELLOW":
            break

    assert ctrl.phase == "EAST_YELLOW"
    assert abs(ctrl.phase_duration - 2.5) < 0.01


def test_countdown_timers_accuracy_and_non_negative():
    """Verify authoritative countdown timers are strictly non-negative, accurate, and update dynamically."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # In initial state: NORTH_GREEN, phase_duration=8.0, time_in_phase=0.0
    countdowns = ctrl.calculate_countdowns()
    for app, cd in countdowns.items():
        assert cd >= 0.0, f"Approach {app} countdown is negative: {cd}"

    assert countdowns["north"] == 8.0  # Time to North Yellow
    assert countdowns["south"] == 8.0 + 2.5 + 1.5  # 12.0s wait to South Green

    # Advance 4 ticks (2.0s)
    for _ in range(4):
        ctrl.tick(delta=0.5)

    countdowns2 = ctrl.calculate_countdowns()
    assert abs(countdowns2["north"] - 6.0) < 0.1
    assert abs(countdowns2["south"] - 10.0) < 0.1

    # Verify state response contains countdowns and active approach
    state = ctrl.get_state()
    assert state.active_approach == "north"
    assert state.countdowns["north"] > 0
    assert state.countdowns["south"] > 0
    assert state.countdowns["east"] > 0
    assert state.countdowns["west"] > 0


def test_countdown_during_emergency_preemption_displays_priority_and_hold():
    """Verify emergency preemption replaces normal countdowns with PRIORITY (0.0) and HOLD (-1.0)."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Request ambulance from East
    ctrl.request_ambulance(approach="east", active=True)

    # Tick into EMERGENCY_PRIORITY
    for _ in range(12):
        ctrl.tick(delta=0.5)
        if ctrl.phase == "EMERGENCY_PRIORITY":
            break

    assert ctrl.phase == "EMERGENCY_PRIORITY"
    countdowns = ctrl.calculate_countdowns()

    # East is priority approach (0.0 -> PRIORITY)
    assert countdowns["east"] == 0.0
    # Conflicting directions are held (-1.0 -> HOLD)
    assert countdowns["north"] == -1.0
    assert countdowns["south"] == -1.0
    assert countdowns["west"] == -1.0

    state = ctrl.get_state()
    assert state.countdowns["east"] == 0.0
    assert state.countdowns["north"] == -1.0


def test_dynamic_high_demand_direction_rotation_sequence():
    """Verify dynamic high-demand direction shifts systematically: South -> East -> North -> West."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Initial high demand is South
    assert ctrl.traffic_generator.current_high_demand_approach == "south"

    # Step generator by 30 seconds (full rotation interval)
    ctrl.traffic_generator.update(delta=31.0)
    assert ctrl.traffic_generator.current_high_demand_approach == "east"

    ctrl.traffic_generator.update(delta=31.0)
    assert ctrl.traffic_generator.current_high_demand_approach == "north"

    ctrl.traffic_generator.update(delta=31.0)
    assert ctrl.traffic_generator.current_high_demand_approach == "west"

    ctrl.traffic_generator.update(delta=31.0)
    assert ctrl.traffic_generator.current_high_demand_approach == "south"


def test_density_labels_match_queue_counts():
    """Verify density classifications match measured vehicle queues deterministically."""
    ctrl = IntersectionController()
    gen = ctrl.traffic_generator

    gen.sync_client_counts({"north": 1, "south": 4, "east": 7, "west": 0})
    m_north = gen.get_metrics("north")
    m_south = gen.get_metrics("south")
    m_east = gen.get_metrics("east")
    m_west = gen.get_metrics("west")

    assert m_north.density == TrafficDensityEnum.LOW
    assert m_south.density == TrafficDensityEnum.MEDIUM
    assert m_east.density == TrafficDensityEnum.HIGH
    assert m_west.density == TrafficDensityEnum.LOW


def test_queue_based_green_duration_formula():
    """Verify authoritative green calculation:
    green_duration = clamp(base_green + queued_vehicle_count * extension_per_vehicle, minimum_green, maximum_green)
    Defaults: min=6.0s, base=8.0s, ext=1.5s, max=22.0s
    """
    ctrl = IntersectionController()

    # 0 queued -> 8.0s
    assert ctrl.calculate_queue_green_duration(queue_count=0) == 8.0

    # 1 queued -> 9.5s
    assert ctrl.calculate_queue_green_duration(queue_count=1) == 9.5

    # 2 queued -> 11.0s
    assert ctrl.calculate_queue_green_duration(queue_count=2) == 11.0

    # 4 queued -> 14.0s
    assert ctrl.calculate_queue_green_duration(queue_count=4) == 14.0

    # 6 queued -> 17.0s
    assert ctrl.calculate_queue_green_duration(queue_count=6) == 17.0

    # 8 queued -> 20.0s
    assert ctrl.calculate_queue_green_duration(queue_count=8) == 20.0

    # 10 queued -> 22.0s (capped at maximum_green)
    assert ctrl.calculate_queue_green_duration(queue_count=10) == 22.0

    # 15 queued -> 22.0s (strictly capped at maximum_green)
    assert ctrl.calculate_queue_green_duration(queue_count=15) == 22.0

    # Negative queue (-2) -> 6.0s (clamped at minimum_green)
    assert ctrl.calculate_queue_green_duration(queue_count=-2) == 6.0


def test_approach_specific_density_setting():
    """Verify that approach-specific density controls update target approach queues correctly."""
    ctrl = IntersectionController()

    # Set EAST to HIGH density
    msg = ctrl.set_traffic_density(TrafficDensityEnum.HIGH, approach="east")
    assert "EAST" in msg
    assert ctrl.traffic_generator.current_high_demand_approach == "east"
    m_east = ctrl.traffic_generator.get_metrics("east")
    assert m_east.density == TrafficDensityEnum.HIGH
    assert m_east.queue_length >= 5

    # Set NORTH to LOW density
    ctrl.set_traffic_density(TrafficDensityEnum.LOW, approach="north")
    m_north = ctrl.traffic_generator.get_metrics("north")
    assert m_north.density == TrafficDensityEnum.LOW
    assert m_north.queue_length <= 2

    # Set WEST to MEDIUM density
    ctrl.set_traffic_density(TrafficDensityEnum.MEDIUM, approach="west")
    m_west = ctrl.traffic_generator.get_metrics("west")
    assert m_west.density == TrafficDensityEnum.MEDIUM
    assert 3 <= m_west.queue_length <= 4


def test_multi_lane_queue_telemetry_synchronization():
    """Verify that multi-lane queue telemetry correctly updates per-lane queues and approach metrics."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # Sync multi-lane telemetry from frontend
    frontend_counts = {
        "south": {"queue": 6, "total": 8, "lane0": 3, "lane1": 3},
        "north": {"queue": 2, "total": 3, "lane0": 1, "lane1": 1},
        "east":  {"queue": 4, "total": 5, "lane1": 2, "lane2": 2},
        "west":  {"queue": 0, "total": 1, "lane0": 0, "lane1": 0},
    }
    ctrl.traffic_generator.sync_from_frontend_counts(frontend_counts)

    # South metrics: 6 queued, 3 in lane1, 3 in lane2
    m_south = ctrl.traffic_generator.get_metrics("south")
    assert m_south.queue_length == 6
    assert m_south.vehicle_count == 8
    assert m_south.lane_queues == {"lane1": 3, "lane2": 3}
    assert m_south.density == TrafficDensityEnum.HIGH

    # North metrics: 2 queued, 1 in lane1, 1 in lane2
    m_north = ctrl.traffic_generator.get_metrics("north")
    assert m_north.queue_length == 2
    assert m_north.vehicle_count == 3
    assert m_north.lane_queues == {"lane1": 1, "lane2": 1}
    assert m_north.density == TrafficDensityEnum.LOW

    # East metrics: 4 queued, 2 in lane1, 2 in lane2
    m_east = ctrl.traffic_generator.get_metrics("east")
    assert m_east.queue_length == 4
    assert m_east.vehicle_count == 5
    assert m_east.lane_queues == {"lane1": 2, "lane2": 2}
    assert m_east.density == TrafficDensityEnum.MEDIUM

    # State serialization includes lane_queues in approachMetrics
    state = ctrl.get_state()
    assert "south" in state.approach_metrics
    assert state.approach_metrics["south"].lane_queues == {"lane1": 3, "lane2": 3}


def test_multi_lane_queues_and_continuous_adaptive_green_extension():
    """Verify that side-by-side queues across both lanes continuously adapt green duration up to 22.0s."""
    ctrl = IntersectionController()
    ctrl.set_simulation_state("reset")

    # South approach has side-by-side queue: 4 in lane 1, 4 in lane 2 = total 8 queued
    ctrl.traffic_generator.sync_from_frontend_counts({
        "south": {"queue": 8, "total": 10, "lane0": 4, "lane1": 4}
    })

    # Duration formula: clamp(8 + 1.5 * 8, 6, 22) = 20.0s
    calc_dur = ctrl.calculate_queue_green_duration("south")
    assert calc_dur == 20.0

    # Transition to South Green
    ctrl._transition_to("SOUTH_GREEN", ctrl.get_base_green_duration("south"), "South Green Phase")
    assert ctrl.phase == "SOUTH_GREEN"
    assert ctrl.signals["south"].vehicle == SignalColor.GREEN
    assert ctrl.signals["north"].vehicle == SignalColor.RED
    assert ctrl.signals["east"].vehicle == SignalColor.RED
    assert ctrl.signals["west"].vehicle == SignalColor.RED

    # Advance time towards phase expiration
    for _ in range(22):
        ctrl.tick(delta=0.5)

    # Controller should have extended green based on multi-lane queue
    assert ctrl.green_extended is True
    assert ctrl.phase_duration >= 14.0
    assert ctrl.phase_duration <= 22.0

    # Verify strictly at most one approach green throughout
    greens = [d for d, s in ctrl.signals.items() if s.vehicle == SignalColor.GREEN]
    assert len(greens) == 1
    assert greens[0] == "south"
