import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000")
        await page.wait_for_timeout(2000)

        # Inspect current state
        state = await page.evaluate("""() => {
            const s = window.state || {};
            const vs = window.vehicles3D || [];
            return {
                phase: s.phase,
                phaseDisplay: s.phaseDisplay,
                signals: s.signals,
                vehicleCount: vs.length,
                vehicles: vs.map(v => ({
                    id: v.id,
                    approach: v.approach,
                    route: v.route,
                    laneIndex: v.laneIndex,
                    speed: Number(v.speed.toFixed(3)),
                    pos: { x: Number(v.mesh.position.x.toFixed(2)), z: Number(v.mesh.position.z.toFixed(2)) },
                    inIntersection: v.inIntersection,
                    clearedIntersection: v.clearedIntersection,
                    hasTurned: v.hasTurned,
                    distToStop: Number(v.getDistanceToStopLine().toFixed(2)),
                    signalColor: v.getSignalColor()
                }))
            };
        }""")
        print("Initial state:", state["phase"], state["signals"])
        print(f"Vehicle count: {state['vehicleCount']}")
        for v in state['vehicles'][:10]:
            print(f"  V{v['id']}: app={v['approach']} rt={v['route']} lane={v['laneIndex']} pos=({v['pos']['x']},{v['pos']['z']}) spd={v['speed']} inBox={v['inIntersection']} distStop={v['distToStop']} sig={v['signalColor']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
