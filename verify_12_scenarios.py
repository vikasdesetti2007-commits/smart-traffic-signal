import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        approaches = ["south", "north", "east", "west"]
        routes = ["straight", "left", "right"]

        results = {}

        for app in approaches:
            print(f"\n==========================================")
            print(f"TESTING APPROACH: {app.upper()}")
            print(f"==========================================")
            for rt in routes:
                # 1. Cleanly clear any active emergency and reset simulation
                await page.evaluate("""async () => {
                    await fetch('/api/control/ambulance', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ approach: 'south', route: 'straight', active: false })
                    });
                    await fetch('/api/control/simulation', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ action: 'reset' })
                    });
                    await fetch('/api/control/simulation', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ action: 'start' })
                    });
                    clearAllVehicles3D();
                    clearAllPedestrians3D();
                    window.lastClearedAmbulance = null;
                    await fetchState();
                }""")
                await page.wait_for_timeout(600)

                # 2. Burst spawn vehicles to create dense queues
                await page.evaluate(f"""() => {{
                    burstSpawnVehicles('north', 2);
                    burstSpawnVehicles('south', 2);
                    burstSpawnVehicles('east', 2);
                    burstSpawnVehicles('west', 2);
                }}""")
                await page.wait_for_timeout(500)

                # 3. Select approach & route
                await page.select_option("#ambulanceApproach", app)
                await page.select_option("#ambulanceRoute", rt)
                await page.wait_for_timeout(300)

                # 4. Dispatch
                print(f"Dispatching {app.upper()} [{rt.upper()}] ...")
                await page.click("#btnAmbulanceDispatch")
                await page.wait_for_timeout(500)

                # 5. Monitor until clearance
                cleared = False
                clear_time = 0
                collisions = 0

                for s in range(46): # 23 seconds max
                    await page.wait_for_timeout(500)
                    state_info = await page.evaluate("""() => {
                        const vs = window.vehicles3D || [];
                        const amb = vs.find(v => v.isAmbulance);
                        let hits = 0;
                        if (amb) {
                            for (let j = 0; j < vs.length; j++) {
                                if (vs[j] === amb) continue;
                                if (testOBBCollision(amb.getOBB(), vs[j].getOBB(), 0.02)) {
                                    hits++;
                                }
                            }
                        }
                        return {
                            amb: amb ? {
                                spd: Number(amb.speed.toFixed(3)),
                                pos: { x: Number(amb.mesh.position.x.toFixed(2)), z: Number(amb.mesh.position.z.toFixed(2)) },
                                distStop: Number(amb.getDistanceToStopLine().toFixed(2)),
                                turnProg: Number(amb.turnProgress.toFixed(2)),
                                hasTurned: amb.hasTurned,
                                hasCleared: amb.hasCleared,
                                cleared: amb.hasCleared || amb.clearedIntersection
                            } : null,
                            lastCleared: window.lastClearedAmbulance,
                            hits
                        };
                    }""")
                    collisions += state_info["hits"]
                    amb = state_info["amb"]
                    if state_info["lastCleared"] or (amb and amb["cleared"]):
                        cleared = True
                        clear_time = (s + 1) * 0.5
                        print(f"  ✓ {app.upper()} [{rt.upper()}] CLEARED in {clear_time:.1f}s (collisions: {collisions})")
                        break

                if not cleared:
                    print(f"  ✗ {app.upper()} [{rt.upper()}] FAILED to clear! Last amb state: {state_info['amb']}")
                results[(app, rt)] = {"cleared": cleared, "time": clear_time, "collisions": collisions}

        print("\n==========================================")
        print("SUMMARY OF ALL 12 EMERGENCY COMBINATIONS:")
        print("==========================================")
        all_passed = True
        for (app, rt), res in results.items():
            status = "PASS" if res["cleared"] and res["collisions"] == 0 else "FAIL"
            if status == "FAIL": all_passed = False
            print(f"  {app.upper():<6} {rt.upper():<9}: {status} (time={res['time']:.1f}s, collisions={res['collisions']})")

        print(f"\nFinal Result: {'ALL 12 SCENARIOS PASSED' if all_passed else 'SOME SCENARIOS FAILED'}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
