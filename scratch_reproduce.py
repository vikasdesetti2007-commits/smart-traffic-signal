import asyncio
import os
import sys
import math
from playwright.async_api import async_playwright

async def trace_ambulance(approach, route):
    print(f"\n=======================================================")
    print(f"REPRODUCING: approach={approach}, route={route}")
    print(f"=======================================================")
    
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
        
        # Capture console messages from browser
        page.on("console", lambda msg: print(f"[Browser Console] {msg.type}: {msg.text}"))

        await page.goto("http://localhost:8000/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        # Select approach and route
        await page.select_option("#ambulanceApproach", approach)
        await page.select_option("#ambulanceRoute", route)
        await page.wait_for_timeout(300)

        # Dispatch
        print(f">>> Clicking #btnAmbulanceDispatch for {approach} [{route}]")
        await page.click("#btnAmbulanceDispatch")

        # Record every 500ms for 20 seconds (40 samples)
        for i in range(40):
            await page.wait_for_timeout(500)
            telemetry = await page.evaluate("""() => {
                const s = window.state || {};
                const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                const sigs = s.signals || {};
                const allVehiclesCount = (window.vehicles3D || []).length;
                return {
                    sample: Date.now(),
                    phase: s.phase,
                    phaseDisplay: s.phaseDisplay,
                    timeInPhase: s.timeInPhase,
                    phaseDuration: s.phaseDuration,
                    emergencyActive: s.emergencyActive,
                    emergencyApproach: s.emergencyApproach,
                    emergencyRoute: s.emergencyRoute,
                    signals: {
                        north: sigs.north ? sigs.north.vehicle : 'N/A',
                        south: sigs.south ? sigs.south.vehicle : 'N/A',
                        east: sigs.east ? sigs.east.vehicle : 'N/A',
                        west: sigs.west ? sigs.west.vehicle : 'N/A',
                    },
                    vehicleCount: allVehiclesCount,
                    ambulance: amb ? {
                        exists: true,
                        x: amb.mesh ? Number(amb.mesh.position.x.toFixed(2)) : null,
                        z: amb.mesh ? Number(amb.mesh.position.z.toFixed(2)) : null,
                        heading: amb.mesh ? Number(amb.mesh.rotation.y.toFixed(2)) : null,
                        speed: Number(amb.speed.toFixed(3)),
                        baseSpeed: Number(amb.baseSpeed.toFixed(3)),
                        approach: amb.approach,
                        route: amb.route,
                        exitRoad: amb.exitRoad,
                        hasTurned: amb.hasTurned,
                        hasCleared: amb.hasCleared,
                        distToStop: Number(amb.getDistanceToStopLine().toFixed(2)),
                        signalColor: amb.getSignalColor()
                    } : null
                };
            }""")

            amb = telemetry["ambulance"]
            sigs = telemetry["signals"]
            sig_str = f"N:{sigs['north']} S:{sigs['south']} E:{sigs['east']} W:{sigs['west']}"
            if amb:
                print(f"t={i*0.5:4.1f}s | phase={telemetry['phase']:<18} | {sig_str} | emerActive={telemetry['emergencyActive']} | pos=({amb['x']:5.1f}, {amb['z']:5.1f}) | spd={amb['speed']:.3f} | distStop={amb['distToStop']:5.1f} | exit={amb['exitRoad']} | cleared={amb['hasCleared']}")
            else:
                print(f"t={i*0.5:4.1f}s | phase={telemetry['phase']:<18} | {sig_str} | emerActive={telemetry['emergencyActive']} | AMBULANCE: NOT FOUND | totalVehicles={telemetry['vehicleCount']}")

        await browser.close()

async def main():
    await trace_ambulance("south", "straight")
    await trace_ambulance("south", "left")
    await trace_ambulance("south", "right")

if __name__ == "__main__":
    asyncio.run(main())
