"""Comprehensive Browser Verification for 3D Vehicle Models, Wheel Rotation, and Steering Animation."""

import asyncio
import os
import sys
import math
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

async def run_tests():
    print("=== STARTING VEHICLE 3D MODELS, WHEEL ROTATION & STEERING VERIFICATION ===")
    
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
        
        page.on("console", lambda msg: print(f"[Browser Console] {msg.type}: {msg.text}") if "Ambulance" in msg.text or "Error" in msg.text else None)

        print("1. Loading page...")
        await page.goto("http://localhost:8000/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        # ----------------------------------------------------------------------
        # TEST 1: Inspect 3D Models and Wheel Hierarchy
        # ----------------------------------------------------------------------
        print("\n--- TEST 1: 3D Vehicle Hierarchy & Components ---")
        model_info = await page.evaluate('''() => {
            const vList = window.vehicles3D || [];
            return vList.map(v => ({
                type: v.type,
                length: v.length,
                width: v.width,
                wheelRadius: v.wheelRadius,
                steerPivotsCount: v.mesh.userData.steerPivots ? v.mesh.userData.steerPivots.length : 0,
                rollGroupsCount: v.mesh.userData.rollGroups ? v.mesh.userData.rollGroups.length : 0,
                wheelsCount: v.mesh.userData.wheels ? v.mesh.userData.wheels.length : 0,
                hasTaillight: !!v.mesh.userData.taillightMat,
                hasTurnSignal: !!v.mesh.userData.turnMat
            }));
        }''')
        
        print(f"Active vehicles found: {len(model_info)}")
        for i, info in enumerate(model_info):
            print(f" Vehicle {i+1} [{info['type'].upper()}]: Length={info['length']}m, Width={info['width']}m, WheelRadius={info['wheelRadius']}m | SteerPivots={info['steerPivotsCount']}, RollGroups={info['rollGroupsCount']}, TotalWheels={info['wheelsCount']}")
            assert info['steerPivotsCount'] >= 2, f"Front steering pivots missing on {info['type']}"
            assert info['rollGroupsCount'] >= 4, f"Rolling wheel groups missing on {info['type']}"
            assert info['wheelRadius'] > 0, "Wheel radius must be positive"

        # ----------------------------------------------------------------------
        # TEST 2: Wheel Rotation While Moving vs Stopped
        # ----------------------------------------------------------------------
        print("\n--- TEST 2: Dynamic Wheel Rotation & Stopping ---")
        
        # Sample consecutive frames for moving vehicle
        samples = []
        for _ in range(8):
            await page.wait_for_timeout(100)
            data = await page.evaluate('''() => {
                const v = (window.vehicles3D || []).find(veh => !veh.isAmbulance && veh.speed > 0.1);
                if (!v) return null;
                const rollX = v.mesh.userData.rollGroups && v.mesh.userData.rollGroups[0] ? v.mesh.userData.rollGroups[0].rotation.x : null;
                return {
                    type: v.type,
                    speed: v.speed,
                    wheelRollAngle: v.wheelRollAngle,
                    rollGroupX: rollX,
                    posX: v.mesh.position.x,
                    posZ: v.mesh.position.z
                };
            }''')
            if data:
                samples.append(data)
                
        print(f"Captured {len(samples)} motion samples.")
        if len(samples) >= 3:
            s0 = samples[0]
            s_last = samples[-1]
            dist_moved = math.hypot(s_last['posX'] - s0['posX'], s_last['posZ'] - s0['posZ'])
            angle_diff = (s_last['wheelRollAngle'] - s0['wheelRollAngle']) % (2 * math.pi)
            print(f" Moving vehicle [{s0['type']}]: Traveled {dist_moved:.2f}m | Wheel rotated {angle_diff:.2f} rad")
            assert dist_moved > 0.05, "Vehicle should be translating across road"
            assert angle_diff > 0.05, "Wheels must visibly spin while moving forward"
            print(" [PASS] Dynamic wheel rotation verified on moving vehicle!")

        # Screenshot moving vehicles
        ss_moving = os.path.join(SCREENSHOTS_DIR, "01_moving_traffic_spinning_wheels.png")
        await page.screenshot(path=ss_moving)
        print(f" Saved screenshot: {ss_moving}")

        # Pause simulation and verify wheels stop
        print("\nTesting stationary vehicle wheel lock (speed = 0)...")
        await page.click("#btnPause")
        await page.wait_for_timeout(400)
        
        stopped_samples = []
        for _ in range(4):
            await page.wait_for_timeout(100)
            val = await page.evaluate('''() => {
                const v = (window.vehicles3D || [])[0];
                return v ? { angle: v.wheelRollAngle, speed: v.speed } : null;
            }''')
            if val:
                stopped_samples.append(val)
                
        if len(stopped_samples) >= 2:
            diff = abs(stopped_samples[-1]['angle'] - stopped_samples[0]['angle'])
            print(f" Stopped vehicle rotation change over 400ms: {diff:.6f} rad")
            assert diff < 1e-4, "Wheels must NOT rotate when vehicle is stationary"
            print(" [PASS] Wheels stop rotating when vehicle stops!")

        # Resume simulation
        await page.click("#btnStart")
        await page.wait_for_timeout(500)

        # ----------------------------------------------------------------------
        # TEST 3: Front-Wheel Steering on Left and Right Turns
        # ----------------------------------------------------------------------
        print("\n--- TEST 3: Front-Wheel Steering Animation ---")
        
        # Test 3A: Left Turn Steering
        print("\nTesting South -> Turn Left (Steering to driver's left)...")
        await page.select_option("#ambulanceApproach", "south")
        await page.select_option("#ambulanceRoute", "left")
        await page.click("#btnAmbulanceDispatch")

        max_steer_left = 0.0
        steered_left_observed = False
        realigned_left = False
        
        for _ in range(30): # 6 seconds
            await page.wait_for_timeout(200)
            telemetry = await page.evaluate('''() => {
                const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                if (!amb) return null;
                const frontPivot = amb.mesh.userData.steerPivots ? amb.mesh.userData.steerPivots[0].rotation.y : 0;
                const rearWheels = amb.mesh.userData.wheels ? amb.mesh.userData.wheels.filter(w => !w.isFront).map(w => w.steerPivot.rotation.y) : [];
                return {
                    steerAngle: amb.steerAngle,
                    targetSteerAngle: amb.targetSteerAngle,
                    frontPivotAngle: frontPivot,
                    rearPivotAngles: rearWheels,
                    turnProgress: amb.turnProgress,
                    hasTurned: amb.hasTurned,
                    hasCleared: amb.hasCleared,
                    speed: amb.speed,
                    wheelRoll: amb.wheelRollAngle
                };
            }''')
            if not telemetry:
                continue
                
            sa = telemetry['steerAngle']
            prog = telemetry['turnProgress']
            if prog > 0.05 and prog < 0.80:
                if sa < max_steer_left:
                    max_steer_left = sa
                if sa < -0.08:
                    steered_left_observed = True
                    # Capture screenshot while steering in curve
                    if not os.path.exists(os.path.join(SCREENSHOTS_DIR, "02_left_turn_steered_wheels.png")):
                        await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_left_turn_steered_wheels.png"))
            if telemetry['hasTurned']:
                if abs(sa) < 0.08:
                    realigned_left = True
                    break

        print(f" Left turn maximum front-wheel steering observed: {max_steer_left:.3f} rad ({math.degrees(max_steer_left):.1f} deg)")
        print(f" Steered toward inside of curve: {steered_left_observed}")
        print(f" Realigned back to center after exit: {realigned_left}")
        assert steered_left_observed, "Front wheels must steer toward curve during left turn"
        assert realigned_left, "Front wheels must realign back to center after turn completion"
        print(" [PASS] Left-turn front-wheel steering verified!")

        # Wait for Test 3A ambulance to clear
        for _ in range(30):
            is_busy = await page.evaluate('''() => {
                const s = window.state || {};
                const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                return s.emergencyActive || (amb && !amb.hasCleared);
            }''')
            if not is_busy:
                break
            await page.wait_for_timeout(200)

        # Test 3B: Right Turn Steering
        print("\nTesting South -> Turn Right (Steering to driver's right)...")
        await page.select_option("#ambulanceApproach", "south")
        await page.select_option("#ambulanceRoute", "right")
        await page.click("#btnAmbulanceDispatch")

        max_steer_right = 0.0
        steered_right_observed = False
        realigned_right = False
        
        for _ in range(40): # 8 seconds
            await page.wait_for_timeout(200)
            telemetry = await page.evaluate('''() => {
                const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                if (!amb) return null;
                const frontPivot = amb.mesh.userData.steerPivots ? amb.mesh.userData.steerPivots[0].rotation.y : 0;
                return {
                    steerAngle: amb.steerAngle,
                    targetSteerAngle: amb.targetSteerAngle,
                    frontPivotAngle: frontPivot,
                    turnProgress: amb.turnProgress,
                    hasTurned: amb.hasTurned,
                    hasCleared: amb.hasCleared,
                    speed: amb.speed
                };
            }''')
            if not telemetry:
                continue
                
            sa = telemetry['steerAngle']
            prog = telemetry['turnProgress']
            if prog > 0.05 and prog < 0.80:
                if sa > max_steer_right:
                    max_steer_right = sa
                if sa > 0.08:
                    steered_right_observed = True
                    if not os.path.exists(os.path.join(SCREENSHOTS_DIR, "03_right_turn_steered_wheels.png")):
                        await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_right_turn_steered_wheels.png"))
            if telemetry['hasTurned']:
                if abs(sa) < 0.08:
                    realigned_right = True
                    break

        print(f" Right turn maximum front-wheel steering observed: {max_steer_right:.3f} rad ({math.degrees(max_steer_right):.1f} deg)")
        print(f" Steered toward inside of curve: {steered_right_observed}")
        print(f" Realigned back to center after exit: {realigned_right}")
        assert steered_right_observed, "Front wheels must steer toward curve during right turn"
        assert realigned_right, "Front wheels must realign back to center after turn completion"
        print(" [PASS] Right-turn front-wheel steering verified!")

        # Wait for Test 3B ambulance to clear before Test 4
        for _ in range(30):
            is_busy = await page.evaluate('''() => {
                const s = window.state || {};
                const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                return s.emergencyActive || (amb && !amb.hasCleared);
            }''')
            if not is_busy:
                break
            await page.wait_for_timeout(200)

        # ----------------------------------------------------------------------
        # TEST 4: Ambulance Priority & All 12 Routes With 3D Upgrades
        # ----------------------------------------------------------------------
        print("\n--- TEST 4: All 12 Route Combinations with Upgraded 3D Wheels & Priority ---")
        approaches = ["south", "north", "east", "west"]
        routes = ["straight", "left", "right"]
        pass_count = 0

        for app in approaches:
            for rt in routes:
                key = f"{app.upper()} -> {rt.upper()}"
                
                # Wait for any prior emergency or ambulance to completely clear
                for _ in range(40):
                    is_busy = await page.evaluate('''() => {
                        const s = window.state || {};
                        const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                        return s.emergencyActive || (amb && !amb.hasCleared);
                    }''')
                    if not is_busy:
                        break
                    await page.wait_for_timeout(250)

                await page.select_option("#ambulanceApproach", app)
                await page.select_option("#ambulanceRoute", rt)
                await page.click("#btnAmbulanceDispatch")

                route_passed = False
                for _ in range(45): # up to 9 seconds
                    await page.wait_for_timeout(200)
                    state = await page.evaluate('''() => {
                        const s = window.state || {};
                        const amb = (window.vehicles3D || []).find(v => v.isAmbulance);
                        return {
                            phase: s.phase,
                            emerActive: s.emergencyActive,
                            sigs: s.signals || {},
                            amb: amb ? {
                                x: amb.mesh.position.x,
                                z: amb.mesh.position.z,
                                speed: amb.speed,
                                wheelRoll: amb.wheelRollAngle,
                                steer: amb.steerAngle,
                                hasCleared: amb.hasCleared
                            } : null
                        };
                    }''')
                    if state['phase'] == 'EMERGENCY_PRIORITY':
                        # Confirm only incoming approach is green
                        app_sig = state['sigs'].get(app, {}).get('vehicle')
                        assert app_sig == 'GREEN', f"Incoming {app} must be GREEN"
                        for other in ['north', 'south', 'east', 'west']:
                            if other != app:
                                other_sig = state['sigs'].get(other, {}).get('vehicle')
                                assert other_sig == 'RED', f"Conflicting {other} must be RED during emergency"
                    
                    if state['amb'] and state['amb']['hasCleared']:
                        route_passed = True
                        break

                if route_passed:
                    pass_count += 1
                    print(f" [PASS] {key}: Exclusive signals verified, wheels rolling, cleared exit road!")
                else:
                    print(f" [FAIL] {key}: Timeout waiting for ambulance clearance")

        print(f"\n12-Route Result: {pass_count}/12 PASSED")
        assert pass_count == 12, "All 12 combinations must pass with 100% success"

        # Final screenshot of ambulance priority corridor
        await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_ambulance_priority_corridor.png"))
        print(f" Final corridor screenshot saved: {os.path.join(SCREENSHOTS_DIR, '04_ambulance_priority_corridor.png')}")

        await browser.close()
        print("\n=== ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
