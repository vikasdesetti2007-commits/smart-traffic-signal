# Smart Traffic Signal Controller & 3D WebGL Intersection Simulation

A full-stack, responsive smart traffic signal simulation and deterministic safety controller built with **Python FastAPI**, **Three.js (WebGL)**, **CSS3 Glassmorphism**, and **Vanilla JavaScript**.

> **DISCLAIMER:**  
> This software is an educational demonstration and simulation of traffic control logic, formal propositional reasoning, and multi-phase preemption. It is **NOT** certified for direct physical municipal or highway traffic-control infrastructure.

---

## 3D WebGL Features & Improvements

1. **Genuine 3D Intersection (Three.js & WebGL)**:
   - Built on a real 3D coordinate system ($X, Y, Z$) with WebGL rendering and PCF Soft Shadows.
   - Asphalt roadways with two-way dual-lane traffic, yellow double centerlines, dashed white lane dividers, white stop lines, and 3D zebra crosswalks.
   - Raised sidewalks ($Y = 0.25$) with concrete curbs, low-poly city buildings with lit window arrays, surrounding sidewalk trees, and realistic streetlights.
   - Cantilever steel traffic signal poles with 3-aspect lanterns (Red, Yellow, Green) and eye-level pedestrian signal boxes whose emissive glow dynamically synchronizes in real time with the backend state.

2. **Interactive 3D Camera Controls**:
   - **Orbit, Zoom & Pan:** Full mouse and touch controls via `THREE.OrbitControls` (Left Drag to orbit, Right Drag to pan, Scroll wheel to zoom).
   - **Camera Preset Quick-Views:**
     - 📐 **3D Perspective** (Elevated angled isometric view).
     - 🛰️ **Top-Down** (Overhead traffic management view).
     - 🚗 **Street Level** (Driver / street-level perspective).
     - ↺ **Reset View**.

3. **3D Vehicle Models & Realistic Kinematics**:
   - Built with detailed multi-part 3D composite meshes:
     - **Sedans & Coupes:** Chassis, tinted cabin glass, rotating wheels on alloy rims, headlights, taillights, amber turn indicators.
     - **SUVs & Trucks:** Raised chassis, larger wheels, boxier profile.
     - **Transit Bus:** 8.5m extended body, large panoramic windows, destination board, 6 wheels.
     - **Emergency Ambulance:** High-visibility livery, red cross emblems, dual-color roof lightbar, and dynamic emergency strobe light casting real-time pulses across the scene.
   - **Kinematics & Collision Avoidance:**
     - Vehicles accelerate and decelerate realistically.
     - Stop line compliance on Red and Yellow.
     - Intelligent Driver Model (car-following headway buffer) prevents rear-end collisions and forms realistic vehicle queues.
     - 90° circular turning trajectories (right turns into outer lane, left turns across intersection into inner lane) with vehicle heading smoothly aligned along velocity tangent.
     - Blinking amber turn indicators while approaching and navigating turns.

4. **Emergency Vehicle (Ambulance) Preemption**:
   - Select approach (North, South, East, West) and click **Dispatch Ambulance**.
   - Initiates safe clearance intervals (Yellow & All-Red) on conflicting lanes before granting priority Green.
   - The ambulance maintains high speed and passes smoothly through the intersection without stopping at Red.
   - Alternating red/blue strobe beacons illuminate road surfaces and nearby buildings.
   - Automatically releases preemption back to normal cyclic scheduling once the ambulance clears the intersection.

5. **Adjustable Vehicle Speed Meter & Fleet Telemetry**:
   - Dynamic 0–100 km/h speed slider with live speed readout badge.
   - One-click presets: **Slow (25 km/h)**, **Normal (50 km/h)**, **Fast (80 km/h)**, and **Hold (0 km/h)**.
   - Smooth acceleration and deceleration physics scaling with vehicle type; vehicles never snap instantly between speeds.
   - Real-time fleet average telemetry and target speed display.
   - Setting speed to 0 km/h safely holds all vehicles in place without pausing signal timers, pedestrian crossing countdowns, or camera orbit.

6. **3D Animated Pedestrians & Setback Crosswalks**:
   - 3D humanoid figures with animated leg/arm walking motion crossing zebra crosswalks during the permitted **WALK** phase.
   - High-contrast white zebra crosswalk markings on asphalt with 12.0m stop line setbacks, preventing stopped vehicles from ever overhanging the pedestrian crossing.
   - Safely held on sidewalk curbs during **DONT_WALK**.
   - Strict vehicle-pedestrian conflict elimination (all vehicles held in All-Red during walk phase).

7. **Formal Propositional Logic Demonstration ($G = (P \lor Q) \land \neg R$)**:
   - $P$: High Traffic Density ($\ge 75\%$).
   - $Q$: Emergency Vehicle Detected.
   - $R$: Pedestrian Crossing Active.
   - Formula: $G = (P \lor Q) \land \neg R$.
   - Live interactive 8-row truth table dynamically highlights the active state row in real time.

