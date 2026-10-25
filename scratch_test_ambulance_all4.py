import asyncio
from playwright.async_api import async_playwright

async def test_approach(page, approach):
    print(f"\n=======================================================")
    print(f"TESTING AMBULANCE PRIORITY: {approach.upper()}")
    print(f"=======================================================")

    await page.evaluate(f"""async () => {{
        await apiControlSimulation('reset');
        await apiControlTraffic('high');
        burstSpawnVehicles('north', 2);
        burstSpawnVehicles('south', 2);
        burstSpawnVehicles('east', 2);
        burstSpawnVehicles('west', 2);
    }}""")
    await page.wait_for_timeout(1000)

    # Select approach and route
    await page.select_option("#ambulanceApproach", approach)
    await page.select_option("#ambulanceRoute", "straight")
    await page.wait_for_timeout(300)

    # Click dispatch
    await page.click("#btnAmbulanceDispatch")

    # Monitor for 20 samples (10 seconds)
    ambulance_cleared = False
    all_red_observed = False
    vehicles_in_box_during_all_red = []

    for i in range(20):
        await page.wait_for_timeout(500)
        data = await page.evaluate(f"""() => {{
            const s = window.state || {{}};
            const vs = window.vehicles3D || [];
            const sigs = s.signals || {{}};
            const amb = vs.find(v => v.isAmbulance);

            const allRed = ['north', 'south', 'east', 'west'].every(k => sigs[k] && sigs[k].vehicle === 'RED');
            const inBoxVehicles = vs.filter(v => Math.abs(v.mesh.position.x) <= 8.5 && Math.abs(v.mesh.position.z) <= 8.5);

            return {{
                phase: s.phase,
                phaseDisplay: s.phaseDisplay,
                emergencyActive: s.emergencyActive,
                allRed,
                signals: {{
                    north: sigs.north ? sigs.north.vehicle : 'N/A',
                    south: sigs.south ? sigs.south.vehicle : 'N/A',
                    east: sigs.east ? sigs.east.vehicle : 'N/A',
                    west: sigs.west ? sigs.west.vehicle : 'N/A',
                }},
                boxCount: inBoxVehicles.length,
                boxVehicles: inBoxVehicles.map(v => ({{
                    id: v.id,
                    isAmb: v.isAmbulance,
                    app: v.approach,
                    rt: v.route,
                    lane: v.laneIndex,
                    spd: Number(v.speed.toFixed(3)),
                    pos: {{ x: Number(v.mesh.position.x.toFixed(2)), z: Number(v.mesh.position.z.toFixed(2)) }},
                    distToStop: Number(v.getDistanceToStopLine().toFixed(2)),
                    hasTurned: v.hasTurned,
                    inBox: v.inIntersection,
                    cleared: v.clearedIntersection
                }})),
                ambulance: amb ? {{
                    spd: Number(amb.speed.toFixed(3)),
                    pos: {{ x: Number(amb.mesh.position.x.toFixed(2)), z: Number(amb.mesh.position.z.toFixed(2)) }},
                    distToStop: Number(amb.getDistanceToStopLine().toFixed(2)),
                    cleared: amb.hasCleared || amb.clearedIntersection || (typeof amb.hasClearedIntersection === 'function' ? amb.hasClearedIntersection() : false)
                }} : null
            }};
        }}""")

        if data['allRed']:
            all_red_observed = True
            if data['boxCount'] > 0:
                vehicles_in_box_during_all_red.append({
                    "time": i * 0.5,
                    "phase": data['phase'],
                    "vehicles": data['boxVehicles']
                })

        amb_info = f"Amb: pos=({data['ambulance']['pos']['x']},{data['ambulance']['pos']['z']}) spd={data['ambulance']['spd']} dist={data['ambulance']['distToStop']}" if data['ambulance'] else "Amb: None"
        sig_str = f"N:{data['signals']['north']} S:{data['signals']['south']} E:{data['signals']['east']} W:{data['signals']['west']}"
        all_red_tag = " [ALL RED]" if data['allRed'] else ""
        print(f"t={i*0.5:4.1f}s | {data['phase']:<22} | {sig_str}{all_red_tag} | BoxVeh: {data['boxCount']} | {amb_info}")

        if data['ambulance'] and data['ambulance']['cleared']:
            ambulance_cleared = True
            print(f">>> Ambulance CLEARED intersection at t={i*0.5:.1f}s!")
            break

    print(f"Result for {approach}: Cleared={ambulance_cleared}, AllRedObserved={all_red_observed}")
    if vehicles_in_box_during_all_red:
        print(f"Vehicles in box during ALL-RED ({len(vehicles_in_box_during_all_red)} samples):")
        for sample in vehicles_in_box_during_all_red[:3]:
            print(f"  t={sample['time']}s phase={sample['phase']}: {sample['vehicles']}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000")
        await page.wait_for_timeout(2000)

        for app in ["south", "north", "east", "west"]:
            await test_approach(page, app)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
