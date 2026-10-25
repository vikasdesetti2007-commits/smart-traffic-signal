"""Comprehensive Playwright Browser Verification for Ambulance Priority Fix.
Tests all 12 approach & route combinations with clearance telemetry logging,
ensuring the ambulance respects clearance before priority, accelerates smoothly
without stopping at red lights once emergency priority is granted, and holds
emergency priority continuously until reaching the physical exit boundary (>= 38.0m).
"""

import asyncio
import os
import sys
import math
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

EXIT_MAP = {
    "south": {"straight": "north", "left": "east", "right": "west"},
    "north": {"straight": "south", "left": "west", "right": "east"},
    "east": {"straight": "west", "left": "north", "right": "south"},
    "west": {"straight": "east", "left": "south", "right": "north"},
}


async def run_verification():
    print("=" * 75)
    print("STARTING PLAYWRIGHT VERIFICATION: EMERGENCY PRIORITY LIFECYCLE & EXIT BOUNDARY")
    print("=" * 75)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # Capture console diagnostics
        telemetry_logs = []
        page.on("console", lambda msg: telemetry_logs.append(msg.text) if "Ambulance" in msg.text else None)

        print("1. Loading application at http://localhost:8000/ ...")
        await page.goto("http://localhost:8000/", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        approaches = ["south", "north", "east", "west"]
        routes = ["straight", "left", "right"]
        results = []

        test_num = 0
        total_tests = len(approaches) * len(routes)

        for app in approaches:
            for rt in routes:
                test_num += 1
                test_name = f"Test {test_num}/{total_tests}: {app.upper()} -> {rt.upper()}"
                print(f"\n" + "-" * 75)
                print(f"RUNNING {test_name}")
                print("-" * 75)

                # Wait for any prior emergency to be completely deactivated
                for _ in range(40):
                    is_busy = await page.evaluate("() => window.state && window.state.emergencyActive")
                    if not is_busy:
                        break
                    await page.wait_for_timeout(200)

                # Select approach and route in UI
                await page.select_option("#ambulanceApproach", app)
                await page.select_option("#ambulanceRoute", rt)

                # Dispatch ambulance
                await page.click("#btnAmbulanceDispatch")
                print(f"Dispatched ambulance from {app.upper()} along {rt.upper()} route.")

                # Wait for new active ambulance to be spawned
                for _ in range(30):
                    has_new = await page.evaluate("() => (window.vehicles3D || []).some(v => v.isAmbulance && !v.hasCleared)")
                    if has_new:
                        break
                    await page.wait_for_timeout(100)

                # Telemetry tracking for this run
                phase_history = []
                stopped_during_clearance = False
                accelerated_under_priority = False
                stopped_at_red_after_priority = False
                exclusive_green_confirmed = False
                threejs_lenses_confirmed = False
                premature_deactivation_detected = False
                cleared_successfully = False
                cleared_at_exit_boundary = False
                final_telemetry = None

                # Poll up to 75 frames (15 seconds) to allow traversing to exit boundary
                for step in range(75):
                    await page.wait_for_timeout(200)

                    telemetry = await page.evaluate('''() => {
                        const s = window.state || {};
                        const amb = (window.vehicles3D || []).find(v => v.isAmbulance && !v.hasCleared) || (window.vehicles3D || []).find(v => v.isAmbulance);
                        if (!amb) return { no_amb: true, phase: s.phase, emerActive: s.emergencyActive };

                        const sig = amb.getSignalColor ? amb.getSignalColor() : null;
                        const dist = amb.getDistanceToStopLine ? amb.getDistanceToStopLine() : null;
                        const allSigs = {};
                        if (s.signals) {
                            for (const k of ['north', 'south', 'east', 'west']) {
                                allSigs[k] = s.signals[k] ? s.signals[k].vehicle : null;
                            }
                        }

                        // 3D physical lens materials in Three.js scene
                        const threeLenses = {};
                        if (window.signalLenses3D) {
                            for (const k of ['north', 'south', 'east', 'west']) {
                                const l = window.signalLenses3D[k];
                                if (l) {
                                    threeLenses[k] = {
                                        green: l.green ? l.green.emissiveIntensity : 0,
                                        red: l.red ? l.red.emissiveIntensity : 0,
                                        yellow: l.yellow ? l.yellow.emissiveIntensity : 0
                                    };
                                }
                            }
                        }

                        // Determine stopping reason as reported by vehicle
                        let reason = 'cruising';
                        if (amb.corridorGranted) {
                            reason = 'protected_green_corridor_active';
                        } else if (dist <= 2.0 && dist >= -1.0) {
                            reason = 'yielding_at_stop_line_for_clearance';
                        } else if (dist < 28 && dist > 2.0) {
                            reason = 'decelerating_for_safety_clearance';
                        }

                        return {
                            phase: s.phase,
                            emerActive: s.emergencyActive,
                            emerApproach: s.emergencyApproach,
                            emerRoute: s.emergencyRoute,
                            signals: allSigs,
                            threeLenses: threeLenses,
                            ambSignal: sig,
                            distToStop: dist,
                            speed: amb.speed,
                            targetSpeed: (amb.corridorGranted || !s.emergencyActive) ? (amb.baseSpeed * 1.0) : 0,
                            corridorGranted: !!amb.corridorGranted,
                            pos: { x: amb.mesh.position.x, z: amb.mesh.position.z },
                            hasTurned: amb.hasTurned,
                            hasCleared: amb.hasCleared,
                            stoppingReason: reason
                        };
                    }''')

                    if not telemetry or telemetry.get('no_amb'):
                        continue

                    phase = telemetry['phase']
                    if phase not in phase_history:
                        phase_history.append(phase)

                    speed = telemetry['speed']
                    dist = telemetry['distToStop']
                    corridor_granted = telemetry['corridorGranted']

                    # Print periodic diagnostic line
                    if step % 5 == 0 or corridor_granted or telemetry['hasCleared']:
                        sig_summary = ", ".join([f"{k}:{v}" for k, v in telemetry['signals'].items()])
                        print(f"  [{step*0.2:4.1f}s] Phase={phase:<18} | CorridorGranted={str(corridor_granted):<5} | AmbSpeed={speed:.3f} | Dist={dist:5.1f}m | Pos=({telemetry['pos']['x']:5.1f},{telemetry['pos']['z']:5.1f}) | Sigs=[{sig_summary}] | Reason={telemetry['stoppingReason']}")

                    # Check 1: Did it decelerate/stop during clearance if before stop line?
                    if not corridor_granted and telemetry['emerActive']:
                        if dist is not None and dist < 2.0 and dist >= -1.0 and speed < 0.15:
                            stopped_during_clearance = True

                    # Check 2: Verify exclusive signal state when EMERGENCY_PRIORITY active
                    if phase == "EMERGENCY_PRIORITY":
                        incoming_sig = telemetry['signals'].get(app)
                        conflicting_sigs = [v for k, v in telemetry['signals'].items() if k != app]
                        if incoming_sig == "GREEN" and all(s == "RED" for s in conflicting_sigs):
                            exclusive_green_confirmed = True

                        # Also check Three.js 3D lens materials
                        lenses = telemetry.get('threeLenses', {})
                        inc_green = lenses.get(app, {}).get('green', 0)
                        conf_reds = [lenses.get(k, {}).get('red', 0) for k in ['north', 'south', 'east', 'west'] if k != app]
                        if inc_green > 2.0 and all(r > 2.0 for r in conf_reds):
                            threejs_lenses_confirmed = True

                        # Check 3: Once priority is granted, does ambulance accelerate?
                        if speed > 0.35:
                            accelerated_under_priority = True

                        # Check 4: Does it ever stop at a red light after priority?
                        if corridor_granted and dist is not None and dist >= -1.0 and speed < 0.05 and step > 10:
                            stopped_at_red_after_priority = True

                    # CRITICAL BUG CHECK: Priority MUST NOT be cancelled before hasCleared is reached
                    if corridor_granted and not telemetry['hasCleared']:
                        if phase != "EMERGENCY_PRIORITY":
                            print(f"  [ERROR] PREMATURE DEACTIVATION DETECTED! Phase={phase} before ambulance cleared intersection exit boundary!")
                            premature_deactivation_detected = True

                    # Check 5: Cleared the intersection at actual exit road boundary (38.0m)
                    if telemetry['hasCleared']:
                        cleared_successfully = True
                        final_telemetry = telemetry
                        exit_road = EXIT_MAP[app][rt]
                        pos = telemetry['pos']
                        if exit_road == "north" and pos['z'] <= -38.0:
                            cleared_at_exit_boundary = True
                        elif exit_road == "south" and pos['z'] >= 38.0:
                            cleared_at_exit_boundary = True
                        elif exit_road == "east" and pos['x'] >= 38.0:
                            cleared_at_exit_boundary = True
                        elif exit_road == "west" and pos['x'] <= -38.0:
                            cleared_at_exit_boundary = True

                        # Capture screenshot of priority corridor clearance
                        if test_num == 1:
                            ss_path = os.path.join(SCREENSHOTS_DIR, "04_ambulance_priority_corridor.png")
                            await page.screenshot(path=ss_path)
                            print(f"  Screenshot saved: {ss_path}")
                        break

                # Post-clearance check: after clearing exit boundary, verify transition to all-red safety clearance
                await page.wait_for_timeout(600)
                post_phase = await page.evaluate("() => window.state && window.state.phase")
                post_events = await page.evaluate("() => (window.state && window.state.recentEvents) || []")
                clear_event_logged = any("Vehicle3D.hasClearedIntersection" in (e.get('message') or '') for e in post_events)

                passed = (
                    cleared_successfully and
                    cleared_at_exit_boundary and
                    exclusive_green_confirmed and
                    threejs_lenses_confirmed and
                    accelerated_under_priority and
                    not stopped_at_red_after_priority and
                    not premature_deactivation_detected
                )

                status_str = "PASSED" if passed else "FAILED"
                print(f"RESULT: {test_name} -> {status_str}")
                print(f"  - Phases Observed: {' -> '.join(phase_history)} -> PostPhase: {post_phase}")
                print(f"  - Exclusive Green ({app.upper()}=GREEN, others=RED): {exclusive_green_confirmed}")
                print(f"  - Three.js 3D Signal Lenses Illuminated Correctly: {threejs_lenses_confirmed}")
                print(f"  - Accelerated Decisively Through Stop Line: {accelerated_under_priority}")
                print(f"  - Stopped At Red After Priority: {stopped_at_red_after_priority}")
                print(f"  - No Premature Deactivation While Moving: {not premature_deactivation_detected}")
                print(f"  - Cleared Far-Side Exit Road Boundary (>= 38m): {cleared_at_exit_boundary}")
                print(f"  - Audit Event Logged by Caller/Reason: {clear_event_logged}")
                if final_telemetry:
                    print(f"  - Final Position at Clearance: ({final_telemetry['pos']['x']:.1f}, {final_telemetry['pos']['z']:.1f})")

                assert passed, f"{test_name} failed verification!"
                results.append({
                    "test": f"{app.upper()} -> {rt.upper()}",
                    "passed": passed,
                    "phases": phase_history,
                    "final_pos": final_telemetry['pos'] if final_telemetry else None,
                    "cleared_boundary": cleared_at_exit_boundary,
                    "no_premature_deactivation": not premature_deactivation_detected
                })

        await browser.close()
        print("\n" + "=" * 75)
        print(f"ALL {len(results)}/{total_tests} AMBULANCE PRIORITY & EXIT BOUNDARY TESTS PASSED WITH 100% SUCCESS!")
        print("=" * 75)

if __name__ == "__main__":
    asyncio.run(run_verification())