---

## Tech Stack

- **Backend:** Python 3.14+, FastAPI 0.161.1, Pydantic v2
- **Server:** Uvicorn with standard C-extensions (`uvloop`, `httptools`, `watchfiles`, `websockets`)
- **Testing:** Pytest 9.1.1, Starlette TestClient (HTTPX)
- **Frontend:** Three.js r128 (WebGL), OrbitControls, HTML5, CSS3 Glassmorphism, Vanilla JavaScript

---

## Directory Structure

```text
smart-traffic-signal/
├── app/
│   ├── __init__.py           # Package initialization & version
│   ├── schemas.py            # Pydantic data models & request/response schemas
│   ├── logic_engine.py       # Formal propositional logic & truth table evaluator
│   ├── controller.py         # Deterministic safety state machine & preemption engine
│   └── main.py               # FastAPI application, REST endpoints & static server
├── static/
│   ├── index.html            # Responsive 3D operator dashboard & camera toolbar
│   ├── style.css             # Glassmorphic dark-mode styling with 3D WebGL container
│   ├── app.js                # 60 FPS Three.js engine, 3D kinematics & API sync
│   └── vendor/
│       ├── three.min.js      # Three.js 3D WebGL library (offline bundled)
│       └── OrbitControls.js  # Camera orbit/pan/zoom controls
├── tests/
│   ├── __init__.py
│   ├── test_logic_engine.py  # Tests for all 8 truth table rows & logic formula
│   ├── test_controller.py    # Tests for safety invariants, preemption & clearance
│   └── test_api.py           # Integration tests for FastAPI endpoints & validation
├── requirements.txt          # Python dependency specifications
└── README.md                 # Complete system documentation and API reference
```

---

## Launch Instructions

### 1. Run Automated Tests

Execute the 29 automated unit and integration tests:

```bash
/home/vikas/smart-traffic-signal/.venv/bin/pytest -v
```

Expected result:
```text
======================== 29 passed in 0.49s =========================
```

### 2. Launch the Web Application

Start the FastAPI application with Uvicorn:

```bash
/home/vikas/smart-traffic-signal/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
```
http://localhost:8000/
```

---

## How to Test Features in the Browser

### Testing Ambulance Priority Mode
1. In the **Emergency Vehicle Preemption** card, choose an approach (e.g., **South Approach**).
2. Click **🚨 Dispatch Ambulance**.
3. **Observe:**
   - The backend controller immediately initiates safe clearance: conflicting East-West green transitions to Yellow (2.5s) and then All-Red (1.5s).
   - Once cleared, a continuous protected Green corridor is granted to the ambulance's corridor.
   - The ambulance appears with rapid alternating red & blue roof lightbar strobes and a dynamic emergency point light illuminating the pavement.
   - The ambulance accelerates through the intersection without stopping at Red.
   - The Truth Table dynamically highlights **Row 3** ($P=0, Q=1, R=0 \implies G=1$) or **Row 7** ($P=1, Q=1, R=0 \implies G=1$).
   - As soon as the ambulance exits the intersection, the system smoothly transitions back to normal cyclic scheduling via an All-Red interlock.

### Testing Pedestrian Crossing Mode
1. Click **🚶 Request Pedestrian Walk Phase**.
2. **Observe:**
   - Conflicting vehicular green transitions safely through Yellow and All-Red.
   - All vehicle signals turn RED.
   - Pedestrian signal boxes illuminate green WALK with a 7-second countdown badge.
   - 3D pedestrians walk across all 4 zebra crosswalks with animated leg/arm motion.
   - Vehicles remain stopped safely behind their stop lines until the pedestrian clearance flashing interval finishes.
   - The Truth Table highlights **Row 2** ($P=0, Q=0, R=1 \implies G=0$) or **Row 6** ($P=1, Q=0, R=1 \implies G=0$).
   - After clearance, vehicle signals safely return to the cyclic green schedule.

### Testing Simultaneous Conflict Arbitration
1. Click **🚶 Request Pedestrian Walk Phase**, then immediately click **🚨 Dispatch Ambulance**.
2. **Observe:**
   - The backend safety controller safely arbitrates the conflict: emergency life-safety takes precedence, but if pedestrians are already in the street, an expedited clearance interval is executed before opening the vehicle corridor.
   - The Truth Table highlights **Row 4** or **Row 8** ($R=1 \implies G=0$ holding general traffic).

---

## API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Health check and simulation status |
| `GET` | `/api/state` | Full telemetry snapshot (signals, phase, truth table, logic, events) |
| `POST` | `/api/control/simulation` | `{"action": "start" \| "pause" \| "reset" \| "step"}` |
| `POST` | `/api/control/traffic` | `{"density": "low" \| "medium" \| "high"}` |
| `POST` | `/api/control/ambulance` | `{"approach": "north" \| "south" \| "east" \| "west", "active": true}` |
| `POST` | `/api/control/pedestrian` | `{"active": true, "crosswalk": "all"}` |
