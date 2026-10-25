import asyncio
import os
import sys
import time
from playwright.async_api import async_playwright

ARTIFACT_DIR = "/home/vikas/.gemini/antigravity-cli/brain/0f530f50-f953-42fa-aabb-208f0c295675"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def run_full_verification():
    print("=======================================================================")
    print("STARTING SMART TRAFFIC SIGNAL ANTI-GRIDLOCK & CLEARANCE VERIFICATION")
    print("=======================================================================")

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

        print("1. Connecting to http://localhost:8000 ...")
        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # ---------------------------------------------------------------------
        # TEST 1: SUBTITLE WRAPPING & RESPONSIVENESS
        # ---------------------------------------------------------------------
        print("\n--- TEST 1: Direction Subtitles & Text Wrapping Verification ---")
        sub_info = await page.evaluate("""() => {
            const getSub = id => {
                const el = document.querySelector(id);
                if (!el) return null;
                const cs = window.getComputedStyle(el);
                return {
                    text: el.textContent.trim(),
                    whiteSpace: cs.whiteSpace,
                    overflow: cs.overflow,
                    textOverflow: cs.textOverflow,
                    clientWidth: el.clientWidth,
                    scrollWidth: el.scrollWidth,
                    clientHeight: el.clientHeight,
                    scrollHeight: el.scrollHeight
                };
            };
            return {
                northHUD: getSub('#hudNorth .hud-sub'),
                southHUD: getSub('#hudSouth .hud-sub'),
                eastHUD: getSub('#hudEast .hud-sub'),
                westHUD: getSub('#hudWest .hud-sub'),
                northBadge: getSub('#badgeNorth .badge-sub'),
                southBadge: getSub('#badgeSouth .badge-sub'),
                eastBadge: getSub('#badgeEast .badge-sub'),
                westBadge: getSub('#badgeWest .badge-sub')
            };
        }""")
        print(f"North HUD Subtitle: text='{sub_info['northHUD']['text']}', whiteSpace={sub_info['northHUD']['whiteSpace']}")
        assert sub_info['northHUD']['whiteSpace'] == 'normal', f"HUD subtitle whitespace should be normal, got {sub_info['northHUD']['whiteSpace']}"
        assert sub_info['northHUD']['textOverflow'] != 'ellipsis', "HUD subtitle should not have ellipsis truncation"
        assert "Incoming from North, travelling southbound" in sub_info['northHUD']['text']
        print("✓ Approach subtitles wrap responsively onto two lines without truncation or ellipsis!")

        # ---------------------------------------------------------------------
        # TEST 2: HIGH-DENSITY RUNTIME SCENE TRACKING (Anti-Gridlock & Box Clearance)
        # ---------------------------------------------------------------------
        print("\n--- TEST 2: High-Density Anti-Gridlock & Box Clearance Tracking ---")
        await page.evaluate("""async () => {
            await apiControlSimulation('reset');
            await apiControlTraffic('high');
            burstSpawnVehicles('north', 3);
            burstSpawnVehicles('south', 3);
            burstSpawnVehicles('east', 3);
            burstSpawnVehicles('west', 3);
        }""")
        await page.wait_for_timeout(1000)

        metrics = {
            "samples": 0,
            "peak_vehicles": 0,
            "red_crosswalk_violations": 0,
            "red_box_violations": 0,
            "illegal_red_entries": 0,
            "min_dist_to_stop_on_red": 999.0,
            "sat_collision_events": 0,
            "deadlock_events": 0,
            "all_red_box_clearance_samples": 0
        }

        # Monitor over 40 samples (approx 20 seconds, ~2 full signal cycle transitions)
        for step in range(40):
            await page.wait_for_timeout(500)
            diag = await page.evaluate("""() => {
                const s = window.state || {};
                const sigs = s.signals || {};
                const vs = window.vehicles3D || [];
                const diags = window.getVehicleDiagnostics ? window.getVehicleDiagnostics() : [];

                const allRed = ['north', 'south', 'east', 'west'].every(k => sigs[k] && sigs[k].vehicle === 'RED');

                let satCollisions = 0;
                for (let i = 0; i < vs.length; i++) {
                    for (let j = i + 1; j < vs.length; j++) {
                        if (testOBBCollision(vs[i].getOBB(), vs[j].getOBB(), 0.02)) {
                            satCollisions++;
                        }
                    }
                }

                let minRedDist = 999.0;
                let crosswalkViolations = 0;
                let boxViolations = 0;
                let illegalRed = 0;
                let deadlocks = 0;

                diags.forEach(d => {
                    const sig = sigs[d.approach]?.vehicle || 'RED';
                    if (sig === 'RED' && !d.intersectionOccupancy && !d.hasEnteredOnGreen) {
                        if (d.distToStop < minRedDist) minRedDist = d.distToStop;
                        if (d.crosswalkViolation) crosswalkViolations++;
                        if (d.boxViolation) boxViolations++;
                        if (d.entryPermission === 'ILLEGAL_RED') illegalRed++;
                    }
                    if (d.intersectionOccupancy && d.speed < 0.01 && d.stoppedFrames > 40) {
                        deadlocks++;
                    }
                });

                const inBox = diags.filter(d => d.intersectionOccupancy);

                return {
                    phase: s.phase,
                    allRed,
                    vehicleCount: diags.length,
                    satCollisions,
                    minRedDist,
                    crosswalkViolations,
                    boxViolations,
                    illegalRed,
                    deadlocks,
                    inBoxCount: inBox.length,
                    inBoxDetails: inBox.map(d => ({
                        id: d.id,
                        app: d.approach,
                        rt: d.currentRoute,
                        lane: d.laneIndex,
                        spd: d.speed,
                        pos: { x: d.x, z: d.z },
                        entryPerm: d.entryPermission,
                        entryPhase: d.entrySignalPhase,
                        entryColor: d.entrySignalColor,
                        status: d.exitClearanceStatus
                    }))
                };
            }""")

            metrics["samples"] += 1
            metrics["peak_vehicles"] = max(metrics["peak_vehicles"], diag["vehicleCount"])
            metrics["sat_collision_events"] += diag["satCollisions"]
            metrics["red_crosswalk_violations"] += diag["crosswalkViolations"]
            metrics["red_box_violations"] += diag["boxViolations"]
            metrics["illegal_red_entries"] += diag["illegalRed"]
            metrics["deadlock_events"] += diag["deadlocks"]
            if diag["minRedDist"] < metrics["min_dist_to_stop_on_red"]:
                metrics["min_dist_to_stop_on_red"] = diag["minRedDist"]

            if diag["allRed"] and diag["inBoxCount"] > 0:
                metrics["all_red_box_clearance_samples"] += 1
                print(f"  [ALL-RED Clearance Sample t={step*0.5:.1f}s] Phase: {diag['phase']} | BoxVehicles: {diag['inBoxCount']}")
                for b in diag["inBoxDetails"]:
                    print(f"      V{b['id']} ({b['app']} {b['rt']}): spd={b['spd']} perm={b['entryPerm']} entryPhase={b['entryPhase']} status={b['status']}")

        print("\nHigh-Density Traffic Flow Results:")
        print(f"  - Peak Vehicle Count: {metrics['peak_vehicles']}")
        print(f"  - Min Distance to Stop Line on RED: {metrics['min_dist_to_stop_on_red']:.2f}m")
        print(f"  - Red Light Crosswalk Violations: {metrics['red_crosswalk_violations']}")
        print(f"  - Red Light Box Violations: {metrics['red_box_violations']}")
        print(f"  - Illegal RED Light Entries: {metrics['illegal_red_entries']}")
        print(f"  - Physical OBB Collisions: {metrics['sat_collision_events']}")
        print(f"  - Intersection Deadlocks: {metrics['deadlock_events']}")

        assert metrics["sat_collision_events"] == 0, f"Found {metrics['sat_collision_events']} collisions!"
        assert metrics["red_crosswalk_violations"] == 0, f"Found {metrics['red_crosswalk_violations']} crosswalk violations!"
        assert metrics["red_box_violations"] == 0, f"Found {metrics['red_box_violations']} box violations!"
        assert metrics["illegal_red_entries"] == 0, f"Found {metrics['illegal_red_entries']} illegal red entries!"
        assert metrics["deadlock_events"] == 0, f"Found {metrics['deadlock_events']} deadlocks!"
        assert metrics["min_dist_to_stop_on_red"] >= 0.95, f"Min distance to stop on red too close: {metrics['min_dist_to_stop_on_red']:.2f}m"

        screenshot_hd = os.path.join(ARTIFACT_DIR, "40_high_density_anti_gridlock_clearance.png")
        await page.screenshot(path=screenshot_hd)
        print(f"✓ Fresh High-Density Screenshot captured: {screenshot_hd}")

        # ---------------------------------------------------------------------
        # TEST 3: EMERGENCY PRIORITY DISPATCH FROM ALL FOUR APPROACHES
        # ---------------------------------------------------------------------
        print("\n--- TEST 3: Emergency Priority Dispatch from All Four Approaches ---")
        approaches = ["south", "north", "east", "west"]
        routes = ["straight", "left", "right"]

        for app_idx, app in enumerate(approaches):
            print(f"\nTesting Approach {app_idx+1}/4: {app.upper()} Approach Emergency Priority...")
            for rt in routes:
                print(f"  -> Testing {app.upper()} ambulance route: {rt.upper()}")
                # Reset and spawn traffic
                await page.evaluate(f"""async () => {{
                    clearAllVehicles3D();
                    clearAllPedestrians3D();
                    window.lastClearedAmbulance = null;
                    await apiControlSimulation('reset');
                    await apiControlTraffic('high');
                    burstSpawnVehicles('north', 2);
                    burstSpawnVehicles('south', 2);
                    burstSpawnVehicles('east', 2);
                    burstSpawnVehicles('west', 2);
                }}""")
                await page.wait_for_timeout(1000)

                # Select and dispatch
                await page.select_option("#ambulanceApproach", app)
                await page.select_option("#ambulanceRoute", rt)
                await page.wait_for_timeout(300)
                await page.click("#btnAmbulanceDispatch")

                # Monitor until ambulance clears or timeout (max 18s)
                amb_cleared = False
                amb_collisions = 0
                max_samples = 36 # 18 seconds

                for s in range(max_samples):
                    await page.wait_for_timeout(500)
                    state_res = await page.evaluate("""() => {
                        const s = window.state || {};
                        const vs = window.vehicles3D || [];
                        const amb = vs.find(v => v.isAmbulance);

                        let satHits = 0;
                        if (amb) {
                            for (let j = 0; j < vs.length; j++) {
                                if (vs[j] === amb) continue;
                                if (testOBBCollision(amb.getOBB(), vs[j].getOBB(), 0.02)) {
                                    satHits++;
                                }
                            }
                        }

                        return {
                            phase: s.phase,
                            emergencyActive: s.emergencyActive,
                            amb: amb ? {
                                spd: amb.speed,
                                pos: { x: amb.mesh.position.x, z: amb.mesh.position.z },
                                distStop: amb.getDistanceToStopLine(),
                                hasTurned: amb.hasTurned,
                                cleared: amb.hasCleared || amb.clearedIntersection || (typeof amb.hasClearedIntersection === 'function' ? amb.hasClearedIntersection() : false)
                            } : null,
                            lastCleared: window.lastClearedAmbulance,
                            satHits
                        };
                    }""")

                    amb_collisions += state_res["satHits"]
                    amb_obj = state_res["amb"]
                    if state_res["lastCleared"] or (amb_obj and amb_obj["cleared"]):
                        amb_cleared = True
                        print(f"     ✓ Ambulance cleared intersection successfully at t={s*0.5:.1f}s (collisions: {amb_collisions})")
                        break

                assert amb_cleared, f"Ambulance failed to clear intersection for {app} {rt}!"
                assert amb_collisions == 0, f"Ambulance experienced {amb_collisions} collisions for {app} {rt}!"

            # Capture a screenshot for this approach's emergency run
            shot_path = os.path.join(ARTIFACT_DIR, f"4{app_idx+1}_emergency_priority_{app}.png")
            await page.screenshot(path=shot_path)
            print(f"  ✓ Emergency Priority Screenshot captured for {app.upper()}: {shot_path}")

        print("\n=======================================================================")
        print("ALL TESTS PASSED SUCCESSFULLY! ZERO FAILURES!")
        print("=======================================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_full_verification())
