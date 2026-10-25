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

        all_passed = True
        for app in approaches:
            print(f"\n==========================================")
            print(f"TESTING APPROACH: {app.upper()}")
            print(f"==========================================")
            for rt in routes:
                print(f"Dispatching {app.upper()} [{rt.upper()}] ...")
                # Wait for any prior emergency to deactivate
                for _ in range(40):
                    is_active = await page.evaluate("() => window.state && window.state.emergencyActive")
                    if not is_active:
                        break
                    await page.wait_for_timeout(200)

                await page.evaluate("""async () => {
                    clearAllVehicles3D();
                    clearAllPedestrians3D();
                    window.lastClearedAmbulance = null;
                    await apiControlSimulation('reset');
                    await apiControlTraffic('high');
                    burstSpawnVehicles('north', 2);
                    burstSpawnVehicles('south', 2);
                    burstSpawnVehicles('east', 2);
                    burstSpawnVehicles('west', 2);
                }""")
                await page.wait_for_timeout(1000)

                await page.select_option("#ambulanceApproach", app)
                await page.select_option("#ambulanceRoute", rt)
                await page.wait_for_timeout(300)
                await page.click("#btnAmbulanceDispatch")

                cleared = False
                collisions = 0
                for s in range(40):
                    await page.wait_for_timeout(500)
                    data = await page.evaluate("""() => {
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
                                cleared: amb.hasCleared || amb.clearedIntersection
                            } : null,
                            lastCleared: window.lastClearedAmbulance,
                            hits
                        };
                    }""")
                    collisions += data["hits"]
                    if data["lastCleared"] or (data["amb"] and data["amb"]["cleared"]):
                        cleared = True
                        print(f"  ✓ Cleared in {s*0.5:.1f}s (collisions: {collisions})")
                        break

                if not cleared:
                    print(f"  ✗ FAILED to clear within 20s for {app} {rt}")
                    all_passed = False
                if collisions > 0:
                    print(f"  ✗ Collisions detected: {collisions}")
                    all_passed = False

        print(f"\nOVERALL RESULT: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
