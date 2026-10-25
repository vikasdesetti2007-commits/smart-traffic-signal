"""End-to-end browser verification of all 12 ambulance route combinations using Playwright."""

import asyncio
import os
import sys
import math
from playwright.async_api import async_playwright

EXPECTED_EXITS = {
    ("south", "straight"): ("north", "z", -17.9, -1, math.pi),
    ("south", "left"):     ("east",  "x", 17.9,  1,  math.pi / 2),
    ("south", "right"):    ("west",  "x", -17.9, -1, -math.pi / 2),

    ("north", "straight"): ("south", "z", 17.9,  1,  0.0),
    ("north", "left"):     ("west",  "x", -17.9, -1, -math.pi / 2),
    ("north", "right"):    ("east",  "x", 17.9,  1,  math.pi / 2),

    ("east", "straight"):  ("west",  "x", -17.9, -1, -math.pi / 2),
    ("east", "left"):      ("north", "z", -17.9, -1, math.pi),
    ("east", "right"):     ("south", "z", 17.9,  1,  0.0),

    ("west", "straight"):  ("east",  "x", 17.9,  1,  math.pi / 2),
    ("west", "left"):      ("south", "z", 17.9,  1,  0.0),
    ("west", "right"):     ("north", "z", -17.9, -1, math.pi),
}

async def run_verification():
    print("=== Starting 12-Route Browser Automation Verification ===")
    results = {}
    
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
        
        # Navigate to application
        await page.goto("http://localhost:8000/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        # Verify page loaded
        title = await page.title()
        print(f"Loaded page: {title}")
        
        # Set speed to fast (80 km/h) for snappy animation testing
        btn_fast = page.locator("#btnSpeedFast")
        if await btn_fast.count() > 0:
            await btn_fast.click()
            await page.wait_for_timeout(500)
            print("Speed preset set to Fast (80 km/h).")

        approaches = ["south", "north", "east", "west"]
        routes = ["straight", "left", "right"]

        for approach in approaches:
            for route in routes:
                test_key = f"{approach.upper()} -> {route.upper()}"
                expected_exit, coord_axis, threshold, sign, exp_heading = EXPECTED_EXITS[(approach, route)]
                print(f"\n--- Testing: {test_key} (Expected Exit: {expected_exit.upper()}) ---")

                # Select approach and route
                await page.select_option("#ambulanceApproach", approach)
                await page.select_option("#ambulanceRoute", route)
                await page.wait_for_timeout(300)

                # Click Dispatch Ambulance
                await page.click("#btnAmbulanceDispatch")

                # Wait for EMERGENCY_PRIORITY phase and exclusive signals
                phase_granted = False
                last_phase = "UNKNOWN"
                for _ in range(40): # up to 8 seconds
                    phase_info = await page.evaluate("""() => {
                        const s = window.state || {};
                        return {
                            phase: s.phase,
                            emergencyActive: s.emergencyActive,
                            approach: s.emergencyApproach,
                            route: s.emergencyRoute,
                            signals: s.signals
                        };
                    }""")
                    last_phase = phase_info.get("phase")
                    if last_phase == "EMERGENCY_PRIORITY":
                        phase_granted = True
                        break
                    await page.wait_for_timeout(200)

                if not phase_granted:
                    print(f"FAILED: {test_key} did not reach EMERGENCY_PRIORITY (last phase: {last_phase})")
                    results[test_key] = {"status": "FAIL", "reason": f"Timeout waiting for EMERGENCY_PRIORITY (phase: {last_phase})"}
                    continue

                # Verify exclusive signals in browser state
                signals = phase_info.get("signals", {})
                green_signals = [d for d, s in signals.items() if s.get("vehicle") == "GREEN"]
                red_signals = [d for d, s in signals.items() if s.get("vehicle") == "RED"]
                
                is_exclusive = (green_signals == [approach]) and (len(red_signals) == 3)
                if not is_exclusive:
                    print(f"FAILED: {test_key} signals not exclusive! Green: {green_signals}, Red: {red_signals}")
                    results[test_key] = {"status": "FAIL", "reason": f"Signals not exclusive: {green_signals}"}
                    continue
                else:
                    print(f"Signals verified: ONLY {approach.upper()} is GREEN; all 3 others RED.")

                # Track 3D ambulance movement until it reaches exit
                reached_exit = False
                final_pos = None
                final_heading = None
                trajectory = []

                for _ in range(50): # up to 10 seconds of driving
                    amb_data = await page.evaluate("""() => {
                        const v = (window.vehicles3D || []).find(veh => veh.isAmbulance);
                        if (!v || !v.mesh) return null;
                        return {
                            x: v.mesh.position.x,
                            z: v.mesh.position.z,
                            heading: v.mesh.rotation.y,
                            speed: v.speed,
                            hasTurned: v.hasTurned,
                            hasCleared: v.hasCleared,
                            exitRoad: v.exitRoad
                        };
                    }""")

                    if amb_data:
                        trajectory.append((amb_data["x"], amb_data["z"]))
                        final_pos = (amb_data["x"], amb_data["z"])
                        final_heading = amb_data["heading"]

                        # Check if vehicle crossed the exit threshold
                        val = amb_data[coord_axis]
                        if sign > 0 and val >= threshold:
                            reached_exit = True
                            break
                        elif sign < 0 and val <= threshold:
                            reached_exit = True
                            break
                    await page.wait_for_timeout(200)

                # Check heading alignment: diff from exp_heading
                heading_err = None
                if final_heading is not None:
                    heading_err = abs((final_heading - exp_heading + math.pi) % (2 * math.pi) - math.pi)

                if reached_exit:
                    print(f"PASSED: Reached {expected_exit.upper()} exit! Final pos: ({final_pos[0]:.1f}, {final_pos[1]:.1f}), Heading: {final_heading:.2f} rad (err={heading_err:.3f} rad)")
                    results[test_key] = {
                        "status": "PASS",
                        "approach": approach,
                        "route": route,
                        "exit": expected_exit,
                        "final_pos": final_pos,
                        "heading_err": heading_err
                    }
                else:
                    print(f"FAILED: Did not reach exit within time. Last pos: {final_pos}")
                    results[test_key] = {
                        "status": "FAIL",
                        "reason": f"Did not reach {expected_exit} exit. Last pos: {final_pos}"
                    }

                # Allow ambulance to clear and normal traffic to restore before next test
                await page.wait_for_timeout(2000)

        await browser.close()

    print("\n================= 12-ROUTE SUMMARY =================")
    pass_count = sum(1 for r in results.values() if r["status"] == "PASS")
    total_count = len(results)
    for k, v in results.items():
        print(f"[{v['status']}] {k}: Exit={v.get('exit', 'N/A')}")
    print(f"\nTotal: {pass_count}/{total_count} PASSED")
    if pass_count == total_count:
        print("ALL 12 COMBINATIONS VERIFIED IN BROWSER WITH 100% SUCCESS!")
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_verification())
