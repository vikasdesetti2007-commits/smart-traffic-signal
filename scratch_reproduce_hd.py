import asyncio
import json
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

        # Setup high density traffic matching test 2
        await page.evaluate("""async () => {
            await apiControlSimulation('reset');
            await apiControlTraffic('high', 'north');
            await apiControlTraffic('high', 'south');
            await apiControlTraffic('high', 'east');
            await apiControlTraffic('high', 'west');
            burstSpawnVehicles('north', 3);
            burstSpawnVehicles('south', 3);
            burstSpawnVehicles('east', 3);
            burstSpawnVehicles('west', 3);
        }""")
        await page.wait_for_timeout(1000)

        print("Tracking across 30 samples (approx 15s)...")
        # Sample every 500ms
        for step in range(30):
            await page.wait_for_timeout(500)
            data = await page.evaluate("""(sIdx) => {
                const s = window.state || {};
                const vs = window.vehicles3D || [];
                const sigs = s.signals || {};

                // HUD panel texts
                const hud = {
                    north: {
                        color: sigs.north ? sigs.north.vehicle : 'N/A',
                        text: document.querySelector('#hudNorth .hud-light')?.textContent?.trim(),
                        time: document.querySelector('#hudNorth .hud-time')?.textContent?.trim(),
                        sub: document.querySelector('#hudNorth .hud-sub')?.textContent?.trim()
                    },
                    south: {
                        color: sigs.south ? sigs.south.vehicle : 'N/A',
                        text: document.querySelector('#hudSouth .hud-light')?.textContent?.trim(),
                        time: document.querySelector('#hudSouth .hud-time')?.textContent?.trim(),
                        sub: document.querySelector('#hudSouth .hud-sub')?.textContent?.trim()
                    },
                    east: {
                        color: sigs.east ? sigs.east.vehicle : 'N/A',
                        text: document.querySelector('#hudEast .hud-light')?.textContent?.trim(),
                        time: document.querySelector('#hudEast .hud-time')?.textContent?.trim(),
                        sub: document.querySelector('#hudEast .hud-sub')?.textContent?.trim()
                    },
                    west: {
                        color: sigs.west ? sigs.west.vehicle : 'N/A',
                        text: document.querySelector('#hudWest .hud-light')?.textContent?.trim(),
                        time: document.querySelector('#hudWest .hud-time')?.textContent?.trim(),
                        sub: document.querySelector('#hudWest .hud-sub')?.textContent?.trim()
                    }
                };

                // Check intersection box (|x| <= 8.5 && |z| <= 8.5)
                const inBoxVehicles = vs.filter(v => Math.abs(v.mesh.position.x) <= 8.5 && Math.abs(v.mesh.position.z) <= 8.5);

                return {
                    time: (sIdx * 0.5).toFixed(1),
                    phase: s.phase,
                    phaseDisplay: s.phaseDisplay,
                    hud,
                    allRedHUD: ['north', 'south', 'east', 'west'].every(k => hud[k].color === 'RED'),
                    totalVehicles: vs.length,
                    boxCount: inBoxVehicles.length,
                    boxVehicles: inBoxVehicles.map(v => ({
                        id: v.id,
                        app: v.approach,
                        rt: v.route,
                        lane: v.laneIndex,
                        x: Number(v.mesh.position.x.toFixed(2)),
                        z: Number(v.mesh.position.z.toFixed(2)),
                        spd: Number(v.speed.toFixed(3)),
                        hasTurned: v.hasTurned,
                        inBox: v.inIntersection,
                        cleared: v.clearedIntersection,
                        distToStop: Number(v.getDistanceToStopLine().toFixed(2)),
                        signal: v.getSignalColor()
                    }))
                };
            }""", step)

            all_red = data['allRedHUD']
            sig_status = " ".join([f"{k.upper()}:{data['hud'][k]['color']}" for k in ['north', 'south', 'east', 'west']])
            all_red_tag = " >>> ALL RED! <<<" if all_red else ""
            print(f"t={data['time']}s | Phase: {data['phase']:<20} | {sig_status}{all_red_tag} | BoxVehicles: {data['boxCount']}")
            if data['boxCount'] > 0:
                for bv in data['boxVehicles']:
                    print(f"    -> V{bv['id']} ({bv['app']} {bv['rt']} lane {bv['lane']}): pos=({bv['x']},{bv['z']}) spd={bv['spd']} sig={bv['signal']} inBox={bv['inBox']} distStop={bv['distToStop']} hasTurned={bv['hasTurned']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
