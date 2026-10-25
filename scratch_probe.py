import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000")
        await page.wait_for_timeout(1500)

        # Set HIGH traffic density on all approaches and burst spawn
        await page.evaluate("""async () => {
            await apiControlSimulation('reset');
            await apiControlTraffic('high');
            burstSpawnVehicles('north', 3);
            burstSpawnVehicles('south', 3);
            burstSpawnVehicles('east', 3);
            burstSpawnVehicles('west', 3);
        }""")
        await page.wait_for_timeout(1000)

        # Let simulation run and log anomalies across 100 iterations (approx 30s)
        print("Monitoring for 30s (60 samples)...")
        all_red_samples = []
        violations = []

        for step in range(60):
            await page.wait_for_timeout(500)
            status = await page.evaluate("""(sIdx) => {
                const s = window.state || {};
                const vs = window.vehicles3D || [];
                const sigs = s.signals || {};

                const allRed = ['north', 'south', 'east', 'west'].every(k => sigs[k] && sigs[k].vehicle === 'RED');

                const vehicleData = vs.map(v => {
                    const p = v.mesh.position;
                    const halfL = (v.length || 4.5) * 0.5;
                    let distFromCenter = 999;
                    if (v.approach === 'north') distFromCenter = -p.z;
                    else if (v.approach === 'south') distFromCenter = p.z;
                    else if (v.approach === 'east') distFromCenter = p.x;
                    else if (v.approach === 'west') distFromCenter = -p.x;
                    const frontFromCenter = distFromCenter - halfL;

                    const sig = sigs[v.approach] ? sigs[v.approach].vehicle : 'RED';
                    const inBox = Math.abs(p.x) <= 8.5 && Math.abs(p.z) <= 8.5;
                    const distToStop = v.getDistanceToStopLine();

                    // Crosswalk is 8.2 to 10.6 from center
                    const onCrosswalk = (frontFromCenter <= 10.6 && distFromCenter >= 8.2);

                    return {
                        id: v.id,
                        approach: v.approach,
                        route: v.route,
                        lane: v.laneIndex,
                        speed: Number(v.speed.toFixed(3)),
                        x: Number(p.x.toFixed(2)),
                        z: Number(p.z.toFixed(2)),
                        distToStop: Number(distToStop.toFixed(2)),
                        frontFromCenter: Number(frontFromCenter.toFixed(2)),
                        inBox,
                        onCrosswalk,
                        sig,
                        inIntersection: v.inIntersection,
                        clearedIntersection: v.clearedIntersection,
                        hasTurned: v.hasTurned
                    };
                });

                return {
                    step: sIdx,
                    phase: s.phase,
                    allRed,
                    signals: {
                        north: sigs.north?.vehicle,
                        south: sigs.south?.vehicle,
                        east: sigs.east?.vehicle,
                        west: sigs.west?.vehicle,
                    },
                    vehicles: vehicleData
                };
            }""", step)

            if status['allRed']:
                in_box = [v for v in status['vehicles'] if v['inBox']]
                on_ped = [v for v in status['vehicles'] if v['onCrosswalk'] and not v['clearedIntersection']]
                all_red_samples.append({
                    "step": step,
                    "phase": status['phase'],
                    "in_box": in_box,
                    "on_ped": on_ped
                })
                print(f"[{step*0.5:4.1f}s] ALL-RED Phase: {status['phase']} | VehiclesInBox: {len(in_box)} | OnCrosswalk: {len(on_ped)}")
                for v in in_box:
                    print(f"   -> IN BOX: V{v['id']} ({v['approach']} {v['route']}) pos=({v['x']},{v['z']}) spd={v['speed']} inInt={v['inIntersection']}")
                for v in on_ped:
                    print(f"   -> ON CROSSWALK: V{v['id']} ({v['approach']} {v['route']}) spd={v['speed']} front={v['frontFromCenter']} distStop={v['distToStop']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
