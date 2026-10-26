/**
 * Smart Traffic Signal Autonomous Intersection Simulation & Dashboard
 * High-Quality 3D Three.js / WebGL Implementation
 * - Correct Traffic Signal World Orientations (Facing Oncoming Traffic)
 * - Reliable Backend Emergency Ambulance Preemption (All 4 Approaches)
 * - Vehicle Speed Meter (0-100 km/h) with Smooth Acceleration & Braking
 * - High-Contrast Visible Zebra Crosswalks & 3D Pedestrian Synchronization
 * - Zero Building Obstruction with Cinematic Elevated Isometric Camera
 */

// ============================================================================
// 1. Global State & Telemetry
// ============================================================================
const state = {
  backendConnected: false,
  simulationRunning: true,
  trafficDensity: 'medium',
  phase: 'NORTH_GREEN',
  phaseDisplay: 'North Green Phase',
  timeInPhase: 0,
  phaseDuration: 8.0,
  signals: {
    north: { vehicle: 'GREEN', pedestrian: 'DONT_WALK' },
    south: { vehicle: 'RED', pedestrian: 'DONT_WALK' },
    east: { vehicle: 'RED', pedestrian: 'DONT_WALK' },
    west: { vehicle: 'RED', pedestrian: 'DONT_WALK' },
  },
  emergencyActive: false,
  emergencyApproach: 'south',
  pedestrianActive: false,
  pedestrianRemaining: 0,
  logic: {
    p: false,
    q: false,
    r: false,
    g: false,
    active_row: 1,
    description: '',
    safety_note: ''
  },
  truthTable: [],
  recentEvents: [],
  activeApproach: 'north',
  greenExtended: false,
  currentHighDemandApproach: 'south',
  approachMetrics: {},
  countdowns: { north: 8.0, south: 12.0, east: 24.0, west: 36.0 },
  minGreenDuration: 8.0,
  normalGreenDuration: 12.0,
  maxGreenDuration: 22.0,
};
window.state = state;

// Vehicle speed meter state (0 to 100 km/h, default 50 km/h)
let selectedSpeedKmh = 50;

// ============================================================================
// 2. Backend API Polling & Syncing
// ============================================================================
function showApiError(msg) {
  let errEl = document.getElementById('apiErrorBanner');
  if (!errEl) {
    errEl = document.createElement('div');
    errEl.id = 'apiErrorBanner';
    errEl.className = 'api-error-banner';
    const wrapper = document.getElementById('canvasWrapper');
    if (wrapper) wrapper.prepend(errEl);
    else document.body.prepend(errEl);
  }
  errEl.textContent = `API Error: ${msg}`;
  errEl.style.display = 'block';
  setTimeout(() => {
    if (errEl) errEl.style.display = 'none';
  }, 6000);
}

async function fetchState() {
  try {
    const res = await fetch(`/api/state?_t=${Date.now()}`, {
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache'
      }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    applyState(data);
    const errEl = document.getElementById('apiErrorBanner');
    if (errEl) errEl.style.display = 'none';
  } catch (err) {
    state.backendConnected = false;
    updateUIConnectionError(err.message);
    showApiError(`Failed to fetch state: ${err.message}`);
  }
}

// Poll state every 400ms to stay synchronized with backend ticks
setInterval(fetchState, 400);

// ============================================================================
// 3. API Control Helpers
// ============================================================================
async function apiControlSimulation(action) {
  try {
    const res = await fetch('/api/control/simulation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.state) applyState(data.state);
  } catch (err) {
    console.error('Simulation control error:', err);
  }
}

let selectedDensityApproach = 'south';
let currentDensitySetting = 'medium';

async function apiControlTraffic(density, approach = null) {
  try {
    const targetApp = approach || selectedDensityApproach || 'south';
    currentDensitySetting = density;
    const res = await fetch('/api/control/traffic', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        density,
        approach: targetApp
      })
    });
    const data = await res.json();
    if (data.state) applyState(data.state);
    if (density === 'high') {
      burstSpawnVehicles(targetApp, 4);
    }
  } catch (err) {
    console.error('Traffic control error:', err);
  }
}

function addLocalEventLog(level, message) {
  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0');
  if (!state.recentEvents) state.recentEvents = [];
  state.recentEvents.unshift({ timestamp: timeStr, level, message });
  renderEventLog();
}

async function apiControlAmbulance(approach, routeOrActive = 'straight', active = true, reason = 'operator_dispatch', caller = 'api') {
  let route = 'straight';
  let isActive = true;
  let reqReason = reason;
  let reqCaller = caller;

  if (typeof routeOrActive === 'boolean') {
    isActive = routeOrActive;
    route = document.getElementById('ambulanceRoute')?.value || state.emergencyRoute || 'straight';
    if (typeof active === 'string') reqReason = active;
    if (typeof reason === 'string' && reason !== 'operator_dispatch') reqCaller = reason;
  } else {
    route = routeOrActive || 'straight';
    isActive = active;
    reqReason = reason;
    reqCaller = caller;
  }

  try {
    const res = await fetch(`/api/control/ambulance?_t=${Date.now()}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache'
      },
      body: JSON.stringify({
        approach,
        route,
        active: isActive,
        caller: reqCaller,
        reason: reqReason
      })
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      const detail = errJson.detail || `Server returned HTTP ${res.status}`;
      throw new Error(detail);
    }
    const data = await res.json();
    if (data.state) applyState(data.state);
    
    if (isActive) {
      spawnAmbulance3D(approach, route, reqCaller, reqReason);
    } else {
      const exitName = (ROUTE_EXIT_ROADS[approach]?.[route] || 'opposite').toUpperCase();
      addLocalEventLog('INFO', `Ambulance cleared intersection on ${approach.toUpperCase()} approach [Exit: ${exitName}] by ${reqCaller} (reason: ${reqReason}). Restoring standard cycles.`);
    }
  } catch (err) {
    console.error('Ambulance control error:', err);
    addLocalEventLog('ERROR', `Ambulance dispatch error: ${err.message}`);
    showApiError(`Ambulance dispatch error: ${err.message}`);
  }
}

async function apiControlPedestrian(active = true, crosswalk = null) {
  try {
    const chosenCrossing = crosswalk || document.getElementById('pedestrianCrossingSelect')?.value || 'north';

    // Prevent duplicate spam if already active or pending
    if (active && (state.pedestrianActive || state.phase.startsWith('PEDESTRIAN'))) {
      return;
    }

    const res = await fetch('/api/control/pedestrian', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active, crosswalk: chosenCrossing })
    });
    const data = await res.json();
    if (data.state) applyState(data.state);
  } catch (err) {
    console.error('Pedestrian control error:', err);
  }
}

function applyState(serverState) {
  const previousPhase = state.phase;
  state.backendConnected = true;
  state.phase = serverState.phase;
  state.phaseDisplay = serverState.phase_display;
  state.timeInPhase = serverState.time_in_phase;
  state.phaseDuration = serverState.phase_duration;
  state.signals = serverState.signals;
  state.emergencyActive = serverState.emergency_active;
  state.emergencyApproach = serverState.emergency_approach;
  state.emergencyRoute = serverState.emergency_route || 'straight';
  state.pedestrianActive = serverState.pedestrian_active;
  state.pedestrianRemaining = serverState.pedestrian_remaining;
  state.pedestrianCrosswalk = serverState.pedestrian_crosswalk || 'north';
  state.trafficDensity = serverState.traffic_density;
  state.simulationRunning = serverState.simulation_running;
  state.logic = serverState.logic;
  state.truthTable = serverState.truth_table;
  state.recentEvents = serverState.recent_events;

  // Adaptive controller extensions & metrics
  state.activeApproach = serverState.active_approach || 'north';
  state.greenExtended = !!serverState.green_extended;
  state.currentHighDemandApproach = serverState.current_high_demand_approach || 'south';
  state.approachMetrics = serverState.approach_metrics || {};
  state.countdowns = serverState.countdowns || {};
  state.minGreenDuration = serverState.min_green_duration || 8.0;
  state.normalGreenDuration = serverState.normal_green_duration || 12.0;
  state.maxGreenDuration = serverState.max_green_duration || 22.0;

  // Pedestrian synchronization: spawn pedestrians strictly during permitted WALK phase
  if (state.phase === 'PEDESTRIAN_WALK') {
    if (previousPhase !== 'PEDESTRIAN_WALK' || pedestrians3D.length === 0) {
      spawnPedestrians3D(state.pedestrianCrosswalk);
    }
  } else if (state.phase !== 'PEDESTRIAN_FLASHING') {
    if (pedestrians3D.length > 0) {
      clearAllPedestrians3D();
    }
  }

  // Emergency vehicle synchronization: if backend has active emergency preemption,
  // ensure the 3D scene has an active ambulance to clear the corridor
  if (state.emergencyActive && state.emergencyApproach) {
    const hasAmb = vehicles3D.some(v => v.isAmbulance);
    if (!hasAmb && (!window.lastClearedAmbulance || Date.now() - window.lastClearedAmbulance > 5000)) {
      spawnAmbulance3D(state.emergencyApproach, state.emergencyRoute || 'straight', 'serverStateSync', 'remote_emergency_preemption');
    }
  } else if (!state.emergencyActive) {
    for (let i = vehicles3D.length - 1; i >= 0; i--) {
      if (vehicles3D[i].isAmbulance && vehicles3D[i].hasClearedIntersection()) {
        vehicles3D[i].destroy();
        vehicles3D.splice(i, 1);
      }
    }
  }

  updateUI();
}

// ============================================================================
// 4. UI DOM Rendering & Updates
// ============================================================================
function updateUI() {
  const pill = document.getElementById('backendStatusPill');
  const pillText = document.getElementById('backendStatusText');
  if (state.backendConnected) {
    pill.classList.remove('error');
    pillText.textContent = 'FASTAPI ENGINE ONLINE';
  } else {
    pill.classList.add('error');
    pillText.textContent = 'CONNECTING TO ENGINE...';
  }

  document.getElementById('telemetryPhase').textContent = state.phaseDisplay || state.phase;
  document.getElementById('telemetryTimer').textContent = 
    `${state.timeInPhase.toFixed(1)}s / ${state.phaseDuration.toFixed(1)}s`;

  // Update Dynamic High-Demand Direction Badge
  const highDemandBadge = document.getElementById('highDemandBadge');
  if (highDemandBadge) {
    highDemandBadge.textContent = (state.currentHighDemandApproach || 'SOUTH').toUpperCase();
  }

  updateHudLight('north', state.signals?.north);
  updateHudLight('south', state.signals?.south);
  updateHudLight('east', state.signals?.east);
  updateHudLight('west', state.signals?.west);

  const banner = document.getElementById('priorityBanner');
  if (state.emergencyActive) {
    banner.style.display = 'flex';
    const appStr = state.emergencyApproach ? state.emergencyApproach.toUpperCase() : 'APPROACHING';
    const routeStr = (state.emergencyRoute || 'straight').toUpperCase();
    const exitStr = (ROUTE_EXIT_ROADS[state.emergencyApproach]?.[state.emergencyRoute || 'straight'] || 'opposite').toUpperCase();
    const isPriorityGranted = state.phase === 'EMERGENCY_PRIORITY';

    if (isPriorityGranted) {
      banner.className = 'priority-banner active-cleared';
      document.getElementById('priorityBannerText').textContent = 
        `AMBULANCE PRIORITY: ${appStr} EXCLUSIVE GREEN [${routeStr} -> ${exitStr} EXIT]`;
    } else {
      banner.className = 'priority-banner safety-clearance';
      document.getElementById('priorityBannerText').textContent = 
        `AMBULANCE INCOMING (${appStr}) — CLEARING INTERSECTION`;
    }
  } else {
    banner.style.display = 'none';
  }

  const pedBadge = document.getElementById('pedCountdownBadge');
  if (state.pedestrianRemaining > 0) {
    pedBadge.classList.add('active');
    const crossStr = state.pedestrianCrosswalk ? state.pedestrianCrosswalk.toUpperCase() : 'CROSSING';
    pedBadge.textContent = `${crossStr} WALK: ${state.pedestrianRemaining.toFixed(1)}s`;
  } else if (state.pedestrianActive) {
    pedBadge.classList.add('active');
    pedBadge.textContent = 'CLEARING VEHICLES...';
  } else {
    pedBadge.classList.remove('active');
    pedBadge.textContent = 'Walk Inactive';
  }

  document.querySelectorAll('.btn-approach').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.approach === (selectedDensityApproach || state.currentHighDemandApproach || 'south'));
  });

  document.querySelectorAll('.btn-toggle').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.density === state.trafficDensity);
  });

  renderLogicBadges();
  renderTruthTable();
  renderEventLog();
}

function updateHudLight(dir, sig) {
  const capDir = dir.charAt(0).toUpperCase() + dir.slice(1).toLowerCase();
  const hudLight = document.getElementById(`hudLight${capDir}`);
  const hudPed = document.getElementById(`hudPed${capDir}`);
  const hudTimer = document.getElementById(`hudTimer${capDir}`);
  const hudExt = document.getElementById(`hudExt${capDir}`);
  const hudDensity = document.getElementById(`hudDensity${capDir}`);
  const hudOverlay = document.getElementById(`hud${capDir}`);

  const panelLight = document.getElementById(`panelLight${capDir}`);
  const panelPed = document.getElementById(`panelPed${capDir}`);
  const panelTimer = document.getElementById(`panelTimer${capDir}`);
  const panelExt = document.getElementById(`badgeExt${capDir}`);
  const panelDensity = document.getElementById(`panelDensity${capDir}`);
  const badge = document.getElementById(`badge${capDir}`);

  if (!sig) return;

  const colorClass = sig.vehicle.toLowerCase();
  const lightText = `● ${sig.vehicle}`;

  let pedText = 'DONT WALK';
  let pedClass = 'dont-walk';
  if (sig.pedestrian === 'WALK') {
    pedText = 'WALK';
    pedClass = 'walk';
  } else if (sig.pedestrian === 'FLASHING_DONT_WALK') {
    pedText = 'CLEAR (FLASH)';
    pedClass = 'flash';
  }

  // Countdowns (strictly non-negative, PRIORITY / HOLD handling during emergency preemption)
  const cdVal = state.countdowns ? state.countdowns[dir] : undefined;
  let timerText = '--s';
  let timerClass = '';

  if (state.emergencyActive) {
    if (dir === (state.emergencyApproach || 'south').toLowerCase()) {
      timerText = 'PRIORITY';
      timerClass = 'priority';
    } else {
      timerText = 'HOLD';
      timerClass = 'hold';
    }
  } else if (typeof cdVal === 'number') {
    if (cdVal < 0) {
      timerText = 'HOLD';
      timerClass = 'hold';
    } else {
      timerText = `${Math.max(0, Math.round(cdVal))}s`;
    }
  }

  // Green extension indicator
  const isExtended = !!state.greenExtended && (dir === state.activeApproach) && (sig.vehicle === 'GREEN');

  // Approach queue and density metrics
  const metric = state.approachMetrics ? state.approachMetrics[dir] : null;
  const queueLen = metric ? metric.queue_length : 0;
  const density = metric ? metric.density.toLowerCase() : 'low';
  const lQueues = metric && metric.lane_queues ? metric.lane_queues : null;
  const l1 = lQueues ? (lQueues.lane1 ?? Math.round(queueLen / 2)) : Math.round(queueLen / 2);
  const l2 = lQueues ? (lQueues.lane2 ?? (queueLen - l1)) : (queueLen - l1);

  if (hudLight) {
    hudLight.textContent = lightText;
    hudLight.className = `hud-light ${colorClass}`;
  }
  if (hudTimer) {
    hudTimer.textContent = timerText;
    hudTimer.className = `hud-timer ${timerClass}`;
  }
  if (hudExt) {
    hudExt.style.display = isExtended ? 'inline-block' : 'none';
  }
  if (hudDensity) {
    hudDensity.textContent = `Q:${queueLen} [L1:${l1}|L2:${l2}]`;
    hudDensity.className = `hud-density ${density}`;
  }
  if (hudOverlay) {
    hudOverlay.classList.toggle('active-green', sig.vehicle === 'GREEN');
    hudOverlay.classList.toggle('extended', isExtended);
  }

  if (hudPed) {
    hudPed.textContent = `PED: ${pedText}`;
    hudPed.className = `hud-ped ${pedClass}`;
  }

  if (panelLight) {
    panelLight.textContent = lightText;
    panelLight.className = `badge-light ${colorClass}`;
  }
  if (panelTimer) {
    panelTimer.textContent = timerText;
    panelTimer.className = `badge-timer ${timerClass}`;
  }
  if (panelExt) {
    panelExt.style.display = isExtended ? 'inline-block' : 'none';
  }
  if (panelDensity) {
    panelDensity.textContent = `${density.toUpperCase()} (${queueLen}) [L1:${l1}|L2:${l2}]`;
    panelDensity.className = `badge-density ${density}`;
  }
  if (panelPed) {
    panelPed.textContent = pedText;
    panelPed.className = `badge-ped ${pedClass}`;
  }
  if (badge) {
    badge.classList.toggle('active-green', sig.vehicle === 'GREEN');
    badge.classList.toggle('extended', isExtended);
  }
}

function renderLogicBadges() {
  const { p, q, r, g, active_row, description } = state.logic;
  
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = val ? '1' : '0';
    el.classList.toggle('true', val);
  };

  setVal('evalValP', p);
  setVal('evalValQ', q);
  setVal('evalValR', r);
  setVal('evalValG', g);

  const expEl = document.getElementById('logicExplanation');
  if (expEl) {
    expEl.innerHTML = `<strong>Active Case (Row ${active_row}):</strong> ${description || 'Operating under normal parameters.'}`;
  }
}

function renderTruthTable() {
  const tbody = document.getElementById('truthTableBody');
  if (!tbody || !state.truthTable || state.truthTable.length === 0) return;

  const currentActiveRow = state.logic.active_row;

  tbody.innerHTML = state.truthTable.map(row => {
    const isActive = row.row_id === currentActiveRow;
    return `
      <tr class="${isActive ? 'active-row' : ''}">
        <td><strong>${row.row_id}</strong></td>
        <td>${row.p ? 1 : 0}</td>
        <td>${row.q ? 1 : 0}</td>
        <td>${row.r ? 1 : 0}</td>
        <td>${row.p_or_q ? 1 : 0}</td>
        <td>${row.not_r ? 1 : 0}</td>
        <td><strong>${row.g ? 1 : 0}</strong></td>
        <td>${row.description}</td>
      </tr>
    `;
  }).join('');
}

function renderEventLog() {
  const container = document.getElementById('eventLogList');
  if (!container || !state.recentEvents) return;

  container.innerHTML = state.recentEvents.slice(0, 20).map(evt => `
    <div class="log-entry ${evt.level}">
      <span class="log-time">[${evt.timestamp}]</span>
      <span class="log-level">${evt.level}:</span>
      <span class="log-msg">${evt.message}</span>
    </div>
  `).join('');
}

function updateUIConnectionError(msg) {
  const pill = document.getElementById('backendStatusPill');
  const pillText = document.getElementById('backendStatusText');
  pill.classList.add('error');
  pillText.textContent = 'CONNECTING TO FASTAPI...';
}

// ============================================================================
// 5. OPERATOR CONTROLS & SPEED METER EVENT LISTENERS
// ============================================================================

document.getElementById('btnStart').addEventListener('click', () => apiControlSimulation('start'));
document.getElementById('btnPause').addEventListener('click', () => apiControlSimulation('pause'));
document.getElementById('btnStep').addEventListener('click', () => apiControlSimulation('step'));
document.getElementById('btnReset').addEventListener('click', () => {
  clearAllVehicles3D();
  clearAllPedestrians3D();
  apiControlSimulation('reset');
});

document.querySelectorAll('.btn-approach').forEach(btn => {
  btn.addEventListener('click', () => {
    selectedDensityApproach = btn.dataset.approach;
    document.querySelectorAll('.btn-approach').forEach(b => {
      b.classList.toggle('active', b.dataset.approach === selectedDensityApproach);
    });
    apiControlTraffic(currentDensitySetting, selectedDensityApproach);
  });
});

document.querySelectorAll('.btn-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    currentDensitySetting = btn.dataset.density;
    apiControlTraffic(btn.dataset.density, selectedDensityApproach);
  });
});

document.getElementById('btnAmbulanceDispatch').addEventListener('click', () => {
  const approach = document.getElementById('ambulanceApproach')?.value || 'south';
  const route = document.getElementById('ambulanceRoute')?.value || 'straight';
  apiControlAmbulance(approach, route, true, 'operator_dispatch_button', 'UI.btnAmbulanceDispatch');
});

document.getElementById('btnAmbulanceClear').addEventListener('click', () => {
  const approach = document.getElementById('ambulanceApproach')?.value || 'south';
  const route = document.getElementById('ambulanceRoute')?.value || 'straight';
  // Explicit manual operator clear: remove active ambulance models from 3D scene
  for (let i = vehicles3D.length - 1; i >= 0; i--) {
    if (vehicles3D[i].isAmbulance) {
      vehicles3D[i].destroy();
      vehicles3D.splice(i, 1);
    }
  }
  apiControlAmbulance(approach, route, false, 'operator_manual_clear_button', 'UI.btnAmbulanceClear');
});

document.getElementById('btnPedestrianWalk').addEventListener('click', () => {
  const chosenCrossing = document.getElementById('pedestrianCrossingSelect')?.value || 'north';
  apiControlPedestrian(true, chosenCrossing);
});

document.getElementById('btnClearLog').addEventListener('click', () => {
  state.recentEvents = [];
  renderEventLog();
});

// Vehicle Speed Slider & Preset Buttons
const speedSlider = document.getElementById('vehicleSpeedSlider');
const speedReadout = document.getElementById('speedReadout');
const telemetryTargetSpeed = document.getElementById('telemetryTargetSpeed');

function setVehicleSpeed(speedKmh) {
  selectedSpeedKmh = Math.max(10, Math.min(100, Number(speedKmh)));
  if (speedSlider) speedSlider.value = selectedSpeedKmh;
  if (speedReadout) speedReadout.textContent = `${selectedSpeedKmh} km/h`;
  if (telemetryTargetSpeed) telemetryTargetSpeed.textContent = `${selectedSpeedKmh} km/h`;

  document.querySelectorAll('.speed-presets .btn').forEach(b => {
    b.classList.remove('btn-primary');
    b.classList.add('btn-secondary');
  });

  if (selectedSpeedKmh === 25) document.getElementById('btnSpeedSlow')?.classList.replace('btn-secondary', 'btn-primary');
  else if (selectedSpeedKmh === 50) document.getElementById('btnSpeedNormal')?.classList.replace('btn-secondary', 'btn-primary');
  else if (selectedSpeedKmh === 80) document.getElementById('btnSpeedFast')?.classList.replace('btn-secondary', 'btn-primary');
}

if (speedSlider) {
  speedSlider.addEventListener('input', (e) => {
    setVehicleSpeed(e.target.value);
  });
}

document.getElementById('btnSpeedSlow')?.addEventListener('click', () => setVehicleSpeed(25));
document.getElementById('btnSpeedNormal')?.addEventListener('click', () => setVehicleSpeed(50));
document.getElementById('btnSpeedFast')?.addEventListener('click', () => setVehicleSpeed(80));

// ============================================================================
// 6. THREE.JS 3D SCENE & CINEMATIC ISOMETRIC SETUP
// ============================================================================

let scene, camera, renderer, controls;
let ambientLight, sunLight, ambulancePointLight;
const vehicles3D = [];
const pedestrians3D = [];
window.vehicles3D = vehicles3D;
window.pedestrians3D = pedestrians3D;
let signalLenses3D = {};
window.signalLenses3D = signalLenses3D;
let lastSpawn3D = 0;
let beaconTimer = 0;

const ROAD_WIDTH_3D = 16;
const HALF_ROAD_3D = 8;
const LANE_WIDTH_3D = 4;
const STOP_LINE_DIST_3D = 12.0; // Stop line placed 12.0 units from center (1.4 units before crosswalk)
const CROSSWALK_DIST_3D = 9.4;   // Zebra crosswalk placed between 8.2 and 10.6
const BOUNDS_3D = 55;
const EXIT_BOUNDARY_DIST_3D = 38.0; // Distance along exit road where emergency corridor is considered cleared

// Exact 12 route-to-exit mappings from driver's perspective
const ROUTE_EXIT_ROADS = {
  south: { straight: 'north', left: 'east',  right: 'west' },
  north: { straight: 'south', left: 'west',  right: 'east' },
  east:  { straight: 'west',  left: 'north', right: 'south' },
  west:  { straight: 'east',  left: 'south', right: 'north' }
};

// Mathematically verified Cubic Bézier curves for smooth realistic turning through intersection
// Lane 0: Outer / Curb lane (offset 6.0)
const TURN_CURVES = {
  south: {
    left:  { p0: [6, 10],   p1: [6, 6],   p2: [6, 6],   p3: [10, 6],   exitHeading: Math.PI / 2,  length: 7.21 },
    right: { p0: [6, 10],   p1: [6, -1],  p2: [-1, -6], p3: [-10, -6], exitHeading: -Math.PI / 2, length: 25.67 }
  },
  north: {
    left:  { p0: [-6, -10], p1: [-6, -6], p2: [-6, -6], p3: [-10, -6], exitHeading: -Math.PI / 2, length: 7.21 },
    right: { p0: [-6, -10], p1: [-6, 1],  p2: [1, 6],   p3: [10, 6],   exitHeading: Math.PI / 2,  length: 25.67 }
  },
  east: {
    left:  { p0: [10, -6],  p1: [6, -6],  p2: [6, -6],  p3: [6, -10],  exitHeading: Math.PI,      length: 7.21 },
    right: { p0: [10, -6],  p1: [-1, -6], p2: [-6, 1],  p3: [-6, 10],  exitHeading: 0,            length: 25.67 }
  },
  west: {
    left:  { p0: [-10, 6],  p1: [-6, 6],  p2: [-6, 6],  p3: [-6, 10],  exitHeading: 0,            length: 7.21 },
    right: { p0: [-10, 6],  p1: [1, 6],   p2: [6, -1],  p3: [6, -10],  exitHeading: Math.PI,      length: 25.67 }
  }
};

// Lane 1: Inner / Median lane (offset 2.0)
const TURN_CURVES_LANE1 = {
  south: {
    left:  { p0: [2, 10],   p1: [2, 2],   p2: [2, 2],   p3: [10, 2],   exitHeading: Math.PI / 2,  length: 7.21 },
    right: { p0: [2, 10],   p1: [2, -1],  p2: [-1, -2], p3: [-10, -2], exitHeading: -Math.PI / 2, length: 25.67 }
  },
  north: {
    left:  { p0: [-2, -10], p1: [-2, -2], p2: [-2, -2], p3: [-10, -2], exitHeading: -Math.PI / 2, length: 7.21 },
    right: { p0: [-2, -10], p1: [-2, 1],  p2: [1, 2],   p3: [10, 2],   exitHeading: Math.PI / 2,  length: 25.67 }
  },
  east: {
    left:  { p0: [10, -2],  p1: [2, -2],  p2: [2, -2],  p3: [2, -10],  exitHeading: Math.PI,      length: 7.21 },
    right: { p0: [10, -2],  p1: [-1, -2], p2: [-2, 1],  p3: [-2, 10],  exitHeading: 0,            length: 25.67 }
  },
  west: {
    left:  { p0: [-10, 2],  p1: [-2, 2],  p2: [-2, 2],  p3: [-2, 10],  exitHeading: 0,            length: 7.21 },
    right: { p0: [-10, 2],  p1: [1, 2],   p2: [2, -1],  p3: [2, -10],  exitHeading: Math.PI,      length: 25.67 }
  }
};

function getVehicleTurnCurve(approach, route, laneIndex = 0) {
  if (laneIndex === 1 && TURN_CURVES_LANE1[approach]?.[route]) {
    return TURN_CURVES_LANE1[approach][route];
  }
  return TURN_CURVES[approach]?.[route];
}

function evalCubicBezier(p0, p1, p2, p3, t) {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const t2 = t * t;
  return [
    mt2 * mt * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t2 * t * p3[0],
    mt2 * mt * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t2 * t * p3[1]
  ];
}

function evalCubicBezierTangent(p0, p1, p2, p3, t) {
  const mt = 1 - t;
  const t2 = t * t;
  return [
    3 * mt * mt * (p1[0] - p0[0]) + 6 * mt * t * (p2[0] - p1[0]) + 3 * t2 * (p3[0] - p2[0]),
    3 * mt * mt * (p1[1] - p0[1]) + 6 * mt * t * (p2[1] - p1[1]) + 3 * t2 * (p3[1] - p2[1])
  ];
}

// Balanced palette for distinct passenger vehicles inspired by clean automotive illustration
const CAR_PAINTS = [
  0x38bdf8, // Sky Blue
  0x10b981, // Emerald Mint
  0xf43f5e, // Coral Crimson
  0xf59e0b, // Amber Gold
  0x6366f1, // Royal Indigo
  0x0284c7, // Ocean Blue
  0xf8fafc, // Pearl White
  0x475569, // Slate Charcoal
  0xea580c, // Sunset Orange
  0x0d9488, // Forest Teal
  0x8b5cf6  // Vivid Violet
];

function init3D() {
  const container = document.getElementById('webglContainer');
  if (!container) return;

  const width = container.clientWidth || 760;
  const height = container.clientHeight || 760;

  // 1. Scene with soft atmospheric haze
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a101d);
  scene.fog = new THREE.FogExp2(0x0a101d, 0.007);

  // 2. Camera with moderate, cinematic perspective angle
  // Using FOV 40 for a natural diorama / architectural isometric view
  camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 500);
  setCameraPreset('isometric');

  // 3. WebGL Renderer with soft shadows
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputEncoding = THREE.sRGBEncoding;
  container.innerHTML = '';
  container.appendChild(renderer.domElement);

  // 4. OrbitControls with smooth damping
  if (typeof THREE.OrbitControls !== 'undefined') {
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.06; // Prevent dipping beneath asphalt
    controls.minDistance = 15;
    controls.maxDistance = 140;
    controls.target.set(0, 0.5, 0);
  }

  // 5. Lighting Setup (Balanced for High Visibility & Crisp Shadows)
  ambientLight = new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 0.95);
  scene.add(ambientLight);

  sunLight = new THREE.DirectionalLight(0xfffbeb, 1.45);
  sunLight.position.set(45, 65, 35);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.width = 2048;
  sunLight.shadow.mapSize.height = 2048;
  sunLight.shadow.camera.near = 10;
  sunLight.shadow.camera.far = 160;
  sunLight.shadow.camera.left = -40;
  sunLight.shadow.camera.right = 40;
  sunLight.shadow.camera.top = 40;
  sunLight.shadow.camera.bottom = -40;
  sunLight.shadow.bias = -0.0004;
  scene.add(sunLight);

  // Dynamic Emergency Strobe PointLight
  ambulancePointLight = new THREE.PointLight(0xef4444, 0, 45, 2.5);
  ambulancePointLight.position.set(0, 4, 0);
  scene.add(ambulancePointLight);

  // 6. Build Unobstructed 3D City Infrastructure
  build3DCityInfrastructure();

  // Expose handles on window for verification & diagnostics
  window.scene = scene;
  window.camera = camera;
  window.renderer = renderer;
  window.controls = controls;

  // 7. Window resize handling
  window.addEventListener('resize', onWindowResize);
  const resizeObserver = new ResizeObserver(() => onWindowResize());
  resizeObserver.observe(container);

  // 8. Camera preset buttons
  setupCameraButtons();

  // 9. Start 3D Loop (Independent of Network Requests)
  requestAnimationFrame(animate3D);
}

function onWindowResize() {
  const container = document.getElementById('webglContainer');
  if (!container || !renderer || !camera) return;
  const width = container.clientWidth;
  const height = container.clientHeight;
  if (width === 0 || height === 0) return;

  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}

function setCameraPreset(mode) {
  if (!camera) return;
  if (mode === 'isometric') {
    // Cinematic elevated isometric view: moderate ~35 deg elevation, perfectly centering intersection
    camera.up.set(0, 1, 0);
    camera.position.set(38, 30, 42);
    if (controls) controls.target.set(0, 0.5, 0);
  } else if (mode === 'topdown') {
    // True orthogonal-style topdown overhead plan view with North facing straight up
    camera.up.set(0, 0, -1);
    camera.position.set(0, 72, 0);
    if (controls) controls.target.set(0, 0, 0);
  } else if (mode === 'street') {
    camera.up.set(0, 1, 0);
    camera.position.set(0, 2.8, 32);
    if (controls) controls.target.set(0, 1.8, 0);
  }
  camera.lookAt(0, 0.5, 0);
  if (controls) controls.update();

  document.querySelectorAll('.cam-btn').forEach(b => b.classList.remove('active'));
  if (mode === 'isometric') document.getElementById('btnCamIsometric')?.classList.add('active');
  if (mode === 'topdown') document.getElementById('btnCamTopDown')?.classList.add('active');
  if (mode === 'street') document.getElementById('btnCamStreet')?.classList.add('active');
}

function setupCameraButtons() {
  document.getElementById('btnCamIsometric')?.addEventListener('click', () => setCameraPreset('isometric'));
  document.getElementById('btnCamTopDown')?.addEventListener('click', () => setCameraPreset('topdown'));
  document.getElementById('btnCamStreet')?.addEventListener('click', () => setCameraPreset('street'));
  document.getElementById('btnCamReset')?.addEventListener('click', () => setCameraPreset('isometric'));

  // Compass widget click re-aligns camera to face North
  document.getElementById('compassWidget')?.addEventListener('click', () => {
    if (!camera || !controls) return;
    const dist = Math.hypot(camera.position.x, camera.position.z);
    camera.position.x = 0.001;
    camera.position.z = Math.max(15, dist);
    if (controls) controls.target.set(0, 0.5, 0);
    camera.lookAt(0, 0.5, 0);
    if (controls) controls.update();
    if (typeof updateCompass === 'function') updateCompass();
  });
}

// ============================================================================
// 7. 3D CITY INFRASTRUCTURE & CORRECT SIGNAL ORIENTATIONS
// ============================================================================

function build3DCityInfrastructure() {
  const cityGroup = new THREE.Group();

  // A. Ground Base
  const groundGeo = new THREE.PlaneGeometry(160, 160);
  const groundMat = new THREE.MeshStandardMaterial({ color: 0x090e18, roughness: 0.95 });
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.05;
  ground.receiveShadow = true;
  cityGroup.add(ground);

  // B. Asphalt Road Surface (High Contrast against Markings & Cars)
  const roadMat = new THREE.MeshStandardMaterial({ color: 0x182030, roughness: 0.82, metalness: 0.1 });

  // North-South Road
  const nsRoad = new THREE.Mesh(new THREE.PlaneGeometry(ROAD_WIDTH_3D, 120), roadMat);
  nsRoad.rotation.x = -Math.PI / 2;
  nsRoad.position.y = 0.01;
  nsRoad.receiveShadow = true;
  cityGroup.add(nsRoad);

  // East-West Road
  const ewRoad = new THREE.Mesh(new THREE.PlaneGeometry(120, ROAD_WIDTH_3D), roadMat);
  ewRoad.rotation.x = -Math.PI / 2;
  ewRoad.position.y = 0.012;
  ewRoad.receiveShadow = true;
  cityGroup.add(ewRoad);

  // C. Raised Sidewalks with Concrete Curbs
  const sidewalkMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.75 });
  const curbMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.5 });
  const sideSize = 52;
  const sideH = 0.28;

  const quadrants = [
    { x: -sideSize / 2 - HALF_ROAD_3D, z: -sideSize / 2 - HALF_ROAD_3D },
    { x: sideSize / 2 + HALF_ROAD_3D, z: -sideSize / 2 - HALF_ROAD_3D },
    { x: -sideSize / 2 - HALF_ROAD_3D, z: sideSize / 2 + HALF_ROAD_3D },
    { x: sideSize / 2 + HALF_ROAD_3D, z: sideSize / 2 + HALF_ROAD_3D }
  ];

  quadrants.forEach(q => {
    const sw = new THREE.Mesh(new THREE.BoxGeometry(sideSize, sideH, sideSize), sidewalkMat);
    sw.position.set(q.x, sideH / 2, q.z);
    sw.receiveShadow = true;
    cityGroup.add(sw);

    // Curb edge strips
    const curb1 = new THREE.Mesh(new THREE.BoxGeometry(sideSize, 0.06, 0.4), curbMat);
    curb1.position.set(q.x, sideH + 0.03, q.z > 0 ? HALF_ROAD_3D + 0.2 : -HALF_ROAD_3D - 0.2);
    cityGroup.add(curb1);

    const curb2 = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.06, sideSize), curbMat);
    curb2.position.set(q.x > 0 ? HALF_ROAD_3D + 0.2 : -HALF_ROAD_3D - 0.2, sideH + 0.03, q.z);
    cityGroup.add(curb2);
  });

  // D. Road Markings (Yellow Centerlines, White Dashes, Stop Lines, Zebra Crosswalks)
  buildRoadMarkings(cityGroup);

  // E. 3D Cantilever Traffic Signal Poles (Fixed in World Space, Correctly Facing Traffic)
  buildTrafficSignalPoles(cityGroup);

  // F. 3D Streetlights
  buildStreetlights(cityGroup);

  // G. Background Buildings & Foreground Metro Plaza (Unobstructed View)
  buildCityBuildingsAndPlaza(cityGroup);

  // H. Sidewalk Trees
  buildSidewalkTrees(cityGroup);

  scene.add(cityGroup);
}

function buildRoadMarkings(group) {
  const yellowMat = new THREE.MeshBasicMaterial({ color: 0xfacc15 });
  const whiteMat = new THREE.MeshBasicMaterial({ color: 0xffffff });

  // 1. Double Yellow Centerlines
  const makeCenterline = (x, z, w, l) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, l), yellowMat);
    m.rotation.x = -Math.PI / 2;
    m.position.set(x, 0.02, z);
    group.add(m);
  };

  // North Centerlines
  makeCenterline(-0.16, -34, 0.14, 46);
  makeCenterline(0.16, -34, 0.14, 46);
  // South Centerlines
  makeCenterline(-0.16, 34, 0.14, 46);
  makeCenterline(0.16, 34, 0.14, 46);
  // West Centerlines
  makeCenterline(-34, -0.16, 46, 0.14);
  makeCenterline(-34, 0.16, 46, 0.14);
  // East Centerlines
  makeCenterline(34, -0.16, 46, 0.14);
  makeCenterline(34, 0.16, 46, 0.14);

  // 2. Dashed White Lane Dividers
  const makeDashedLane = (startX, startZ, endX, endZ, isHorizontal) => {
    const dashLength = 1.0;
    const gapLength = 1.2;
    const totalDist = Math.abs(isHorizontal ? endX - startX : endZ - startZ);
    const count = Math.floor(totalDist / (dashLength + gapLength));

    for (let i = 0; i < count; i++) {
      const step = i * (dashLength + gapLength);
      const m = new THREE.Mesh(
        new THREE.PlaneGeometry(isHorizontal ? dashLength : 0.15, isHorizontal ? 0.15 : dashLength),
        whiteMat
      );
      m.rotation.x = -Math.PI / 2;
      if (isHorizontal) {
        const cx = startX < endX ? startX + step + dashLength / 2 : startX - step - dashLength / 2;
        m.position.set(cx, 0.022, startZ);
      } else {
        const cz = startZ < endZ ? startZ + step + dashLength / 2 : startZ - step - dashLength / 2;
        m.position.set(startX, 0.022, cz);
      }
      group.add(m);
    }
  };

  // North lane dividers
  makeDashedLane(-LANE_WIDTH_3D, -STOP_LINE_DIST_3D - 0.5, -LANE_WIDTH_3D, -BOUNDS_3D, false);
  makeDashedLane(LANE_WIDTH_3D, -STOP_LINE_DIST_3D - 0.5, LANE_WIDTH_3D, -BOUNDS_3D, false);
  // South lane dividers
  makeDashedLane(-LANE_WIDTH_3D, STOP_LINE_DIST_3D + 0.5, -LANE_WIDTH_3D, BOUNDS_3D, false);
  makeDashedLane(LANE_WIDTH_3D, STOP_LINE_DIST_3D + 0.5, LANE_WIDTH_3D, BOUNDS_3D, false);
  // West lane dividers
  makeDashedLane(-STOP_LINE_DIST_3D - 0.5, -LANE_WIDTH_3D, -BOUNDS_3D, -LANE_WIDTH_3D, true);
  makeDashedLane(-STOP_LINE_DIST_3D - 0.5, LANE_WIDTH_3D, -BOUNDS_3D, LANE_WIDTH_3D, true);
  // East lane dividers
  makeDashedLane(STOP_LINE_DIST_3D + 0.5, -LANE_WIDTH_3D, BOUNDS_3D, -LANE_WIDTH_3D, true);
  makeDashedLane(STOP_LINE_DIST_3D + 0.5, LANE_WIDTH_3D, BOUNDS_3D, LANE_WIDTH_3D, true);

  // 3. Solid White Stop Lines (Placed at distance 12.0 from center, giving 1.4 units setback before crosswalk)
  const makeStopLine = (x, z, w, l) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, l), whiteMat);
    m.rotation.x = -Math.PI / 2;
    m.position.set(x, 0.025, z);
    group.add(m);
  };
  // North approach stop line (incoming Southbound on -X side)
  makeStopLine(-LANE_WIDTH_3D, -STOP_LINE_DIST_3D, HALF_ROAD_3D, 0.7);
  // South approach stop line (incoming Northbound on +X side)
  makeStopLine(LANE_WIDTH_3D, STOP_LINE_DIST_3D, HALF_ROAD_3D, 0.7);
  // West approach stop line (incoming Eastbound on +Z side)
  makeStopLine(-STOP_LINE_DIST_3D, LANE_WIDTH_3D, 0.7, HALF_ROAD_3D);
  // East approach stop line (incoming Westbound on -Z side)
  makeStopLine(STOP_LINE_DIST_3D, -LANE_WIDTH_3D, 0.7, HALF_ROAD_3D);

  // 4. High-Contrast 3D Zebra Crosswalks (Centered at distance 9.4 units from center, between curbs)
  const makeZebraCrosswalk = (startX, startZ, isHorizontal) => {
    const stripes = 11;
    const stripeWidth = 0.88;
    const stripeLength = 2.8;
    const step = (ROAD_WIDTH_3D - 1.0) / stripes;
    const crosswalkMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.15,
      emissive: 0xffffff,
      emissiveIntensity: 0.45
    });

    for (let i = 0; i < stripes; i++) {
      const stripe = new THREE.Mesh(
        new THREE.PlaneGeometry(
          isHorizontal ? stripeWidth : stripeLength,
          isHorizontal ? stripeLength : stripeWidth
        ),
        crosswalkMat
      );
      stripe.rotation.x = -Math.PI / 2;
      if (isHorizontal) {
        stripe.position.set(startX - HALF_ROAD_3D + 0.8 + i * step, 0.038, startZ);
      } else {
        stripe.position.set(startX, 0.038, startZ - HALF_ROAD_3D + 0.8 + i * step);
      }
      group.add(stripe);
    }
  };

  makeZebraCrosswalk(0, -CROSSWALK_DIST_3D, true);  // North crosswalk
  makeZebraCrosswalk(0, CROSSWALK_DIST_3D, true);   // South crosswalk
  makeZebraCrosswalk(-CROSSWALK_DIST_3D, 0, false); // West crosswalk
  makeZebraCrosswalk(CROSSWALK_DIST_3D, 0, false);  // East crosswalk

  // 5. Large, Readable 3D Road Labels Anchored to Physical Approach Roads Before Stop Lines
  buildRoadDirectionLabels(group);
}

function drawCanvasRoundRect(ctx, x, y, w, h, r) {
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(x, y, w, h, r);
  } else {
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
  }
}

function createRoadLabelCanvas(direction, arrowChar, subtitle, colorHex, isVertical = false) {
  const canvas = document.createElement('canvas');
  if (isVertical) {
    canvas.width = 640;
    canvas.height = 1024;
  } else {
    canvas.width = 1024;
    canvas.height = 600;
  }
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  // Clear canvas
  ctx.clearRect(0, 0, w, h);

  // Background plaque with rounded corners
  const pad = 16;
  const rad = 28;
  ctx.save();
  ctx.beginPath();
  drawCanvasRoundRect(ctx, pad, pad, w - pad * 2, h - pad * 2, rad);
  ctx.fillStyle = 'rgba(11, 15, 25, 0.94)';
  ctx.fill();

  // Glowing perimeter border
  ctx.strokeStyle = colorHex;
  ctx.lineWidth = 14;
  ctx.shadowColor = colorHex;
  ctx.shadowBlur = 24;
  ctx.stroke();
  ctx.restore();

  // Corner bracket accents
  ctx.save();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 5;
  const bLen = 32;
  // Top-left
  ctx.beginPath();
  ctx.moveTo(pad + 12, pad + 12 + bLen);
  ctx.lineTo(pad + 12, pad + 12);
  ctx.lineTo(pad + 12 + bLen, pad + 12);
  ctx.stroke();
  // Top-right
  ctx.beginPath();
  ctx.moveTo(w - pad - 12 - bLen, pad + 12);
  ctx.lineTo(w - pad - 12, pad + 12);
  ctx.lineTo(w - pad - 12, pad + 12 + bLen);
  ctx.stroke();
  // Bottom-left
  ctx.beginPath();
  ctx.moveTo(pad + 12, h - pad - 12 - bLen);
  ctx.lineTo(pad + 12, h - pad - 12);
  ctx.lineTo(pad + 12 + bLen, h - pad - 12);
  ctx.stroke();
  // Bottom-right
  ctx.beginPath();
  ctx.moveTo(w - pad - 12 - bLen, h - pad - 12);
  ctx.lineTo(w - pad - 12, h - pad - 12);
  ctx.lineTo(w - pad - 12, h - pad - 12 - bLen);
  ctx.stroke();
  ctx.restore();

  // Content typography
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  if (!isVertical) {
    // Horizontal layout (North & South approaches)
    // 1. Header tag
    ctx.font = '800 32px monospace';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText('APPROACH ROAD • TWO LANES', w / 2, 85);

    // 2. Primary Direction Title with Arrow (e.g. "NORTH ↑", "SOUTH ↓")
    ctx.font = '900 138px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.9)';
    ctx.shadowBlur = 20;
    ctx.fillText(`${direction} ${arrowChar}`, w / 2, 235);
    ctx.shadowBlur = 0;

    // 3. Subtitle / Movement Direction
    ctx.font = '800 36px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = colorHex;
    ctx.fillText(subtitle, w / 2, 365);

    // 4. Lane divider ticks and labels
    ctx.font = '700 32px monospace';
    ctx.fillStyle = '#64748b';
    ctx.fillText('◀ LANE 2 (CURB)   |   LANE 1 (INNER) ▶', w / 2, 490);
  } else {
    // Vertical layout (East & West approaches)
    // 1. Header tag
    ctx.font = '800 30px monospace';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText('APPROACH ROAD', w / 2, 85);

    // 2. Primary Direction Title
    ctx.font = '900 132px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.9)';
    ctx.shadowBlur = 20;
    ctx.fillText(direction, w / 2, 235);
    ctx.shadowBlur = 0;

    // 3. Large Directional Arrow
    ctx.font = '900 152px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = colorHex;
    ctx.fillText(arrowChar, w / 2, 415);

    // 4. Subtitle / Movement Direction
    ctx.font = '800 36px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(`INCOMING FROM ${direction}`, w / 2, 570);

    ctx.font = '800 34px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = colorHex;
    ctx.fillText(direction === 'EAST' ? 'TRAVELLING WESTBOUND' : 'TRAVELLING EASTBOUND', w / 2, 630);

    ctx.font = '800 32px "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText('TWO LANES', w / 2, 695);

    // 5. Lane details
    ctx.font = '700 30px monospace';
    ctx.fillStyle = '#64748b';
    ctx.fillText('INCOMING TRAFFIC', w / 2, 880);
  }

  return canvas;
}

function buildRoadDirectionLabels(group) {
  const approaches = [
    {
      dir: 'NORTH',
      arrow: '↑',
      sub: 'INCOMING FROM NORTH • TRAVELLING SOUTHBOUND',
      color: '#38bdf8',
      x: -4.0,
      z: -18.5,
      w: 7.2,
      l: 4.4,
      isVertical: false,
      rotZ: 0
    },
    {
      dir: 'SOUTH',
      arrow: '↓',
      sub: 'INCOMING FROM SOUTH • TRAVELLING NORTHBOUND',
      color: '#10b981',
      x: 4.0,
      z: 18.5,
      w: 7.2,
      l: 4.4,
      isVertical: false,
      rotZ: 0
    },
    {
      dir: 'EAST',
      arrow: '→',
      sub: 'INCOMING FROM EAST • TRAVELLING WESTBOUND',
      color: '#f59e0b',
      x: 18.5,
      z: -4.0,
      w: 4.4,
      l: 7.2,
      isVertical: true,
      rotZ: 0
    },
    {
      dir: 'WEST',
      arrow: '←',
      sub: 'INCOMING FROM WEST • TRAVELLING EASTBOUND',
      color: '#a855f7',
      x: -18.5,
      z: 4.0,
      w: 4.4,
      l: 7.2,
      isVertical: true,
      rotZ: 0
    }
  ];

  approaches.forEach(cfg => {
    const canvas = createRoadLabelCanvas(cfg.dir, cfg.arrow, cfg.sub, cfg.color, cfg.isVertical);
    const texture = new THREE.CanvasTexture(canvas);
    if (renderer && renderer.capabilities) {
      texture.anisotropy = renderer.capabilities.getMaxAnisotropy() || 8;
    }
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    texture.generateMipmaps = true;

    const mat = new THREE.MeshStandardMaterial({
      map: texture,
      transparent: true,
      roughness: 0.3,
      metalness: 0.1,
      emissive: new THREE.Color(cfg.color),
      emissiveMap: texture,
      emissiveIntensity: 0.45,
      polygonOffset: true,
      polygonOffsetFactor: -3,
      polygonOffsetUnits: -6,
      depthWrite: false
    });

    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(cfg.w, cfg.l), mat);
    mesh.rotation.x = -Math.PI / 2;
    if (cfg.rotZ) mesh.rotation.z = cfg.rotZ;
    mesh.position.set(cfg.x, 0.038, cfg.z);
    mesh.name = `roadLabel_${cfg.dir.toLowerCase()}`;
    group.add(mesh);
  });

  // Roadside Approach Direction Signs (Distinctly readable from Street Level viewpoint)
  const totemConfigs = [
    { label: 'NORTH ↑', sub: 'Incoming from North, travelling southbound', color: '#38bdf8', x: -HALF_ROAD_3D - 0.9, z: -16.0, rotY: 0 },
    { label: 'SOUTH ↓', sub: 'Incoming from South, travelling northbound', color: '#10b981', x: HALF_ROAD_3D + 0.9, z: 16.0, rotY: Math.PI },
    { label: 'EAST →',  sub: 'Incoming from East, travelling westbound',  color: '#f59e0b', x: 16.0, z: -HALF_ROAD_3D - 0.9, rotY: Math.PI / 2 },
    { label: 'WEST ←',  sub: 'Incoming from West, travelling eastbound',  color: '#a855f7', x: -16.0, z: HALF_ROAD_3D + 0.9, rotY: -Math.PI / 2 }
  ];

  totemConfigs.forEach(t => {
    const postMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.4, metalness: 0.8 });
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 2.8, 12), postMat);
    post.position.set(t.x, 1.4, t.z);

    // Signboard
    const signCanvas = document.createElement('canvas');
    signCanvas.width = 512;
    signCanvas.height = 256;
    const sCtx = signCanvas.getContext('2d');
    sCtx.fillStyle = 'rgba(11, 15, 25, 0.95)';
    sCtx.fillRect(0, 0, 512, 256);
    sCtx.strokeStyle = t.color;
    sCtx.lineWidth = 12;
    sCtx.strokeRect(6, 6, 500, 244);

    sCtx.textAlign = 'center';
    sCtx.textBaseline = 'middle';
    sCtx.font = '900 80px "Inter", -apple-system, sans-serif';
    sCtx.fillStyle = '#ffffff';
    sCtx.fillText(t.label, 256, 95);

    sCtx.font = '700 24px "Inter", -apple-system, sans-serif';
    sCtx.fillStyle = t.color;
    sCtx.fillText(t.sub.toUpperCase(), 256, 185);

    const signTex = new THREE.CanvasTexture(signCanvas);
    const signMat = new THREE.MeshStandardMaterial({
      map: signTex,
      emissive: new THREE.Color(t.color),
      emissiveMap: signTex,
      emissiveIntensity: 0.5,
      roughness: 0.2
    });

    const signBoard = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.85, 0.08), signMat);
    signBoard.position.set(0, 0.9, 0);
    post.add(signBoard);
    post.rotation.y = t.rotY;

    group.add(post);
  });
}

/**
 * Build 3D Cantilever Traffic Signal Poles with Exact World Orientation.
 * CRITICAL RULE:
 * - North-facing signals face SOUTH toward oncoming Southbound drivers looking South (+Z).
 * - South-facing signals face NORTH toward oncoming Northbound drivers looking North (-Z).
 * - East-facing signals face WEST toward oncoming Westbound drivers looking West (-X).
 * - West-facing signals face EAST toward oncoming Eastbound drivers looking East (+X).
 * Signal heads are FIXED in world space and NEVER rotate with camera movements!
 */
function buildTrafficSignalPoles(group) {
  signalLenses3D = {
    north: {},
    south: {},
    east: {},
    west: {}
  };
  window.signalLenses3D = signalLenses3D;

  const poleMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8, roughness: 0.3 });
  const housingMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.5 });
  const visorMat = new THREE.MeshStandardMaterial({ color: 0x090d16, roughness: 0.6 });

  // Configuration for each approach:
  // - poleX, poleZ: Corner pole location on sidewalk curb near the stop line
  // - armVector: Direction the cantilever arm reaches across the incoming lane
  // - headOffset: Local position of the signal head along the arm
  // - headRotationY: Exact world angle around Y so lenses face directly into oncoming drivers' eyes
  const signalConfigs = [
    {
      approach: 'north',
      poleX: -HALF_ROAD_3D - 1.4, // Northwest corner (X = -9.4, Z = -12.0)
      poleZ: -STOP_LINE_DIST_3D,
      armRotZ: Math.PI / 2,
      armRotY: 0,                // Arm reaches along +X over southbound lanes
      headX: 5.4,                // Centered over incoming southbound lane (X = -4.0)
      headY: 6.8,
      headZ: 0,
      headRotationY: Math.PI,    // Lenses face NORTH (-Z) toward incoming Southbound drivers!
      pedBoxRotY: 0              // Pedestrian indicator faces across the street
    },
    {
      approach: 'south',
      poleX: HALF_ROAD_3D + 1.4,  // Southeast corner (X = +9.4, Z = +12.0)
      poleZ: STOP_LINE_DIST_3D,
      armRotZ: Math.PI / 2,
      armRotY: Math.PI,          // Arm reaches along -X over northbound lanes
      headX: -5.4,               // Centered over incoming northbound lane (X = +4.0)
      headY: 6.8,
      headZ: 0,
      headRotationY: 0,          // Lenses face SOUTH (+Z) toward incoming Northbound drivers!
      pedBoxRotY: Math.PI
    },
    {
      approach: 'east',
      poleX: STOP_LINE_DIST_3D,   // Northeast corner (X = +12.0, Z = -9.4)
      poleZ: -HALF_ROAD_3D - 1.4,
      armRotZ: Math.PI / 2,
      armRotY: Math.PI / 2,      // Arm reaches along +Z over westbound lanes
      headX: 0,
      headY: 6.8,
      headZ: 5.4,                // Centered over incoming westbound lane (Z = -4.0)
      headRotationY: Math.PI / 2,// Lenses face EAST (+X) toward incoming Westbound drivers!
      pedBoxRotY: Math.PI / 2
    },
    {
      approach: 'west',
      poleX: -STOP_LINE_DIST_3D,  // Southwest corner (X = -12.0, Z = +9.4)
      poleZ: HALF_ROAD_3D + 1.4,
      armRotZ: Math.PI / 2,
      armRotY: -Math.PI / 2,     // Arm reaches along -Z over eastbound lanes
      headX: 0,
      headY: 6.8,
      headZ: -5.4,               // Centered over incoming eastbound lane (Z = +4.0)
      headRotationY: -Math.PI / 2,// Lenses face WEST (-X) toward incoming Eastbound drivers!
      pedBoxRotY: -Math.PI / 2
    }
  ];

  signalConfigs.forEach(cfg => {
    const poleGroup = new THREE.Group();
    poleGroup.position.set(cfg.poleX, 0, cfg.poleZ);

    // 1. Vertical Mast
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.24, 7.5, 12), poleMat);
    mast.position.y = 3.75;
    mast.castShadow = true;
    poleGroup.add(mast);

    // 2. Cantilever Horizontal Arm reaching over incoming lanes
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 6.0, 12), poleMat);
    arm.rotation.z = cfg.armRotZ;
    arm.rotation.y = cfg.armRotY;
    arm.position.set(
      cfg.armRotY === 0 ? 3.0 : (cfg.armRotY === Math.PI ? -3.0 : 0),
      7.0,
      cfg.armRotY === Math.PI / 2 ? 3.0 : (cfg.armRotY === -Math.PI / 2 ? -3.0 : 0)
    );
    poleGroup.add(arm);

    // 3. 3-Aspect Signal Head (Fixed in World Space)
    const headGroup = new THREE.Group();
    headGroup.position.set(cfg.headX, cfg.headY, cfg.headZ);
    headGroup.rotation.y = cfg.headRotationY;

    // Housing Box
    const box = new THREE.Mesh(new THREE.BoxGeometry(0.85, 2.4, 0.5), housingMat);
    box.castShadow = true;
    headGroup.add(box);

    // 3 Aspect Lenses: Red, Yellow, Green
    const redMat = new THREE.MeshStandardMaterial({
      color: 0xef4444,
      emissive: 0xef4444,
      emissiveIntensity: 0.05,
      roughness: 0.25
    });
    const yellowMat = new THREE.MeshStandardMaterial({
      color: 0xf59e0b,
      emissive: 0xf59e0b,
      emissiveIntensity: 0.05,
      roughness: 0.25
    });
    const greenMat = new THREE.MeshStandardMaterial({
      color: 0x10b981,
      emissive: 0x10b981,
      emissiveIntensity: 0.05,
      roughness: 0.25
    });

    const lensGeo = new THREE.SphereGeometry(0.25, 16, 12);

    // Red lens (top)
    const redLens = new THREE.Mesh(lensGeo, redMat);
    redLens.position.set(0, 0.72, 0.24);
    headGroup.add(redLens);

    // Yellow lens (middle)
    const yellowLens = new THREE.Mesh(lensGeo, yellowMat);
    yellowLens.position.set(0, 0, 0.24);
    headGroup.add(yellowLens);

    // Green lens (bottom)
    const greenLens = new THREE.Mesh(lensGeo, greenMat);
    greenLens.position.set(0, -0.72, 0.24);
    headGroup.add(greenLens);

    // Realistic Lens Visor Hoods
    const addVisor = (vy) => {
      const visor = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.28, 12, 1, true, 0, Math.PI), visorMat);
      visor.rotation.x = Math.PI / 2;
      visor.position.set(0, vy + 0.1, 0.28);
      headGroup.add(visor);
    };
    addVisor(0.72);
    addVisor(0);
    addVisor(-0.72);

    poleGroup.add(headGroup);

    // 4. Pedestrian Signal Box at eye level (Mounted on pole, height 2.3m)
    const pedBoxGroup = new THREE.Group();
    pedBoxGroup.position.set(0, 2.3, 0);
    pedBoxGroup.rotation.y = cfg.pedBoxRotY;

    const pedBox = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.9, 0.38), housingMat);
    pedBox.position.z = 0.24;
    pedBoxGroup.add(pedBox);

    const pedWalkMat = new THREE.MeshStandardMaterial({
      color: 0x10b981,
      emissive: 0x10b981,
      emissiveIntensity: 0.05
    });
    const pedStopMat = new THREE.MeshStandardMaterial({
      color: 0xef4444,
      emissive: 0xef4444,
      emissiveIntensity: 1.8
    });

    const pedStopLens = new THREE.Mesh(new THREE.PlaneGeometry(0.26, 0.26), pedStopMat);
    pedStopLens.position.set(0, 0.22, 0.44);
    pedBoxGroup.add(pedStopLens);

    const pedWalkLens = new THREE.Mesh(new THREE.PlaneGeometry(0.26, 0.26), pedWalkMat);
    pedWalkLens.position.set(0, -0.22, 0.44);
    pedBoxGroup.add(pedWalkLens);

    poleGroup.add(pedBoxGroup);
    group.add(poleGroup);

    signalLenses3D[cfg.approach] = {
      red: redMat,
      yellow: yellowMat,
      green: greenMat,
      pedStop: pedStopMat,
      pedWalk: pedWalkMat
    };
  });
}

function buildStreetlights(group) {
  const poleMat = new THREE.MeshStandardMaterial({ color: 0x64748b, metalness: 0.8 });
  const lampMat = new THREE.MeshStandardMaterial({
    color: 0xe0f2fe,
    emissive: 0x38bdf8,
    emissiveIntensity: 1.2
  });

  const positions = [
    { x: -HALF_ROAD_3D - 1.5, z: -25 },
    { x: -HALF_ROAD_3D - 1.5, z: 25 },
    { x: HALF_ROAD_3D + 1.5, z: -25 },
    { x: HALF_ROAD_3D + 1.5, z: 25 },
    { x: -25, z: -HALF_ROAD_3D - 1.5 },
    { x: 25, z: -HALF_ROAD_3D - 1.5 },
    { x: -25, z: HALF_ROAD_3D + 1.5 },
    { x: 25, z: HALF_ROAD_3D + 1.5 }
  ];

  positions.forEach(pos => {
    const sl = new THREE.Group();
    sl.position.set(pos.x, 0, pos.z);

    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 8, 8), poleMat);
    pole.position.y = 4;
    pole.castShadow = true;
    sl.add(pole);

    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.1, 2.0, 8), poleMat);
    arm.rotation.z = Math.PI / 4;
    arm.position.set(pos.x > 0 ? -0.7 : 0.7, 7.8, 0);
    sl.add(arm);

    const lamp = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.15, 0.8), lampMat);
    lamp.position.set(pos.x > 0 ? -1.3 : 1.3, 8.2, 0);
    sl.add(lamp);

    group.add(sl);
  });
}

// Composition & Skyline (Guarantees zero road obstruction from camera angle!)
function buildCityBuildingsAndPlaza(group) {
  const buildingColors = [0x1e293b, 0x334155, 0x1e3a5f, 0x27272a, 0x1e293b];

  // 1. BACKGROUND BUILDINGS (Placed in -X, -Z and far edges to form a scenic skyline that NEVER blocks roads)
  const bldgConfigs = [
    // Top-Left quadrant (-X, -Z): Tallest skyline backdrop
    { x: -28, z: -28, w: 16, h: 26, d: 16 },
    { x: -44, z: -28, w: 14, h: 20, d: 14 },
    { x: -28, z: -44, w: 14, h: 32, d: 14 },
    // Top-Right quadrant (+X, -Z): Set back behind East road
    { x: 30, z: -30, w: 16, h: 22, d: 16 },
    { x: 44, z: -30, w: 14, h: 18, d: 14 },
    { x: 30, z: -44, w: 14, h: 24, d: 14 },
    // Bottom-Left quadrant (-X, +Z): Set back behind West road
    { x: -30, z: 30, w: 16, h: 16, d: 16 },
    { x: -44, z: 30, w: 14, h: 22, d: 14 },
    { x: -30, z: 44, w: 14, h: 18, d: 14 }
  ];

  bldgConfigs.forEach((cfg, idx) => {
    const col = buildingColors[idx % buildingColors.length];
    const bldgMat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.8, metalness: 0.1 });
    const bldg = new THREE.Mesh(new THREE.BoxGeometry(cfg.w, cfg.h, cfg.d), bldgMat);
    bldg.position.set(cfg.x, cfg.h / 2, cfg.z);
    bldg.castShadow = true;
    bldg.receiveShadow = true;

    // Rooftop utility box & antenna
    const roofBox = new THREE.Mesh(
      new THREE.BoxGeometry(cfg.w * 0.4, 2.5, cfg.d * 0.4),
      new THREE.MeshStandardMaterial({ color: 0x475569 })
    );
    roofBox.position.set(cfg.x, cfg.h + 1.25, cfg.z);
    group.add(roofBox);

    group.add(bldg);
  });

  // 2. FOREGROUND QUADRANT (+X, +Z): OPEN CIVIC PLAZA & METRO PARK
  // (Prevents any building from blocking the camera's view of South & East roads!)
  const plazaMat = new THREE.MeshStandardMaterial({ color: 0x3b4252, roughness: 0.7 });
  const plazaFloor = new THREE.Mesh(new THREE.BoxGeometry(32, 0.05, 32), plazaMat);
  plazaFloor.position.set(28, 0.3, 28);
  plazaFloor.receiveShadow = true;
  group.add(plazaFloor);

  // Decorative Central Water Fountain / Monument (Low height: 1.2 units)
  const fountainRing = new THREE.Mesh(
    new THREE.CylinderGeometry(4.5, 4.5, 0.7, 24),
    new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.4 })
  );
  fountainRing.position.set(28, 0.65, 28);
  fountainRing.castShadow = true;
  group.add(fountainRing);

  const waterPool = new THREE.Mesh(
    new THREE.CylinderGeometry(4.1, 4.1, 0.6, 24),
    new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.1, metalness: 0.8 })
  );
  waterPool.position.set(28, 0.8, 28);
  group.add(waterPool);

  // Low stone park benches
  const benchMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8 });
  const b1 = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.4, 0.8), benchMat);
  b1.position.set(28, 0.5, 21);
  const b2 = b1.clone();
  b2.position.set(28, 0.5, 35);
  const b3 = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.4, 3.0), benchMat);
  b3.position.set(21, 0.5, 28);
  const b4 = b3.clone();
  b4.position.set(35, 0.5, 28);
  group.add(b1, b2, b3, b4);
}

function buildSidewalkTrees(group) {
  const trunkMat = new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.9 });
  const leavesMat1 = new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.6, flatShading: true });
  const leavesMat2 = new THREE.MeshStandardMaterial({ color: 0x16a34a, roughness: 0.6, flatShading: true });

  const treeCoords = [
    { x: -HALF_ROAD_3D - 3.5, z: -16 },
    { x: -HALF_ROAD_3D - 3.5, z: -36 },
    { x: HALF_ROAD_3D + 3.5, z: -16 },
    { x: HALF_ROAD_3D + 3.5, z: -36 },
    { x: -HALF_ROAD_3D - 3.5, z: 16 },
    { x: -HALF_ROAD_3D - 3.5, z: 36 },
    { x: -16, z: -HALF_ROAD_3D - 3.5 },
    { x: -36, z: -HALF_ROAD_3D - 3.5 },
    { x: 16, z: -HALF_ROAD_3D - 3.5 },
    { x: 36, z: -HALF_ROAD_3D - 3.5 },
    { x: -16, z: HALF_ROAD_3D + 3.5 },
    { x: -36, z: HALF_ROAD_3D + 3.5 },
    // Low ornamental trees in the plaza
    { x: 18, z: 18 },
    { x: 38, z: 18 },
    { x: 18, z: 38 }
  ];

  treeCoords.forEach((coord, i) => {
    const tree = new THREE.Group();
    tree.position.set(coord.x, 0.28, coord.z);

    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.24, 2.4, 8), trunkMat);
    trunk.position.y = 1.2;
    trunk.castShadow = true;
    tree.add(trunk);

    const foliage = new THREE.Mesh(
      new THREE.DodecahedronGeometry(1.6, 1),
      i % 2 === 0 ? leavesMat1 : leavesMat2
    );
    foliage.position.y = 3.1;
    foliage.castShadow = true;
    tree.add(foliage);

    group.add(tree);
  });
}

// ============================================================================
// 8. 3D VEHICLE MESH FACTORIES & KINEMATICS
// ============================================================================

// ============================================================================
// 8. 3D VEHICLE MESH FACTORIES & KINEMATICS
// ============================================================================

const VEHICLE_SHARED_MATS = {
  wheel: new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.90 }),
  rim: new THREE.MeshStandardMaterial({ color: 0xd4d4d8, metalness: 0.85, roughness: 0.22 }),
  window: new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.10, metalness: 0.90, transparent: true, opacity: 0.85 }),
  headlight: new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 1.8 }),
  taillight: new THREE.MeshStandardMaterial({ color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 1.0 }),
  turn: new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0xf59e0b, emissiveIntensity: 0.0 }),
  bumper: new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.75 }),
  chrome: new THREE.MeshStandardMaterial({ color: 0xf1f5f9, metalness: 0.92, roughness: 0.12 }),
  mirror: new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.45 }),
  plateWhite: new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.60 }),
  plateYellow: new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.60 }),
  grilleDark: new THREE.MeshStandardMaterial({ color: 0x09090b, roughness: 0.85, metalness: 0.20 }),
  skidPlate: new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.35, metalness: 0.60 }),
  taxiYellow: new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.30, metalness: 0.15 }),
  taxiSign: new THREE.MeshStandardMaterial({ color: 0xfffbeb, emissive: 0xfacc15, emissiveIntensity: 1.6 }),
  truckContainer: new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.65, metalness: 0.25 }),
  busBlue: new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.32, metalness: 0.15 }),
  whiteRoof: new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.35 }),
  ambRedStripe: new THREE.MeshStandardMaterial({ color: 0xef4444, roughness: 0.30 }),
  ambBlueStar: new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.30 })
};

function makeLicensePlate(w = 0.52, h = 0.14, isYellow = false) {
  const g = new THREE.Group();
  const frame = new THREE.Mesh(new THREE.BoxGeometry(w + 0.04, h + 0.04, 0.02), VEHICLE_SHARED_MATS.bumper);
  const face = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.03), isYellow ? VEHICLE_SHARED_MATS.plateYellow : VEHICLE_SHARED_MATS.plateWhite);
  g.add(frame, face);
  return g;
}

function makeVehicleWheel(wx, wy, wz, r = 0.38, width = 0.26, isFront = false) {
  // 1. Steering Pivot: placed at wheel mount position (wx, wy, wz)
  const steerPivot = new THREE.Group();
  steerPivot.position.set(wx, wy, wz);
  steerPivot.userData.isFront = isFront;

  // 2. Roll Group: child of steerPivot, centered at [0, 0, 0]
  // Rotates around local X-axis for forward/backward wheel rolling
  const rollGroup = new THREE.Group();
  steerPivot.add(rollGroup);

  // 3. Tire: Outer rubber cylinder
  const tireGeom = new THREE.CylinderGeometry(r, r, width, 18);
  tireGeom.rotateZ(Math.PI / 2); // Aligns axle along local X
  const tire = new THREE.Mesh(tireGeom, VEHICLE_SHARED_MATS.wheel);
  tire.castShadow = true;
  rollGroup.add(tire);

  // 4. Rim: Metallic silver cylinder slightly inset
  const rimRadius = r * 0.62;
  const rimWidth = width + 0.015;
  const rimGeom = new THREE.CylinderGeometry(rimRadius, rimRadius, rimWidth, 14);
  rimGeom.rotateZ(Math.PI / 2);
  const rim = new THREE.Mesh(rimGeom, VEHICLE_SHARED_MATS.rim);
  rollGroup.add(rim);

  // 5. Spokes / Hubcap Details: Silver cross spokes make rotation visibly dynamic from any angle
  const spokeGeom = new THREE.BoxGeometry(rimWidth + 0.012, rimRadius * 1.82, rimRadius * 0.22);
  const spoke1 = new THREE.Mesh(spokeGeom, VEHICLE_SHARED_MATS.chrome);
  rollGroup.add(spoke1);

  const spoke2 = new THREE.Mesh(spokeGeom, VEHICLE_SHARED_MATS.chrome);
  spoke2.rotation.x = Math.PI / 2;
  rollGroup.add(spoke2);

  // Center axle hubcap / nut
  const hubGeom = new THREE.CylinderGeometry(r * 0.24, r * 0.24, rimWidth + 0.024, 10);
  hubGeom.rotateZ(Math.PI / 2);
  const hub = new THREE.Mesh(hubGeom, VEHICLE_SHARED_MATS.bumper);
  rollGroup.add(hub);

  return { steerPivot, rollGroup, radius: r, isFront };
}

function createCar3DMesh(type, colorHex) {
  const root = new THREE.Group();
  const bodyPaintMat = new THREE.MeshStandardMaterial({
    color: colorHex,
    roughness: 0.32,
    metalness: 0.30
  });

  let length = 4.65;
  let width = 1.95;
  let height = 1.40;
  let wheelRadius = 0.38;
  let wheels = [];

  const turnMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0xf59e0b, emissiveIntensity: 0.0 });
  const taillightMat = new THREE.MeshStandardMaterial({ color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 0.8 });

  if (type === 'hatchback' || type === 'compact') {
    // 1. Compact Sporty Hatchback
    length = 3.90;
    width = 1.90;
    height = 1.45;
    wheelRadius = 0.36;

    // Sculpted lower chassis
    const chassis = new THREE.Mesh(new THREE.BoxGeometry(width, 0.46, length), bodyPaintMat);
    chassis.position.y = 0.44;
    chassis.castShadow = true;
    root.add(chassis);

    // Front & rear sporty bumpers
    const fBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.22, 0.18), VEHICLE_SHARED_MATS.bumper);
    fBump.position.set(0, 0.33, length / 2 + 0.08);
    const rBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.22, 0.18), VEHICLE_SHARED_MATS.bumper);
    rBump.position.set(0, 0.33, -length / 2 - 0.08);
    root.add(fBump, rBump);

    // Front honeycomb grille
    const grille = new THREE.Mesh(new THREE.BoxGeometry(width * 0.45, 0.16, 0.06), VEHICLE_SHARED_MATS.grilleDark);
    grille.position.set(0, 0.44, length / 2 + 0.02);
    root.add(grille);

    // Aerodynamic greenhouse (windshield + side windows + rear tailgate hatch)
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(width - 0.16, 0.54, length * 0.60), VEHICLE_SHARED_MATS.window);
    cabin.position.set(0, 0.92, -0.15);
    cabin.castShadow = true;
    root.add(cabin);

    const roof = new THREE.Mesh(new THREE.BoxGeometry(width - 0.20, 0.06, length * 0.50), bodyPaintMat);
    roof.position.set(0, 1.21, -0.15);
    root.add(roof);

    // Sporty rear roof spoiler wing
    const spoiler = new THREE.Mesh(new THREE.BoxGeometry(width - 0.22, 0.05, 0.26), VEHICLE_SHARED_MATS.bumper);
    spoiler.position.set(0, 1.25, -length * 0.40);
    root.add(spoiler);

    // Dual side mirrors
    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.10, 0.18), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.08, 0.85, 0.35);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.08;
    root.add(m1, m2);

    // Headlights (clear bright lenses)
    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.16, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(width * 0.35, 0.46, length / 2 + 0.02);
    const h2 = h1.clone();
    h2.position.x = -width * 0.35;
    root.add(h1, h2);

    // Taillights
    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.18, 0.08), taillightMat);
    t1.position.set(width * 0.35, 0.54, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -width * 0.35;
    root.add(t1, t2);

    // Turn indicators
    const turn1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.08), turnMat);
    turn1.position.set(width / 2 + 0.02, 0.44, length / 2 - 0.20);
    const turn2 = turn1.clone();
    turn2.position.x = -width / 2 - 0.02;
    root.add(turn1, turn2);

    // License plates
    const fPlate = makeLicensePlate(0.48, 0.12, false);
    fPlate.position.set(0, 0.30, length / 2 + 0.18);
    const rPlate = makeLicensePlate(0.48, 0.12, true);
    rPlate.position.set(0, 0.30, -length / 2 - 0.18);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    // 4 Wheels (2 front steering, 2 rear)
    wheels = [
      makeVehicleWheel(width / 2 + 0.02, wheelRadius, 1.20, wheelRadius, 0.24, true),
      makeVehicleWheel(-width / 2 - 0.02, wheelRadius, 1.20, wheelRadius, 0.24, true),
      makeVehicleWheel(width / 2 + 0.02, wheelRadius, -1.20, wheelRadius, 0.24, false),
      makeVehicleWheel(-width / 2 - 0.02, wheelRadius, -1.20, wheelRadius, 0.24, false)
    ];

  } else if (type === 'suv') {
    // 2. Muscular High-Riding SUV / Crossover
    length = 4.90;
    width = 2.12;
    height = 1.78;
    wheelRadius = 0.44;

    // High chassis with protective dark rocker cladding
    const chassis = new THREE.Mesh(new THREE.BoxGeometry(width, 0.62, length), bodyPaintMat);
    chassis.position.y = 0.60;
    chassis.castShadow = true;
    root.add(chassis);

    const cladding = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.24, length + 0.04), VEHICLE_SHARED_MATS.bumper);
    cladding.position.y = 0.38;
    root.add(cladding);

    // Front silver skid plate & heavy rear bumper
    const skid = new THREE.Mesh(new THREE.BoxGeometry(width * 0.65, 0.20, 0.16), VEHICLE_SHARED_MATS.skidPlate);
    skid.position.set(0, 0.40, length / 2 + 0.08);
    const rBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.06, 0.26, 0.20), VEHICLE_SHARED_MATS.bumper);
    rBump.position.set(0, 0.42, -length / 2 - 0.08);
    root.add(skid, rBump);

    // Front chrome horizontal grille
    const grille = new THREE.Mesh(new THREE.BoxGeometry(width * 0.50, 0.24, 0.06), VEHICLE_SHARED_MATS.chrome);
    grille.position.set(0, 0.66, length / 2 + 0.02);
    root.add(grille);

    // Tall greenhouse cabin
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(width - 0.20, 0.66, length * 0.64), VEHICLE_SHARED_MATS.window);
    cabin.position.set(0, 1.22, -0.18);
    cabin.castShadow = true;
    root.add(cabin);

    const roof = new THREE.Mesh(new THREE.BoxGeometry(width - 0.24, 0.08, length * 0.56), bodyPaintMat);
    roof.position.set(0, 1.58, -0.18);
    root.add(roof);

    // Dual silver roof rails
    const rail1 = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, length * 0.50), VEHICLE_SHARED_MATS.chrome);
    rail1.position.set(0.74, 1.64, -0.18);
    const rail2 = rail1.clone();
    rail2.position.x = -0.74;
    root.add(rail1, rail2);

    // Mirrors, lights
    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.14, 0.20), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.10, 1.15, 0.45);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.10;
    root.add(m1, m2);

    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.20, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(width * 0.35, 0.66, length / 2 + 0.02);
    const h2 = h1.clone();
    h2.position.x = -width * 0.35;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.22, 0.08), taillightMat);
    t1.position.set(width * 0.35, 0.72, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -width * 0.35;
    root.add(t1, t2);

    const turn1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.08), turnMat);
    turn1.position.set(width / 2 + 0.02, 0.58, length / 2 - 0.30);
    const turn2 = turn1.clone();
    turn2.position.x = -width / 2 - 0.02;
    root.add(turn1, turn2);

    // License plates
    const fPlate = makeLicensePlate(0.50, 0.14, false);
    fPlate.position.set(0, 0.32, length / 2 + 0.18);
    const rPlate = makeLicensePlate(0.50, 0.14, true);
    rPlate.position.set(0, 0.38, -length / 2 - 0.18);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    // 4 Rugged Wheels (2 front steering, 2 rear)
    wheels = [
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, 1.48, wheelRadius, 0.30, true),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, 1.48, wheelRadius, 0.30, true),
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, -1.48, wheelRadius, 0.30, false),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, -1.48, wheelRadius, 0.30, false)
    ];

  } else if (type === 'taxi') {
    // 3. City Yellow Taxi Cab
    length = 4.65;
    width = 1.95;
    height = 1.50;
    wheelRadius = 0.38;

    const chassis = new THREE.Mesh(new THREE.BoxGeometry(width, 0.48, length), VEHICLE_SHARED_MATS.taxiYellow);
    chassis.position.y = 0.46;
    chassis.castShadow = true;
    root.add(chassis);

    // Chrome front grille & bumpers
    const grille = new THREE.Mesh(new THREE.BoxGeometry(width * 0.45, 0.22, 0.06), VEHICLE_SHARED_MATS.chrome);
    grille.position.set(0, 0.46, length / 2 + 0.02);
    const fBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.20, 0.18), VEHICLE_SHARED_MATS.bumper);
    fBump.position.set(0, 0.34, length / 2 + 0.08);
    const rBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.20, 0.18), VEHICLE_SHARED_MATS.bumper);
    rBump.position.set(0, 0.34, -length / 2 - 0.08);
    root.add(grille, fBump, rBump);

    // Checkerboard accent stripe along sides
    const stripe1 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, length * 0.65), VEHICLE_SHARED_MATS.bumper);
    stripe1.position.set(width / 2 + 0.01, 0.60, -0.12);
    const stripe2 = stripe1.clone();
    stripe2.position.x = -width / 2 - 0.01;
    root.add(stripe1, stripe2);

    // 3-box cabin
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(width - 0.18, 0.52, length * 0.52), VEHICLE_SHARED_MATS.window);
    cabin.position.set(0, 0.94, -0.12);
    cabin.castShadow = true;
    root.add(cabin);

    const roof = new THREE.Mesh(new THREE.BoxGeometry(width - 0.22, 0.06, length * 0.42), VEHICLE_SHARED_MATS.taxiYellow);
    roof.position.set(0, 1.22, -0.12);
    root.add(roof);

    // Rooftop TAXI Sign
    const signBase = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.08, 0.26), VEHICLE_SHARED_MATS.bumper);
    signBase.position.set(0, 1.26, -0.12);
    const taxiSign = new THREE.Mesh(new THREE.BoxGeometry(0.60, 0.20, 0.20), VEHICLE_SHARED_MATS.taxiSign);
    taxiSign.position.set(0, 1.38, -0.12);
    root.add(signBase, taxiSign);

    // Mirrors, lights
    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.10, 0.18), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.08, 0.85, 0.45);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.08;
    root.add(m1, m2);

    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.18, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(width * 0.35, 0.46, length / 2 + 0.02);
    const h2 = h1.clone();
    h2.position.x = -width * 0.35;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.18, 0.08), taillightMat);
    t1.position.set(width * 0.35, 0.50, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -width * 0.35;
    root.add(t1, t2);

    const turn1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.08), turnMat);
    turn1.position.set(width / 2 + 0.02, 0.44, length / 2 - 0.25);
    const turn2 = turn1.clone();
    turn2.position.x = -width / 2 - 0.02;
    root.add(turn1, turn2);

    // License plates
    const fPlate = makeLicensePlate(0.50, 0.14, false);
    fPlate.position.set(0, 0.28, length / 2 + 0.18);
    const rPlate = makeLicensePlate(0.50, 0.14, true);
    rPlate.position.set(0, 0.28, -length / 2 - 0.18);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    wheels = [
      makeVehicleWheel(width / 2 + 0.02, wheelRadius, 1.38, wheelRadius, 0.26, true),
      makeVehicleWheel(-width / 2 - 0.02, wheelRadius, 1.38, wheelRadius, 0.26, true),
      makeVehicleWheel(width / 2 + 0.02, wheelRadius, -1.38, wheelRadius, 0.26, false),
      makeVehicleWheel(-width / 2 - 0.02, wheelRadius, -1.38, wheelRadius, 0.26, false)
    ];

  } else if (type === 'van') {
    // 4. Commercial Delivery Van
    length = 5.50;
    width = 2.15;
    height = 2.40;
    wheelRadius = 0.42;

    const base = new THREE.Mesh(new THREE.BoxGeometry(width, 0.55, length), bodyPaintMat);
    base.position.y = 0.55;
    base.castShadow = true;
    root.add(base);

    // Cab with windshield
    const cab = new THREE.Mesh(new THREE.BoxGeometry(width - 0.15, 0.75, 1.60), VEHICLE_SHARED_MATS.window);
    cab.position.set(0, 1.15, length / 2 - 1.0);
    cab.castShadow = true;
    root.add(cab);

    // Tall rear cargo compartment
    const cargo = new THREE.Mesh(new THREE.BoxGeometry(width, 1.45, length - 1.40), bodyPaintMat);
    cargo.position.set(0, 1.52, -0.65);
    cargo.castShadow = true;
    root.add(cargo);

    // Rear cargo door seams / handle
    const seam = new THREE.Mesh(new THREE.BoxGeometry(0.04, 1.30, 0.04), VEHICLE_SHARED_MATS.bumper);
    seam.position.set(0, 1.52, -length / 2 - 0.02);
    root.add(seam);

    // High-mount rear brake bar
    const hiBrake = new THREE.Mesh(new THREE.BoxGeometry(0.50, 0.08, 0.04), taillightMat);
    hiBrake.position.set(0, 2.22, -length / 2 - 0.02);
    root.add(hiBrake);

    // Mirrors, lights
    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.18, 0.20), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.08, 1.15, 1.80);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.08;
    root.add(m1, m2);

    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.20, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(width * 0.35, 0.65, length / 2 + 0.02);
    const h2 = h1.clone();
    h2.position.x = -width * 0.35;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.50, 0.08), taillightMat);
    t1.position.set(width * 0.38, 1.20, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -width * 0.38;
    root.add(t1, t2);

    // License plates
    const fPlate = makeLicensePlate(0.52, 0.14, false);
    fPlate.position.set(0, 0.35, length / 2 + 0.04);
    const rPlate = makeLicensePlate(0.52, 0.14, true);
    rPlate.position.set(0, 0.35, -length / 2 - 0.04);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    wheels = [
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, 1.60, wheelRadius, 0.28, true),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, 1.60, wheelRadius, 0.28, true),
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, -1.60, wheelRadius, 0.28, false),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, -1.60, wheelRadius, 0.28, false)
    ];

  } else if (type === 'truck') {
    // 5. Heavy-Duty Long Cargo Truck (Tractor + Container)
    length = 10.20;
    width = 2.55;
    height = 3.45;
    wheelRadius = 0.48;

    // Heavy cab
    const cab = new THREE.Mesh(new THREE.BoxGeometry(width - 0.06, 1.85, 2.50), bodyPaintMat);
    cab.position.set(0, 1.55, length / 2 - 1.35);
    cab.castShadow = true;
    root.add(cab);

    // Cab windshield & glass
    const cabGlass = new THREE.Mesh(new THREE.BoxGeometry(width - 0.18, 0.72, 1.30), VEHICLE_SHARED_MATS.window);
    cabGlass.position.set(0, 1.85, length / 2 - 0.90);
    root.add(cabGlass);

    // Aerodynamic roof wind deflector (cab fairing)
    const fairing = new THREE.Mesh(new THREE.BoxGeometry(width - 0.20, 0.55, 1.40), bodyPaintMat);
    fairing.position.set(0, 2.72, length / 2 - 1.40);
    root.add(fairing);

    // Chrome heavy bumper
    const fBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.06, 0.35, 0.30), VEHICLE_SHARED_MATS.chrome);
    fBump.position.set(0, 0.48, length / 2 + 0.05);
    root.add(fBump);

    // Chrome vertical exhaust stack
    const exhaust = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 2.20, 8), VEHICLE_SHARED_MATS.chrome);
    exhaust.position.set(width / 2 + 0.05, 2.20, length / 2 - 2.50);
    root.add(exhaust);

    // Shipping cargo box container
    const container = new THREE.Mesh(new THREE.BoxGeometry(width, 2.20, 6.90), VEHICLE_SHARED_MATS.truckContainer);
    container.position.set(0, 1.95, -1.35);
    container.castShadow = true;
    root.add(container);

    // Side fuel tanks (cylinders)
    const tank1 = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 1.80, 12), VEHICLE_SHARED_MATS.chrome);
    tank1.rotation.x = Math.PI / 2;
    tank1.position.set(width / 2 - 0.10, 0.65, 0.80);
    const tank2 = tank1.clone();
    tank2.position.x = -width / 2 + 0.10;
    root.add(tank1, tank2);

    // Heavy side mirrors
    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.35, 0.15), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.10, 1.85, length / 2 - 1.20);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.10;
    root.add(m1, m2);

    // Lights
    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.24, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(width * 0.36, 0.55, length / 2 + 0.16);
    const h2 = h1.clone();
    h2.position.x = -width * 0.36;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.24, 0.08), taillightMat);
    t1.position.set(width * 0.36, 0.55, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -width * 0.36;
    root.add(t1, t2);

    // License plates
    const fPlate = makeLicensePlate(0.55, 0.15, false);
    fPlate.position.set(0, 0.40, length / 2 + 0.22);
    const rPlate = makeLicensePlate(0.55, 0.15, true);
    rPlate.position.set(0, 0.45, -length / 2 - 0.04);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    // 6 heavy wheels (2 front steer + 4 rear tandem duals)
    wheels = [
      makeVehicleWheel(width / 2 + 0.04, wheelRadius, 3.85, wheelRadius, 0.32, true),
      makeVehicleWheel(-width / 2 - 0.04, wheelRadius, 3.85, wheelRadius, 0.32, true),
      makeVehicleWheel(width / 2 + 0.04, wheelRadius, -2.80, wheelRadius, 0.32, false),
      makeVehicleWheel(-width / 2 - 0.04, wheelRadius, -2.80, wheelRadius, 0.32, false),
      makeVehicleWheel(width / 2 + 0.04, wheelRadius, -4.05, wheelRadius, 0.32, false),
      makeVehicleWheel(-width / 2 - 0.04, wheelRadius, -4.05, wheelRadius, 0.32, false)
    ];

  } else if (type === 'bus') {
    // 6. City Transit Coach Bus
    length = 10.60;
    width = 2.55;
    height = 3.10;
    wheelRadius = 0.48;

    // Two-tone transit livery: deep blue lower, white roof
    const lowerBody = new THREE.Mesh(new THREE.BoxGeometry(width, 1.10, length), VEHICLE_SHARED_MATS.busBlue);
    lowerBody.position.y = 0.90;
    lowerBody.castShadow = true;
    root.add(lowerBody);

    // Continuous tinted window band
    const windowBand = new THREE.Mesh(new THREE.BoxGeometry(width + 0.05, 0.90, length - 0.80), VEHICLE_SHARED_MATS.window);
    windowBand.position.y = 1.85;
    root.add(windowBand);

    const roof = new THREE.Mesh(new THREE.BoxGeometry(width - 0.04, 0.22, length - 0.20), VEHICLE_SHARED_MATS.whiteRoof);
    roof.position.y = 2.40;
    root.add(roof);

    // Front illuminated LED destination marquee ("METRO 42 RAPID")
    const destSign = new THREE.Mesh(
      new THREE.BoxGeometry(1.80, 0.35, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, emissive: 0xfacc15, emissiveIntensity: 1.4 })
    );
    destSign.position.set(0, 2.25, length / 2 + 0.03);
    root.add(destSign);

    // Rooftop AC units
    const ac1 = new THREE.Mesh(new THREE.BoxGeometry(1.40, 0.22, 1.60), VEHICLE_SHARED_MATS.whiteRoof);
    ac1.position.set(0, 2.55, 1.50);
    const ac2 = new THREE.Mesh(new THREE.BoxGeometry(1.40, 0.22, 1.60), VEHICLE_SHARED_MATS.whiteRoof);
    ac2.position.set(0, 2.55, -2.20);
    root.add(ac1, ac2);

    // Bumpers, lights
    const fBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.30, 0.20), VEHICLE_SHARED_MATS.bumper);
    fBump.position.set(0, 0.45, length / 2 + 0.06);
    const rBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.30, 0.20), VEHICLE_SHARED_MATS.bumper);
    rBump.position.set(0, 0.45, -length / 2 - 0.06);
    root.add(fBump, rBump);

    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.22, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(0.85, 0.75, length / 2 + 0.08);
    const h2 = h1.clone();
    h2.position.x = -0.85;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.35, 0.08), taillightMat);
    t1.position.set(0.85, 0.85, -length / 2 - 0.08);
    const t2 = t1.clone();
    t2.position.x = -0.85;
    root.add(t1, t2);

    // License plates
    const fPlate = makeLicensePlate(0.55, 0.15, false);
    fPlate.position.set(0, 0.35, length / 2 + 0.18);
    const rPlate = makeLicensePlate(0.55, 0.15, true);
    rPlate.position.set(0, 0.35, -length / 2 - 0.18);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    // 6 wheels (2 front steer, 4 rear tandem)
    wheels = [
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, 3.65, wheelRadius, 0.30, true),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, 3.65, wheelRadius, 0.30, true),
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, -2.75, wheelRadius, 0.30, false),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, -2.75, wheelRadius, 0.30, false),
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, -3.95, wheelRadius, 0.30, false),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, -3.95, wheelRadius, 0.30, false)
    ];

  } else if (type === 'ambulance') {
    // 7. High-Fidelity Emergency Paramedic Ambulance
    length = 6.00;
    width = 2.30;
    height = 2.70;
    wheelRadius = 0.44;

    const ambBodyMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.22 });

    // Front Cab
    const cab = new THREE.Mesh(new THREE.BoxGeometry(width, 1.35, 1.80), ambBodyMat);
    cab.position.set(0, 1.10, 1.80);
    cab.castShadow = true;
    root.add(cab);

    // Windshield
    const windshield = new THREE.Mesh(new THREE.BoxGeometry(width - 0.16, 0.62, 0.90), VEHICLE_SHARED_MATS.window);
    windshield.position.set(0, 1.48, 2.00);
    root.add(windshield);

    // Rear Patient Box
    const patientBox = new THREE.Mesh(new THREE.BoxGeometry(width + 0.14, 1.95, 3.90), ambBodyMat);
    patientBox.position.set(0, 1.48, -0.90);
    patientBox.castShadow = true;
    root.add(patientBox);

    // Bold Red Horizontal Chevron Stripe
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(width + 0.18, 0.42, 3.85), VEHICLE_SHARED_MATS.ambRedStripe);
    stripe.position.set(0, 1.35, -0.90);
    root.add(stripe);

    // Blue "Star of Life" Cross Insignia on flanks
    const makeCross = (px, pz) => {
      const g = new THREE.Group();
      const b1 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.65, 0.20), VEHICLE_SHARED_MATS.ambBlueStar);
      const b2 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.20, 0.65), VEHICLE_SHARED_MATS.ambBlueStar);
      g.add(b1, b2);
      g.position.set(px, 1.85, pz);
      return g;
    };
    root.add(makeCross(width / 2 + 0.09, -0.90));
    root.add(makeCross(-width / 2 - 0.09, -0.90));

    // Roof Red Cross
    const rCross1 = new THREE.Mesh(new THREE.BoxGeometry(0.80, 0.04, 0.26), VEHICLE_SHARED_MATS.ambRedStripe);
    const rCross2 = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.04, 0.80), VEHICLE_SHARED_MATS.ambRedStripe);
    rCross1.position.set(0, 2.48, -0.90);
    rCross2.position.set(0, 2.48, -0.90);
    root.add(rCross1, rCross2);

    // Roof Emergency Lightbar with Dynamic Alternating Red & Blue Strobes
    const lightbarBase = new THREE.Mesh(new THREE.BoxGeometry(1.60, 0.14, 0.40), VEHICLE_SHARED_MATS.bumper);
    lightbarBase.position.set(0, 2.48, 1.20);
    root.add(lightbarBase);

    const redStrobeMat = new THREE.MeshStandardMaterial({ color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 3.0 });
    const blueStrobeMat = new THREE.MeshStandardMaterial({ color: 0x3b82f6, emissive: 0x3b82f6, emissiveIntensity: 0.1 });

    const redStrobe = new THREE.Mesh(new THREE.BoxGeometry(0.50, 0.24, 0.28), redStrobeMat);
    redStrobe.position.set(0.50, 2.62, 1.20);
    const blueStrobe = new THREE.Mesh(new THREE.BoxGeometry(0.50, 0.24, 0.28), blueStrobeMat);
    blueStrobe.position.set(-0.50, 2.62, 1.20);
    root.add(redStrobe, blueStrobe);

    root.userData.redStrobeMat = redStrobeMat;
    root.userData.blueStrobeMat = blueStrobeMat;

    // Chrome grille & front bumper
    const grille = new THREE.Mesh(new THREE.BoxGeometry(width * 0.50, 0.26, 0.06), VEHICLE_SHARED_MATS.chrome);
    grille.position.set(0, 0.72, length / 2 - 0.20);
    const fBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.22, 0.20), VEHICLE_SHARED_MATS.bumper);
    fBump.position.set(0, 0.44, length / 2 - 0.15);
    const rStep = new THREE.Mesh(new THREE.BoxGeometry(width * 0.80, 0.12, 0.28), VEHICLE_SHARED_MATS.chrome);
    rStep.position.set(0, 0.38, -length / 2 - 0.04);
    root.add(grille, fBump, rStep);

    // Mirrors, lights
    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.18, 0.20), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.10, 1.20, 1.60);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.10;
    root.add(m1, m2);

    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.20, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(0.72, 0.85, length / 2 - 0.15);
    const h2 = h1.clone();
    h2.position.x = -0.72;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.30, 0.08), taillightMat);
    t1.position.set(0.72, 0.85, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -0.72;
    root.add(t1, t2);

    // License plates
    const fPlate = makeLicensePlate(0.52, 0.14, false);
    fPlate.position.set(0, 0.32, length / 2 - 0.04);
    const rPlate = makeLicensePlate(0.52, 0.14, false);
    rPlate.position.set(0, 0.30, -length / 2 - 0.16);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    wheels = [
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, 1.65, wheelRadius, 0.28, true),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, 1.65, wheelRadius, 0.28, true),
      makeVehicleWheel(width / 2 + 0.03, wheelRadius, -1.65, wheelRadius, 0.28, false),
      makeVehicleWheel(-width / 2 - 0.03, wheelRadius, -1.65, wheelRadius, 0.28, false)
    ];

  } else {
    // 8. Default: Sleek 3-Box Passenger Sedan
    length = 4.65;
    width = 1.95;
    height = 1.40;
    wheelRadius = 0.38;

    const chassis = new THREE.Mesh(new THREE.BoxGeometry(width, 0.48, length), bodyPaintMat);
    chassis.position.y = 0.46;
    chassis.castShadow = true;
    root.add(chassis);

    const grille = new THREE.Mesh(new THREE.BoxGeometry(width * 0.45, 0.22, 0.06), VEHICLE_SHARED_MATS.chrome);
    grille.position.set(0, 0.46, length / 2 + 0.02);
    const fBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.20, 0.18), VEHICLE_SHARED_MATS.bumper);
    fBump.position.set(0, 0.34, length / 2 + 0.08);
    const rBump = new THREE.Mesh(new THREE.BoxGeometry(width + 0.04, 0.20, 0.18), VEHICLE_SHARED_MATS.bumper);
    rBump.position.set(0, 0.34, -length / 2 - 0.08);
    root.add(grille, fBump, rBump);

    const cabin = new THREE.Mesh(new THREE.BoxGeometry(width - 0.18, 0.52, length * 0.52), VEHICLE_SHARED_MATS.window);
    cabin.position.set(0, 0.94, -0.12);
    cabin.castShadow = true;
    root.add(cabin);

    const roof = new THREE.Mesh(new THREE.BoxGeometry(width - 0.22, 0.06, length * 0.42), bodyPaintMat);
    roof.position.set(0, 1.22, -0.12);
    root.add(roof);

    const m1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.10, 0.18), VEHICLE_SHARED_MATS.mirror);
    m1.position.set(width / 2 + 0.08, 0.85, 0.45);
    const m2 = m1.clone();
    m2.position.x = -width / 2 - 0.08;
    root.add(m1, m2);

    const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.18, 0.08), VEHICLE_SHARED_MATS.headlight);
    h1.position.set(width * 0.35, 0.46, length / 2 + 0.02);
    const h2 = h1.clone();
    h2.position.x = -width * 0.35;
    root.add(h1, h2);

    const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.18, 0.08), taillightMat);
    t1.position.set(width * 0.35, 0.50, -length / 2 - 0.02);
    const t2 = t1.clone();
    t2.position.x = -width * 0.35;
    root.add(t1, t2);

    const turn1 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.08), turnMat);
    turn1.position.set(width / 2 + 0.02, 0.44, length / 2 - 0.25);
    const turn2 = turn1.clone();
    turn2.position.x = -width / 2 - 0.02;
    root.add(turn1, turn2);

    // License plates
    const fPlate = makeLicensePlate(0.50, 0.14, false);
    fPlate.position.set(0, 0.28, length / 2 + 0.18);
    const rPlate = makeLicensePlate(0.50, 0.14, true);
    rPlate.position.set(0, 0.28, -length / 2 - 0.18);
    rPlate.rotation.y = Math.PI;
    root.add(fPlate, rPlate);

    wheels = [
      makeVehicleWheel(width / 2 + 0.02, wheelRadius, 1.38, wheelRadius, 0.26, true),
      makeVehicleWheel(-width / 2 - 0.02, wheelRadius, 1.38, wheelRadius, 0.26, true),
      makeVehicleWheel(width / 2 + 0.02, wheelRadius, -1.38, wheelRadius, 0.26, false),
      makeVehicleWheel(-width / 2 - 0.02, wheelRadius, -1.38, wheelRadius, 0.26, false)
    ];
  }

  // Add all wheel steering pivots to vehicle group
  wheels.forEach(w => root.add(w.steerPivot));
  root.userData.wheels = wheels;
  root.userData.steerPivots = wheels.filter(w => w.isFront).map(w => w.steerPivot);
  root.userData.rollGroups = wheels.map(w => w.rollGroup);
  root.userData.wheelRadius = wheelRadius;
  root.userData.taillightMat = taillightMat;
  root.userData.turnMat = turnMat;
  root.userData.length = length;
  root.userData.width = width;
  root.userData.height = height;

  return root;
}

// ============================================================================
// 7. ROBUST 2D ORIENTED BOUNDING BOX (OBB) & SEPARATING AXIS THEOREM (SAT)
// ============================================================================

function getVehicleOBB(vehicle, posX = null, posZ = null, rotY = null) {
  const x = posX !== null ? posX : vehicle.mesh.position.x;
  const z = posZ !== null ? posZ : vehicle.mesh.position.z;
  const heading = rotY !== null ? rotY : vehicle.mesh.rotation.y;
  return {
    x,
    z,
    heading,
    halfLength: (vehicle.length || 4.5) * 0.5,
    halfWidth: (vehicle.width || 2.0) * 0.5
  };
}
window.getVehicleOBB = getVehicleOBB;

function testOBBCollision(boxA, boxB, margin = 0.0) {
  // Center distance vector
  const dx = boxB.x - boxA.x;
  const dz = boxB.z - boxA.z;

  // Box A axes
  const sinA = Math.sin(boxA.heading);
  const cosA = Math.cos(boxA.heading);
  const ax1_x = sinA, ax1_z = cosA;       // Forward A
  const ax2_x = cosA, ax2_z = -sinA;      // Right A

  // Box B axes
  const sinB = Math.sin(boxB.heading);
  const cosB = Math.cos(boxB.heading);
  const bx1_x = sinB, bx1_z = cosB;       // Forward B
  const bx2_x = cosB, bx2_z = -sinB;      // Right B

  const hlA = boxA.halfLength + margin;
  const hwA = boxA.halfWidth + margin;
  const hlB = boxB.halfLength + margin;
  const hwB = boxB.halfWidth + margin;

  // 4 Separating Axes to test (Forward and Right for both boxes)
  const axes = [
    [ax1_x, ax1_z],
    [ax2_x, ax2_z],
    [bx1_x, bx1_z],
    [bx2_x, bx2_z]
  ];

  for (let i = 0; i < 4; i++) {
    const [ux, uz] = axes[i];
    const dist = Math.abs(dx * ux + dz * uz);

    const rA = hlA * Math.abs(ax1_x * ux + ax1_z * uz) +
               hwA * Math.abs(ax2_x * ux + ax2_z * uz);

    const rB = hlB * Math.abs(bx1_x * ux + bx1_z * uz) +
               hwB * Math.abs(bx2_x * ux + bx2_z * uz);

    if (dist > rA + rB) {
      return false; // Separating axis exists: NO intersection
    }
  }

  return true; // Overlap on all 4 axes: intersection detected!
}
window.testOBBCollision = testOBBCollision;

let vehicleIdCounter = 0;

function hasRightOfWay(vehicleA, vehicleB) {
  if (!vehicleA || !vehicleB || vehicleA === vehicleB) return false;

  // 1. Emergency vehicles ALWAYS have absolute priority over non-emergency
  if (vehicleA.isAmbulance && !vehicleB.isAmbulance) return true;
  if (!vehicleA.isAmbulance && vehicleB.isAmbulance) return false;

  // 2. Deadlock resolution: designated clearance vehicle has right-of-way
  if (vehicleA.isDeadlockPriority && !vehicleB.isDeadlockPriority) return true;
  if (!vehicleA.isDeadlockPriority && vehicleB.isDeadlockPriority) return false;

  // 3. Vehicles legitimately inside or clearing the intersection have right-of-way over vehicles outside / waiting at stop lines
  if (vehicleA.inIntersection && !vehicleB.inIntersection) return true;
  if (!vehicleA.inIntersection && vehicleB.inIntersection) return false;

  // 4. Vehicles with legitimate entry permission clearing during yellow/all-red have priority over vehicles waiting at red stop lines
  const sigA = vehicleA.getSignalColor();
  const sigB = vehicleB.getSignalColor();
  if (vehicleA.hasEnteredOnGreen && sigB === 'RED' && !vehicleB.inIntersection) return true;
  if (vehicleB.hasEnteredOnGreen && sigA === 'RED' && !vehicleA.inIntersection) return false;

  // 5. Same lane & approach: the vehicle ahead always has right-of-way (follower yields)
  if (vehicleA.approach === vehicleB.approach && vehicleA.laneIndex === vehicleB.laneIndex) {
    const gapA = vehicleA.getDistanceToVehicleAhead(vehicleB);
    if (gapA >= 0) return false; // vehicleB is ahead, vehicleA yields
    const gapB = vehicleB.getDistanceToVehicleAhead(vehicleA);
    if (gapB >= 0) return true;  // vehicleA is ahead, vehicleB yields
  }

  // 6. If both vehicles are inside the intersection box:
  if (vehicleA.inIntersection && vehicleB.inIntersection) {
    // 6a. If both turning, the one with greater turn progress has priority to exit first
    if (vehicleA.route !== 'straight' && vehicleB.route !== 'straight') {
      if (Math.abs((vehicleA.turnProgress || 0) - (vehicleB.turnProgress || 0)) > 0.03) {
        return (vehicleA.turnProgress || 0) > (vehicleB.turnProgress || 0);
      }
    }
    // 6b. Vehicle closer to its exit boundary has priority to discharge first
    const distA = Math.hypot(vehicleA.mesh.position.x, vehicleA.mesh.position.z);
    const distB = Math.hypot(vehicleB.mesh.position.x, vehicleB.mesh.position.z);
    if (Math.abs(distA - distB) > 0.3) {
      return distA > distB;
    }
    // 6c. Inside intersection precedence: vehicle that entered first (lower ID) clears first
    return (vehicleA.id || 0) < (vehicleB.id || 0);
  }

  // 7. Outside / entry: straight-moving vehicles have right-of-way over vehicles turning across paths
  if (vehicleA.route === 'straight' && vehicleB.route !== 'straight') return true;
  if (vehicleA.route !== 'straight' && vehicleB.route === 'straight') return false;

  // 8. Deterministic tie breaker: lower ID has priority
  return (vehicleA.id || 0) < (vehicleB.id || 0);
}
window.hasRightOfWay = hasRightOfWay;

// Vehicle Simulation Object with Kinematics, Collision Avoidance, and Turning
class Vehicle3D {
  constructor(approach, route = 'straight', isAmbulance = false, vehicleType = 'sedan', laneIndex = null) {
    this.id = ++vehicleIdCounter;
    this.approach = approach; // 'north', 'south', 'east', 'west'
    let normRoute = (route || 'straight').toLowerCase();
    if (normRoute === 'turn_left') normRoute = 'left';
    if (normRoute === 'turn_right') normRoute = 'right';
    if (normRoute !== 'left' && normRoute !== 'right') normRoute = 'straight';
    this.route = normRoute; // 'straight', 'left', 'right'
    this.exitRoad = ROUTE_EXIT_ROADS[this.approach]?.[this.route] || 'opposite';
    this.isAmbulance = isAmbulance;
    this.type = isAmbulance ? 'ambulance' : vehicleType;

    // Multi-lane assignment: Lane 0 (outer / curb, offset 6.0), Lane 1 (inner / median, offset 2.0)
    // Turning lane invariant:
    // Lane 0: dedicated to curb turns (left) and straight
    // Lane 1: dedicated to median turns (right) and straight
    if (this.route === 'left') {
      this.laneIndex = 0; // Curb turn: Lane 0
    } else if (this.route === 'right') {
      this.laneIndex = 1; // Wide turn: Lane 1
    } else if (laneIndex !== null && laneIndex !== undefined) {
      this.laneIndex = (laneIndex === 1) ? 1 : 0;
    } else if (this.isAmbulance) {
      // Emergency vehicle going straight dynamically chooses the lane with fewer queued vehicles
      const countL0 = vehicles3D.filter(v => v.approach === this.approach && !v.hasTurned && v.laneIndex === 0).length;
      const countL1 = vehicles3D.filter(v => v.approach === this.approach && !v.hasTurned && v.laneIndex === 1).length;
      this.laneIndex = (countL1 < countL0) ? 1 : 0;
    } else {
      // Straight vehicles distribute across both lanes
      this.laneIndex = (Math.random() < 0.5) ? 0 : 1;
    }

    let color = 0xffffff;
    if (this.type === 'taxi') {
      color = 0xf59e0b;
    } else if (this.type === 'ambulance') {
      color = 0xffffff;
    } else if (this.type === 'bus') {
      color = 0x0284c7;
    } else {
      color = CAR_PAINTS[Math.floor(Math.random() * CAR_PAINTS.length)];
    }

    this.mesh = createCar3DMesh(this.type, color);
    this.length = this.mesh.userData.length || 4.5;
    this.width = this.mesh.userData.width || 2.0;
    this.wheelRadius = this.mesh.userData.wheelRadius || 0.38;
    this.steerAngle = 0;
    this.targetSteerAngle = 0;
    this.wheelRollAngle = 0;

    if (isAmbulance) {
      this.baseSpeed = 0.92;
    } else if (this.type === 'bus' || this.type === 'truck') {
      this.baseSpeed = 0.36 + Math.random() * 0.04;
    } else if (this.type === 'van' || this.type === 'suv') {
      this.baseSpeed = 0.40 + Math.random() * 0.05;
    } else {
      this.baseSpeed = 0.44 + Math.random() * 0.08;
    }

    this.speed = this.baseSpeed * (selectedSpeedKmh / 50.0) * 0.75;
    this.turnProgress = 0;
    this.hasTurned = false;
    this.hasCleared = false;
    this.inIntersection = false;
    this.clearedIntersection = false;
    this.corridorGranted = false;
    this.entryPermission = 'NONE'; // 'NONE' | 'GRANTED' | 'DENIED_RED' | 'DENIED_BLOCKED' | 'DENIED_PEDESTRIAN'
    this.entrySignalPhase = null;
    this.entrySignalColor = null;
    this.currentRoute = this.route;
    this.exitClearanceStatus = 'approaching'; // 'approaching' | 'holding' | 'entering' | 'clearing' | 'cleared'
    this.hasEnteredOnGreen = false;
    this.stoppedFrames = 0;
    this.turnSide = (this.route === 'left' || this.route === 'right') ? this.route : 'none';
    this.exitRoad = ROUTE_EXIT_ROADS[this.approach]?.[this.route] || (this.approach === 'south' ? 'north' : this.approach === 'north' ? 'south' : this.approach === 'east' ? 'west' : 'east');

    this.initPosition();
    this.lastX = this.mesh.position.x;
    this.lastZ = this.mesh.position.z;
    scene.add(this.mesh);
  }

  getOBB(posX = null, posZ = null, rotY = null) {
    return {
      x: posX !== null ? posX : this.mesh.position.x,
      z: posZ !== null ? posZ : this.mesh.position.z,
      heading: rotY !== null ? rotY : this.mesh.rotation.y,
      halfLength: (this.length || 4.5) * 0.5,
      halfWidth: (this.width || 2.0) * 0.5
    };
  }

  initPosition() {
    // Multi-lane positioning:
    // Lane 0 (outer curb lane): offset 6.0 from road centerline
    // Lane 1 (inner median lane): offset 2.0 from road centerline
    const laneOffset = (this.laneIndex === 1) ? 2.0 : 6.0;
    let startDist = BOUNDS_3D;
    if (this.isAmbulance) {
      let maxDistInLane = 30.0;
      for (let i = 0; i < vehicles3D.length; i++) {
        const other = vehicles3D[i];
        if (other !== this && other.approach === this.approach && other.laneIndex === this.laneIndex && !other.hasTurned) {
          let distFromCenter = 0;
          if (this.approach === 'north') distFromCenter = -other.mesh.position.z;
          else if (this.approach === 'south') distFromCenter = other.mesh.position.z;
          else if (this.approach === 'east') distFromCenter = other.mesh.position.x;
          else if (this.approach === 'west') distFromCenter = -other.mesh.position.x;
          const otherRear = distFromCenter + (other.length || 4.5) * 0.5;
          if (otherRear > maxDistInLane) maxDistInLane = otherRear;
        }
      }
      // Ensure front bumper of ambulance is at least 4.5m behind the rear bumper of any vehicle in that lane
      startDist = Math.max(38.0, maxDistInLane + (this.length || 6.0) * 0.5 + 4.5);
    }

    if (this.approach === 'north') {
      this.mesh.position.set(-laneOffset, 0, -startDist);
      this.mesh.rotation.y = 0; // Facing +Z (Southbound)
    } else if (this.approach === 'south') {
      this.mesh.position.set(laneOffset, 0, startDist);
      this.mesh.rotation.y = Math.PI; // Facing -Z (Northbound)
    } else if (this.approach === 'east') {
      this.mesh.position.set(startDist, 0, -laneOffset);
      this.mesh.rotation.y = -Math.PI / 2; // Facing -X (Westbound)
    } else if (this.approach === 'west') {
      this.mesh.position.set(-startDist, 0, laneOffset);
      this.mesh.rotation.y = Math.PI / 2; // Facing +X (Eastbound)
    }
    this.lastX = this.mesh.position.x;
    this.lastZ = this.mesh.position.z;
  }

  getSignalColor() {
    const sig = state.signals[this.approach];
    return sig ? sig.vehicle : 'RED';
  }

  getDistanceToStopLine() {
    const p = this.mesh.position;
    const halfL = (this.length || 4.5) * 0.5;
    // Precise distance from the FRONT bumper to the stop line
    if (this.approach === 'north') return (-STOP_LINE_DIST_3D - p.z) - halfL;
    if (this.approach === 'south') return (p.z - STOP_LINE_DIST_3D) - halfL;
    if (this.approach === 'east') return (p.x - STOP_LINE_DIST_3D) - halfL;
    if (this.approach === 'west') return (-STOP_LINE_DIST_3D - p.x) - halfL;
    return 999;
  }

  canEnterIntersection(allVehicles) {
    const myLength = this.length || 4.5;

    // 1. Conflicting vehicles inside the intersection box (|X| <= 8.5 && |Z| <= 8.5)
    for (let i = 0; i < allVehicles.length; i++) {
      const other = allVehicles[i];
      if (other === this) continue;

      const otherInBox = Math.abs(other.mesh.position.x) <= 8.5 && Math.abs(other.mesh.position.z) <= 8.5;
      if (otherInBox) {
        // Vehicle from a conflicting approach still occupying the box (e.g. clearing previous phase)
        if (other.approach !== this.approach) {
          return false;
        }
        // Vehicle from same approach:
        if (other.laneIndex === this.laneIndex) {
          // Same lane: cannot enter if vehicle ahead is stopped or slow inside the box
          if (other.speed < 0.15) {
            return false;
          }
          // Also verify safe entry headway so follower does not tailgate into the junction
          let headwayIntoBox = 999;
          if (this.approach === 'north') headwayIntoBox = other.mesh.position.z - (-8.5);
          else if (this.approach === 'south') headwayIntoBox = 8.5 - other.mesh.position.z;
          else if (this.approach === 'east') headwayIntoBox = 8.5 - other.mesh.position.x;
          else if (this.approach === 'west') headwayIntoBox = other.mesh.position.x - (-8.5);
          if (headwayIntoBox < 5.0) {
            return false;
          }
        }
        // NOTE: Different lanes in same approach (Lane 0 vs Lane 1) are physically separated by 4.0m
        // and have parallel or diverging trajectories (curb turn, median turn, straight).
        // They do NOT conflict with each other.
      }
    }

    // 2. Active Pedestrian Crosswalk Check
    const exitRoad = this.exitRoad || ROUTE_EXIT_ROADS[this.approach]?.[this.route] || (this.approach === 'north' ? 'south' : this.approach === 'south' ? 'north' : this.approach === 'east' ? 'west' : 'east');
    const pedsCrossing = pedestrians3D.some(p => p.crosswalkDir === this.approach || p.crosswalkDir === exitRoad);
    if (pedsCrossing) {
      return false;
    }

    // 3. Exit Space Clearance Check ("Don't Block the Box" Anti-Gridlock Rule)
    // Vehicle requires at least 11.2m (crosswalk buffer) + vehicle length + 2.0m bumper clearance
    const requiredExitClearance = 11.2 + myLength + 2.0;

    for (let i = 0; i < allVehicles.length; i++) {
      const other = allVehicles[i];
      if (other === this) continue;

      let otherExitDist = -1;
      let laneMatch = false;

      if (exitRoad === 'north') {
        // Moving North: p.z < -8.0, heading towards -Z (cos heading < -0.3)
        if (other.mesh.position.z < -8.0 && Math.cos(other.mesh.rotation.y) < -0.3) {
          otherExitDist = -other.mesh.position.z;
          const targetX = (this.route === 'straight') ? this.mesh.position.x : (this.laneIndex === 1 ? 2.0 : 6.0);
          laneMatch = Math.abs(other.mesh.position.x - targetX) < 2.5;
        }
      } else if (exitRoad === 'south') {
        // Moving South: p.z > 8.0, heading towards +Z (cos heading > 0.3)
        if (other.mesh.position.z > 8.0 && Math.cos(other.mesh.rotation.y) > 0.3) {
          otherExitDist = other.mesh.position.z;
          const targetX = (this.route === 'straight') ? this.mesh.position.x : (this.laneIndex === 1 ? -2.0 : -6.0);
          laneMatch = Math.abs(other.mesh.position.x - targetX) < 2.5;
        }
      } else if (exitRoad === 'east') {
        // Moving East: p.x > 8.0, heading towards +X (sin heading > 0.3)
        if (other.mesh.position.x > 8.0 && Math.sin(other.mesh.rotation.y) > 0.3) {
          otherExitDist = other.mesh.position.x;
          const targetZ = (this.route === 'straight') ? this.mesh.position.z : (this.laneIndex === 1 ? 2.0 : 6.0);
          laneMatch = Math.abs(other.mesh.position.z - targetZ) < 2.5;
        }
      } else if (exitRoad === 'west') {
        // Moving West: p.x < -8.0, heading towards -X (sin heading < -0.3)
        if (other.mesh.position.x < -8.0 && Math.sin(other.mesh.rotation.y) < -0.3) {
          otherExitDist = -other.mesh.position.x;
          const targetZ = (this.route === 'straight') ? this.mesh.position.z : (this.laneIndex === 1 ? -2.0 : -6.0);
          laneMatch = Math.abs(other.mesh.position.z - targetZ) < 2.5;
        }
      }

      if (otherExitDist > 8.0 && laneMatch) {
        const otherRear = otherExitDist - (other.length || 4.5) * 0.5;
        // If traffic on exit road is queued or moving very slowly near the exit crosswalk
        if (other.speed < 0.25 && otherRear < requiredExitClearance) {
          return false; // Not enough room beyond exit crosswalk; entering now would block intersection
        }
      }
    }

    return true;
  }

  update(allVehicles, dtFactor = 1.0) {
    if (!state.simulationRunning) return;

    // Speed multiplier from user's Speed Meter slider (10 to 100 km/h)
    const speedFactor = Math.max(0.2, selectedSpeedKmh / 50.0);
    const cruiseSpeed = this.baseSpeed * speedFactor;

    const signal = this.getSignalColor();
    const distToStop = this.getDistanceToStopLine();
    const pastStopLine = distToStop < -0.8;
    this.distToStop = distToStop;
    this.passedStopLine = pastStopLine;

    // Intersection Lifecycle & Box Occupancy Tracking
    const halfL = (this.length || 4.5) * 0.5;
    const p = this.mesh.position;
    const physicallyInBox = Math.abs(p.x) <= 8.5 && Math.abs(p.z) <= 8.5;

    if (!this.inIntersection && !this.clearedIntersection) {
      if (physicallyInBox && (this.hasEnteredOnGreen || this.isAmbulance)) {
        this.inIntersection = true;
        this.exitClearanceStatus = 'clearing';
      }
    } else if (this.inIntersection) {
      let hasClearedBox = false;
      const exit = this.exitRoad || ROUTE_EXIT_ROADS[this.approach]?.[this.route];
      if (exit === 'north' && (p.z + halfL < -11.2)) hasClearedBox = true;
      else if (exit === 'south' && (p.z - halfL > 11.2)) hasClearedBox = true;
      else if (exit === 'east' && (p.x - halfL > 11.2)) hasClearedBox = true;
      else if (exit === 'west' && (p.x + halfL < -11.2)) hasClearedBox = true;
      if (hasClearedBox) {
        this.inIntersection = false;
        this.clearedIntersection = true;
        this.exitClearanceStatus = 'cleared';
      } else {
        this.exitClearanceStatus = 'clearing';
      }
    }

    let targetSpeed = cruiseSpeed;

    // 1. Traffic Signal & Anti-Gridlock Compliance
    if (!this.isAmbulance) {
      if (this.clearedIntersection) {
        // Vehicle has safely completed intersection traversal and is cruising along the exit road towards bounds
        targetSpeed = cruiseSpeed;
        this.exitClearanceStatus = 'cleared';
      } else if (this.inIntersection || (this.hasEnteredOnGreen && distToStop <= 0)) {
        // Vehicle legitimately entered on green and is completing its authorized movement:
        // maintain cruise speed to clear the box smoothly during yellow and all-red clearance phases;
        // DO NOT abruptly stop in the intersection
        targetSpeed = cruiseSpeed;
        this.exitClearanceStatus = this.inIntersection ? 'clearing' : 'entering';
        if (state.emergencyActive && this.approach === state.emergencyApproach) {
          targetSpeed = cruiseSpeed * 1.15;
        }
      } else {
        // Vehicle is approaching the stop line on the incoming approach road
        if (signal === 'RED') {
          this.entryPermission = 'DENIED_RED';
          this.inIntersection = false;
          this.hasEnteredOnGreen = false;

          if (distToStop >= 28.0) {
            targetSpeed = cruiseSpeed;
            this.exitClearanceStatus = 'approaching';
          } else if (distToStop > 1.2) {
            targetSpeed = Math.max(0, (distToStop / 28.0) * cruiseSpeed * 0.65);
            if (distToStop <= 1.4) targetSpeed = 0;
            this.exitClearanceStatus = 'approaching';
          } else {
            // Front bumper holding strictly before stop line (min 1.0m buffer, clear of crosswalk)
            targetSpeed = 0;
            this.speed = Math.max(0, this.speed - 0.08);
            if (distToStop <= 1.0) {
              this.speed = 0; // Hard clamp at stop line buffer
              if (this.approach === 'north') this.mesh.position.z = Math.min(this.mesh.position.z, -STOP_LINE_DIST_3D - halfL - 1.0);
              else if (this.approach === 'south') this.mesh.position.z = Math.max(this.mesh.position.z, STOP_LINE_DIST_3D + halfL + 1.0);
              else if (this.approach === 'east') this.mesh.position.x = Math.max(this.mesh.position.x, STOP_LINE_DIST_3D + halfL + 1.0);
              else if (this.approach === 'west') this.mesh.position.x = Math.min(this.mesh.position.x, -STOP_LINE_DIST_3D - halfL - 1.0);
            }
            this.exitClearanceStatus = this.speed < 0.05 ? 'holding' : 'approaching';
          }
        } else if (signal === 'YELLOW') {
          if (this.hasEnteredOnGreen) {
            targetSpeed = cruiseSpeed;
            this.exitClearanceStatus = this.inIntersection ? 'clearing' : 'entering';
          } else if (distToStop >= 26.0) {
            targetSpeed = cruiseSpeed;
            this.exitClearanceStatus = 'approaching';
          } else if (distToStop > 1.2) {
            targetSpeed = Math.max(0, (distToStop / 26.0) * cruiseSpeed * 0.45);
            if (distToStop <= 1.4) targetSpeed = 0;
            this.exitClearanceStatus = 'approaching';
          } else {
            targetSpeed = 0;
            this.speed = Math.max(0, this.speed - 0.08);
            if (distToStop <= 1.0) {
              this.speed = 0;
              if (this.approach === 'north') this.mesh.position.z = Math.min(this.mesh.position.z, -STOP_LINE_DIST_3D - halfL - 1.0);
              else if (this.approach === 'south') this.mesh.position.z = Math.max(this.mesh.position.z, STOP_LINE_DIST_3D + halfL + 1.0);
              else if (this.approach === 'east') this.mesh.position.x = Math.max(this.mesh.position.x, STOP_LINE_DIST_3D + halfL + 1.0);
              else if (this.approach === 'west') this.mesh.position.x = Math.min(this.mesh.position.x, -STOP_LINE_DIST_3D - halfL - 1.0);
            }
            this.exitClearanceStatus = this.speed < 0.05 ? 'holding' : 'approaching';
          }
        } else if (signal === 'GREEN') {
          // Anti-Gridlock ("Don't Block the Box") Entry Gate:
          // Before entering crosswalk/intersection, check that box & exit road are clear
          if (distToStop < 3.5) {
            const canEnter = this.canEnterIntersection(allVehicles);
            if (!canEnter) {
              this.entryPermission = 'DENIED_BLOCKED';
              targetSpeed = 0;
              if (distToStop <= 1.2) {
                this.speed = Math.max(0, this.speed - 0.08);
              }
              if (distToStop <= 1.0) {
                this.speed = 0;
                if (this.approach === 'north') this.mesh.position.z = Math.min(this.mesh.position.z, -STOP_LINE_DIST_3D - halfL - 1.0);
                else if (this.approach === 'south') this.mesh.position.z = Math.max(this.mesh.position.z, STOP_LINE_DIST_3D + halfL + 1.0);
                else if (this.approach === 'east') this.mesh.position.x = Math.max(this.mesh.position.x, STOP_LINE_DIST_3D + halfL + 1.0);
                else if (this.approach === 'west') this.mesh.position.x = Math.min(this.mesh.position.x, -STOP_LINE_DIST_3D - halfL - 1.0);
              }
              this.exitClearanceStatus = this.speed < 0.05 ? 'holding' : 'approaching';
            } else {
              this.entryPermission = 'GRANTED';
              this.entrySignalPhase = state.phase;
              this.entrySignalColor = 'GREEN';
              this.hasEnteredOnGreen = true;
              this.exitClearanceStatus = 'entering';
              targetSpeed = cruiseSpeed;
              if (state.emergencyActive && this.approach === state.emergencyApproach) {
                targetSpeed = cruiseSpeed * 1.15;
              }
            }
          } else {
            this.entryPermission = 'APPROACHING_GREEN';
            targetSpeed = cruiseSpeed;
            this.exitClearanceStatus = 'approaching';
            if (state.emergencyActive && this.approach === state.emergencyApproach) {
              targetSpeed = cruiseSpeed * 1.15;
            }
          }
        }

        // Active pedestrian crosswalk check: vehicles must never move onto an occupied crosswalk
        const hasPedestriansCrossing = pedestrians3D.some(p => p.crosswalkDir === this.approach);
        if (hasPedestriansCrossing && distToStop > 0 && distToStop < 26.0) {
          targetSpeed = Math.max(0, (distToStop / 26.0) * cruiseSpeed * 0.45);
          if (distToStop < 1.6) targetSpeed = 0;
          this.entryPermission = 'DENIED_PEDESTRIAN';
        }
      }

      // Controlled Lateral Yielding: if an ambulance is approaching from behind in the SAME lane
      if (state.emergencyActive && this.approach === state.emergencyApproach && !this.inIntersection && !this.clearedIntersection && !this.hasTurned) {
        const ambBehind = allVehicles.find(v =>
          v.isAmbulance &&
          v.approach === this.approach &&
          v.laneIndex === this.laneIndex &&
          !v.hasTurned
        );
        if (ambBehind) {
          const distBehind = ambBehind.getDistanceToVehicleAhead(this);
          if (distBehind > 0 && distBehind < 32.0) {
            const targetLane = (this.laneIndex === 0) ? 1 : 0;
            const targetOffset = (targetLane === 1) ? 2.0 : 6.0;
            let targetX = this.mesh.position.x;
            let targetZ = this.mesh.position.z;
            if (this.approach === 'north') targetX = -targetOffset;
            else if (this.approach === 'south') targetX = targetOffset;
            else if (this.approach === 'east') targetZ = -targetOffset;
            else if (this.approach === 'west') targetZ = targetOffset;

            // Verify target lane has ample buffer (14m) before attempting lateral shift
            let yieldClear = true;
            for (let j = 0; j < allVehicles.length; j++) {
              const v = allVehicles[j];
              if (v === this) continue;

              let latMatch = false;
              let longDiff = 0;
              if (this.approach === 'north' || this.approach === 'south') {
                latMatch = Math.abs(v.mesh.position.x - targetX) < 2.5;
                longDiff = Math.abs(v.mesh.position.z - this.mesh.position.z);
              } else {
                latMatch = Math.abs(v.mesh.position.z - targetZ) < 2.5;
                longDiff = Math.abs(v.mesh.position.x - this.mesh.position.x);
              }

              if (latMatch && longDiff < 14.0) {
                yieldClear = false;
                break;
              }
            }

            if (yieldClear) {
              this.laneIndex = targetLane;
            }
          }
        }
      }
    } else {
      // Emergency Ambulance Behavior
      // 1. Authoritative Backend Emergency Priority Synchronization
      const isMatchingApproach = (!state.emergencyApproach || state.emergencyApproach === this.approach);
      const isBackendPriorityPhase = (state.phase === 'EMERGENCY_PRIORITY' && isMatchingApproach);
      const isApproachSignalGreen = (state.signals && state.signals[this.approach]?.vehicle === 'GREEN' && isMatchingApproach);

      // Once priority has been granted for this incoming approach, latch it permanently for this ambulance's passage!
      // This guarantees that an older frontend state or transient polling cannot re-enable red-light braking.
      if (state.emergencyActive && (isBackendPriorityPhase || isApproachSignalGreen)) {
        this.corridorGranted = true;
      }

      if (this.corridorGranted) {
        // Protected emergency priority is active!
        // Strictly ignore ordinary red-light, yellow-light, and stop-line braking rules.
        // Maintain cruising speed and proceed decisively through the stop line and intersection along assigned route.
        targetSpeed = cruiseSpeed;
      } else if (state.emergencyActive) {
        // Opposing traffic clearance is in progress (Yellow / All-Red safety interval).
        // Respect clearance: smoothly decelerate and stop before the stop line if necessary; do not enter before clearance finishes.
        if (distToStop >= 28.0) {
          targetSpeed = cruiseSpeed * 0.75;
        } else if (distToStop > 1.2) {
          targetSpeed = Math.max(0.10, (distToStop / 28) * cruiseSpeed * 0.45);
          if (distToStop < 2.0) targetSpeed = 0;
        } else if (distToStop >= -1.0) {
          // Front bumper holding strictly at stop line (safely clear of crosswalk)
          targetSpeed = 0;
          this.speed = Math.max(0, this.speed - 0.08);
        } else {
          // If already past stop line, keep proceeding forward safely
          targetSpeed = cruiseSpeed * 0.5;
        }

        // Active pedestrian crosswalk check: only yields during safety clearance if pedestrians are actively crossing
        const hasPedestriansCrossing = pedestrians3D.some(p => p.crosswalkDir === this.approach);
        if (hasPedestriansCrossing && distToStop > 0 && distToStop < 14) {
          targetSpeed = Math.max(0, (distToStop / 14) * cruiseSpeed * 0.3);
          if (distToStop < 1.4) targetSpeed = 0;
        }
      } else {
        // Protected phase concluded or cleared; keep ambulance cruising through the far-side exit
        targetSpeed = cruiseSpeed;
      }

      // Diagnostic stopping reason calculation
      let stoppingReason = 'cruising_at_speed';
      if (this.corridorGranted) {
        stoppingReason = 'protected_green_corridor_active';
      } else if (distToStop <= 2.0 && distToStop >= -1.0) {
        stoppingReason = 'yielding_at_stop_line_for_clearance';
      } else if (distToStop < 28 && distToStop > 2.0) {
        stoppingReason = 'decelerating_for_safety_clearance';
      }
      if (!this.corridorGranted && pedestrians3D.some(p => p.crosswalkDir === this.approach) && distToStop > 0 && distToStop < 14) {
        stoppingReason = 'yielding_to_crossing_pedestrians';
      }

      if (ambulancePointLight) {
        ambulancePointLight.position.copy(this.mesh.position).add(new THREE.Vector3(0, 3.5, 0));
      }

      // Telemetry diagnostics logging with stopping reason
      if (!this.lastTelemetryLog || Date.now() - this.lastTelemetryLog > 600) {
        this.lastTelemetryLog = Date.now();
        console.log(`[Ambulance Diagnostics] phase=${state.phase} | approach=${this.approach} | corridorGranted=${this.corridorGranted} | signal=${signal} | timer=${state.timeInPhase.toFixed(1)}s/${state.phaseDuration.toFixed(1)}s | pos=(${this.mesh.position.x.toFixed(1)}, ${this.mesh.position.z.toFixed(1)}) | distToStop=${distToStop.toFixed(1)}m | speed=${this.speed.toFixed(3)} | targetSpeed=${targetSpeed.toFixed(3)} | stoppingReason=${stoppingReason}`);
      }

      // As soon as ambulance has completed its movement through the intersection under priority and reached exit boundary, clear emergency
      if (this.hasClearedIntersection() && (this.corridorGranted || state.emergencyActive)) {
        apiControlAmbulance(this.approach, this.route, false, 'exit_boundary_cleared', 'Vehicle3D.hasClearedIntersection');
      }
    }

    // 2. Dynamic Emergency Strobe Mesh Flashing on Ambulance Roof
    if (this.isAmbulance && this.mesh.userData.redStrobeMat && this.mesh.userData.blueStrobeMat) {
      if (state.emergencyActive) {
        const strobeState = Math.floor(beaconTimer * 10) % 2;
        this.mesh.userData.redStrobeMat.emissiveIntensity = strobeState === 0 ? 3.0 : 0.1;
        this.mesh.userData.blueStrobeMat.emissiveIntensity = strobeState === 1 ? 3.0 : 0.1;
      } else {
        this.mesh.userData.redStrobeMat.emissiveIntensity = 0.05;
        this.mesh.userData.blueStrobeMat.emissiveIntensity = 0.05;
      }
    }

    // 3. Collision Avoidance (Bumper-to-Bumper Buffer & Forward Lookahead)
    // All vehicles (including emergency vehicles) obey bumper buffering to prevent clipping
    for (const other of allVehicles) {
      if (other === this) continue;
      const bumperGap = this.getDistanceToVehicleAhead(other);
      if (bumperGap > -1.0 && bumperGap < 28.0) {
        // Bumper buffer: 1.2m for cars, 1.5m for heavy vehicles and ambulance
        const isHeavy = (this.type === 'truck' || this.type === 'bus' || this.isAmbulance || other.type === 'truck' || other.type === 'bus' || other.isAmbulance);
        const minStoppedGap = isHeavy ? 1.5 : 1.2;

        if (bumperGap <= 0.60) {
          // Immediate safety threshold: zero target speed and halt forward velocity
          targetSpeed = 0;
          this.speed = Math.min(this.speed, 0.01);
        } else if (bumperGap <= minStoppedGap) {
          targetSpeed = 0;
          this.speed = Math.max(0, this.speed - 0.08); // Assertive queue braking to prevent inertia encroachment
        } else {
          const gapAboveMin = bumperGap - minStoppedGap;
          if (other.speed < 0.05) {
            // Lead vehicle is stopped in queue or at stop line: smoothly decelerate to rest at minStoppedGap
            const safeApproachSpeed = Math.min(cruiseSpeed * 0.65, Math.sqrt(gapAboveMin * 1.8));
            targetSpeed = Math.min(targetSpeed, safeApproachSpeed);
          } else {
            // Lead vehicle is moving: match leader speed and smoothly spool up queue headway
            const followSpeed = other.speed + Math.min(cruiseSpeed * 0.35, gapAboveMin * 0.30);
            const maxSafeSpeed = Math.min(cruiseSpeed, followSpeed);
            targetSpeed = Math.min(targetSpeed, maxSafeSpeed);
          }
        }
      }
    }

    // Deadlock detection & resolution inside the junction
    if (this.inIntersection && !this.clearedIntersection) {
      if (this.speed < 0.03) {
        this.stoppedFrames = (this.stoppedFrames || 0) + 1;
      } else {
        this.stoppedFrames = 0;
      }
    } else {
      this.stoppedFrames = 0;
    }

    this.isDeadlockPriority = false;
    if (this.stoppedFrames > 25) {
      // Vehicle stalled inside intersection for > 25 frames
      let hasPriorityInDeadlock = true;
      for (let j = 0; j < allVehicles.length; j++) {
        const other = allVehicles[j];
        if (other === this) continue;
        if (other.inIntersection && (other.stoppedFrames || 0) > 20) {
          if (!hasRightOfWay(this, other)) {
            hasPriorityInDeadlock = false;
            break;
          }
        }
      }
      if (hasPriorityInDeadlock) {
        // Priority vehicle breaks deadlock by maintaining clearance propulsion along its route
        this.isDeadlockPriority = true;
        targetSpeed = Math.max(cruiseSpeed * 0.5, 0.22);
        this.speed = Math.max(this.speed, 0.15);
      }
    }

    // Forward Lookahead OBB Collision Check (for crossing, turning, and merging vehicles)
    const fx = Math.sin(this.mesh.rotation.y);
    const fz = Math.cos(this.mesh.rotation.y);
    const lookDist = Math.max(1.8, this.speed * dtFactor * 3.0);
    const lookOBB = {
      x: this.mesh.position.x + fx * (halfL + lookDist * 0.5),
      z: this.mesh.position.z + fz * (halfL + lookDist * 0.5),
      heading: this.mesh.rotation.y,
      halfLength: lookDist * 0.5,
      halfWidth: (this.width || 2.0) * 0.5
    };
    for (const other of allVehicles) {
      if (other === this) continue;
      // other must be ahead along our travel heading; trailing vehicles cannot block our forward path
      const dxOther = other.mesh.position.x - this.mesh.position.x;
      const dzOther = other.mesh.position.z - this.mesh.position.z;
      const longProj = dxOther * fx + dzOther * fz;
      if (longProj < 0.2) continue; // Trailing or alongside; ignore for forward lookahead

      if (testOBBCollision(lookOBB, other.getOBB(), 0.04)) {
        if (!hasRightOfWay(this, other) && !this.isDeadlockPriority) {
          targetSpeed = Math.min(targetSpeed, Math.max(0, other.speed * 0.85));
          if (other.speed < 0.05) {
            const gap = this.getDistanceToVehicleAhead(other);
            if (gap >= 0 && gap < 1.5) {
              targetSpeed = 0;
            }
          }
        } else {
          // If this vehicle has right of way and is inside intersection, maintain clearance momentum
          if (this.inIntersection) {
            targetSpeed = Math.max(targetSpeed, cruiseSpeed * 0.65);
          }
        }
      }
    }

    // Dynamic lane bypass: ambulance can switch lanes if blocked ahead AND adjacent lane is truly clear
    if (this.isAmbulance && !this.passedStopLine) {
      const blockedAhead = allVehicles.some(v =>
        v !== this &&
        v.approach === this.approach &&
        v.laneIndex === this.laneIndex &&
        !v.hasTurned &&
        this.getDistanceToVehicleAhead(v) > 0 &&
        this.getDistanceToVehicleAhead(v) < 22.0
      );
      if (blockedAhead) {
        const targetLane = (this.laneIndex === 0) ? 1 : 0;
        // Verify that target lane has NO vehicles alongside or ahead within 28m
        const fxHead = Math.sin(this.mesh.rotation.y);
        const fzHead = Math.cos(this.mesh.rotation.y);
        const targetOccupied = allVehicles.some(v => {
          if (v === this || v.approach !== this.approach || v.laneIndex !== targetLane || v.hasTurned) return false;
          const dx = v.mesh.position.x - this.mesh.position.x;
          const dz = v.mesh.position.z - this.mesh.position.z;
          const longOffset = dx * fxHead + dz * fzHead;
          return longOffset > -6.0 && longOffset < 28.0;
        });

        if (!targetOccupied) {
          const targetOffset = (targetLane === 1) ? 2.0 : 6.0;
          let testX = this.mesh.position.x;
          let testZ = this.mesh.position.z;
          if (this.approach === 'north') testX = -targetOffset;
          else if (this.approach === 'south') testX = targetOffset;
          else if (this.approach === 'east') testZ = -targetOffset;
          else if (this.approach === 'west') testZ = targetOffset;

          const shiftOBB = {
            x: testX,
            z: testZ,
            heading: this.mesh.rotation.y,
            halfLength: (this.length || 5.2) * 0.5,
            halfWidth: (this.width || 2.2) * 0.5
          };
          const canShift = !allVehicles.some(v => v !== this && testOBBCollision(shiftOBB, v.getOBB(), 0.20));
          if (canShift) {
            this.laneIndex = targetLane;
          }
        }
      }
    }

    // Smooth lateral alignment to lane centerline with collision prevention
    if (!this.hasTurned && (this.route === 'straight' || !this.passedStopLine)) {
      const targetOffset = (this.laneIndex === 1) ? 2.0 : 6.0;
      const latRate = Math.min(1.0, 0.08 * dtFactor);
      let candX = this.mesh.position.x;
      let candZ = this.mesh.position.z;
      if (this.approach === 'north') {
        candX += (-targetOffset - candX) * latRate;
      } else if (this.approach === 'south') {
        candX += (targetOffset - candX) * latRate;
      } else if (this.approach === 'east') {
        candZ += (-targetOffset - candZ) * latRate;
      } else if (this.approach === 'west') {
        candZ += (targetOffset - candZ) * latRate;
      }

      const candOBB = {
        x: candX,
        z: candZ,
        heading: this.mesh.rotation.y,
        halfLength: (this.length || 4.5) * 0.5,
        halfWidth: (this.width || 2.0) * 0.5
      };
      const collidesLaterally = allVehicles.some(v => v !== this && testOBBCollision(candOBB, v.getOBB(), 0.12));
      if (!collidesLaterally) {
        this.mesh.position.x = candX;
        this.mesh.position.z = candZ;
      }
    }

    // 4. Smooth Acceleration and Braking (No Instantaneous Snapping)
    const effectiveAccel = (this.isAmbulance ? 0.055 : 0.032) * Math.max(0.4, speedFactor) * dtFactor;
    const effectiveDecel = 0.055 * Math.max(0.4, speedFactor) * dtFactor;

    if (this.speed < targetSpeed) {
      this.speed = Math.min(targetSpeed, this.speed + effectiveAccel);
    } else if (this.speed > targetSpeed) {
      this.speed = Math.max(targetSpeed, this.speed - effectiveDecel);
    }

    // 5. Taillight flare when braking or holding
    if (this.mesh.userData.taillightMat) {
      this.mesh.userData.taillightMat.emissiveIntensity = this.speed < 0.15 ? 1.6 : 0.6;
    }

    // 6. Movement along Trajectory with Swept Collision Detection
    if (this.route === 'straight' || this.hasTurned) {
      this.targetSteerAngle = 0;
      const heading = this.mesh.rotation.y;
      const totalDist = this.speed * dtFactor;
      if (totalDist > 0.0001) {
        const stepSize = 0.15; // Max 15cm substep for swept collision detection
        const numSteps = Math.max(1, Math.ceil(totalDist / stepSize));
        const stepDist = totalDist / numSteps;
        const sinH = Math.sin(heading);
        const cosH = Math.cos(heading);

        for (let s = 0; s < numSteps; s++) {
          const testX = this.mesh.position.x + sinH * stepDist;
          const testZ = this.mesh.position.z + cosH * stepDist;
          const testOBB = {
            x: testX,
            z: testZ,
            heading: heading,
            halfLength: (this.length || 4.5) * 0.5,
            halfWidth: (this.width || 2.0) * 0.5
          };

          // Test against every other vehicle
          let hitOther = false;
          for (let j = 0; j < allVehicles.length; j++) {
            const other = allVehicles[j];
            if (other === this) continue;
            if (testOBBCollision(testOBB, other.getOBB(), 0.02)) {
              if (hasRightOfWay(this, other) || this.isDeadlockPriority) {
                const curDist = Math.hypot(this.mesh.position.x - other.mesh.position.x, this.mesh.position.z - other.mesh.position.z);
                const nextDist = Math.hypot(testX - other.mesh.position.x, testZ - other.mesh.position.z);
                const dxOther = other.mesh.position.x - testX;
                const dzOther = other.mesh.position.z - testZ;
                const otherInFront = (dxOther * sinH + dzOther * cosH) > 0.1;
                if (nextDist >= curDist - 0.05 || !otherInFront) {
                  continue; // Priority vehicle moving away/clearing
                }
              }
              hitOther = true;
              break;
            }
          }

          if (hitOther) {
            this.speed = 0;
            break;
          }

          this.mesh.position.x = testX;
          this.mesh.position.z = testZ;
        }
      }
    } else {
      this.handleTurning(dtFactor, allVehicles);
    }

    // 7. Steering smoothing & front-wheel steering around Y axis
    const steerSmoothing = Math.min(1.0, 0.32 * dtFactor);
    this.steerAngle += (this.targetSteerAngle - this.steerAngle) * steerSmoothing;
    if (Math.abs(this.steerAngle) < 0.001) this.steerAngle = 0;

    if (this.mesh.userData.steerPivots) {
      for (let i = 0; i < this.mesh.userData.steerPivots.length; i++) {
        this.mesh.userData.steerPivots[i].rotation.y = this.steerAngle;
      }
    }

    // 8. Physical Wheel Rotation: wheelRotation = distanceTravelled / wheelRadius
    const distMoved = Math.hypot(
      this.mesh.position.x - this.lastX,
      this.mesh.position.z - this.lastZ
    );
    this.lastX = this.mesh.position.x;
    this.lastZ = this.mesh.position.z;

    if (distMoved > 0.0001) {
      const dRoll = distMoved / this.wheelRadius;
      this.wheelRollAngle = (this.wheelRollAngle + dRoll) % (Math.PI * 2);
      if (this.mesh.userData.rollGroups) {
        for (let i = 0; i < this.mesh.userData.rollGroups.length; i++) {
          this.mesh.userData.rollGroups[i].rotation.x = this.wheelRollAngle;
        }
      }
    }

    // 8. Blinking Turn Indicators
    if (this.mesh.userData.turnMat && this.turnSide !== 'none' && !this.hasTurned) {
      const isBlinking = Math.floor(beaconTimer * 8) % 2 === 0;
      this.mesh.userData.turnMat.emissiveIntensity = isBlinking ? 2.0 : 0.0;
    }
  }

  getDistanceToVehicleAhead(other) {
    if (!other || other === this) return -1;

    // Approach road: vehicles before the intersection only follow vehicles in the same approach and same lane
    if (!this.inIntersection && !this.clearedIntersection) {
      if (other.approach !== this.approach) return -1;
      if (this.laneIndex !== other.laneIndex) return -1;
    }

    // Inside intersection:
    if (this.inIntersection) {
      // Vehicles on different approaches or different routes have non-parallel crossing/turning paths
      // Guarded by OBB / SAT lookahead and canEnterIntersection, not 1D lane following
      if (other.approach !== this.approach || other.route !== this.route || this.laneIndex !== other.laneIndex) {
        return -1;
      }
    }

    // Exit road:
    if (this.clearedIntersection) {
      if (!other.clearedIntersection || other.exitRoad !== this.exitRoad || this.laneIndex !== other.laneIndex) {
        return -1;
      }
    }

    const p1 = this.mesh.position;
    const p2 = other.mesh.position;
    const heading = this.mesh.rotation.y;

    // Unit forward and right vectors of this vehicle
    const fx = Math.sin(heading);
    const fz = Math.cos(heading);
    const rx = Math.cos(heading);
    const rz = -Math.sin(heading);

    // Vector from this vehicle center to other vehicle center
    const dx = p2.x - p1.x;
    const dz = p2.z - p1.z;

    const longDist = dx * fx + dz * fz; // Longitudinal distance along forward heading
    const latDist = Math.abs(dx * rx + dz * rz); // Lateral offset perpendicular to heading

    // Half extents
    const halfL1 = (this.length || 4.5) * 0.5;
    const halfL2 = (other.length || 4.5) * 0.5;
    const halfW1 = (this.width || 2.0) * 0.5;
    const halfW2 = (other.width || 2.0) * 0.5;

    // Corridor width allows safe side-by-side traffic in adjacent lanes (4.0m apart)
    // while catching any vehicle within our lane or currently intruding/merging laterally
    const corridorWidth = halfW1 + halfW2 + 0.35;

    // Must be in our forward driving corridor and strictly ahead along travel heading
    if (latDist <= corridorWidth && longDist > 0) {
      return longDist - halfL1 - halfL2;
    }

    return -1;
  }

  handleTurning(dtFactor = 1.0, allVehicles = []) {
    const curve = getVehicleTurnCurve(this.approach, this.route, this.laneIndex);
    if (!curve) {
      this.hasTurned = true;
      this.targetSteerAngle = 0;
      return;
    }

    const p = this.mesh.position;

    // Has it reached the start of the intersection turn curve yet?
    if (this.turnProgress === 0) {
      let atTurnStart = false;
      if (this.approach === 'south' && p.z <= curve.p0[1]) atTurnStart = true;
      else if (this.approach === 'north' && p.z >= curve.p0[1]) atTurnStart = true;
      else if (this.approach === 'east' && p.x <= curve.p0[0]) atTurnStart = true;
      else if (this.approach === 'west' && p.x >= curve.p0[0]) atTurnStart = true;

      if (!atTurnStart) {
        // Move straight along approach heading towards the turn entry with swept substeps
        const heading = this.mesh.rotation.y;
        const totalDist = this.speed * dtFactor;
        if (totalDist > 0.0001) {
          const stepSize = 0.15;
          const numSteps = Math.max(1, Math.ceil(totalDist / stepSize));
          const stepDist = totalDist / numSteps;
          const sinH = Math.sin(heading);
          const cosH = Math.cos(heading);

          for (let s = 0; s < numSteps; s++) {
            const testX = p.x + sinH * stepDist;
            const testZ = p.z + cosH * stepDist;
            const testOBB = {
              x: testX,
              z: testZ,
              heading: heading,
              halfLength: (this.length || 4.5) * 0.5,
              halfWidth: (this.width || 2.0) * 0.5
            };

            let hit = false;
            if (allVehicles) {
              for (let j = 0; j < allVehicles.length; j++) {
                const other = allVehicles[j];
                if (other === this) continue;
                if (testOBBCollision(testOBB, other.getOBB(), 0.02)) {
                  if (hasRightOfWay(this, other) || this.isDeadlockPriority) {
                    const curDist = Math.hypot(p.x - other.mesh.position.x, p.z - other.mesh.position.z);
                    const nextDist = Math.hypot(testX - other.mesh.position.x, testZ - other.mesh.position.z);
                    const dxOther = other.mesh.position.x - testX;
                    const dzOther = other.mesh.position.z - testZ;
                    const otherInFront = (dxOther * Math.sin(heading) + dzOther * Math.cos(heading)) > 0.1;
                    if (nextDist >= curDist - 0.05 || !otherInFront) {
                      continue; // Priority vehicle moving away/clearing
                    }
                  }
                  hit = true;
                  break;
                }
              }
            }

            if (hit) {
              this.speed = 0;
              break;
            }
            p.x = testX;
            p.z = testZ;
          }
        }

        // When approaching within 4.5m of turn start, initiate smooth pre-steering
        let distToTurnStart = 999;
        if (this.approach === 'south') distToTurnStart = p.z - curve.p0[1];
        else if (this.approach === 'north') distToTurnStart = curve.p0[1] - p.z;
        else if (this.approach === 'east') distToTurnStart = p.x - curve.p0[0];
        else if (this.approach === 'west') distToTurnStart = curve.p0[0] - p.x;

        if (distToTurnStart < 4.5 && distToTurnStart > 0) {
          const tPre = 0.12;
          const [lax, laz] = evalCubicBezier(curve.p0, curve.p1, curve.p2, curve.p3, tPre);
          const localX = (lax - p.x) * Math.cos(heading) - (laz - p.z) * Math.sin(heading);
          const localZ = (lax - p.x) * Math.sin(heading) + (laz - p.z) * Math.cos(heading);
          this.targetSteerAngle = Math.max(-0.45, Math.min(0.45, Math.atan2(localX, localZ) * 1.25));
        } else {
          this.targetSteerAngle = 0;
        }
        return;
      }
    }

    // Progress along Bézier curve based on speed, dtFactor, and curve length with swept substeps
    const totalStepDt = (this.speed * dtFactor) / (curve.length || 10.0);
    if (totalStepDt > 0.00001) {
      const maxSubStepDt = 0.02;
      const numSteps = Math.max(1, Math.ceil(totalStepDt / maxSubStepDt));
      const subDt = totalStepDt / numSteps;

      for (let s = 0; s < numSteps; s++) {
        const nextProgress = Math.min(1.0, this.turnProgress + subDt);
        const [bx, bz] = evalCubicBezier(curve.p0, curve.p1, curve.p2, curve.p3, nextProgress);
        const [dx, dz] = evalCubicBezierTangent(curve.p0, curve.p1, curve.p2, curve.p3, nextProgress);
        let nextHeading = this.mesh.rotation.y;
        if (Math.hypot(dx, dz) > 1e-4) {
          nextHeading = Math.atan2(dx, dz);
        }

        const testOBB = {
          x: bx,
          z: bz,
          heading: nextHeading,
          halfLength: (this.length || 4.5) * 0.5,
          halfWidth: (this.width || 2.0) * 0.5
        };

        let hit = false;
        if (allVehicles) {
          for (let j = 0; j < allVehicles.length; j++) {
            const other = allVehicles[j];
            if (other === this) continue;
            if (testOBBCollision(testOBB, other.getOBB(), 0.02)) {
              if (hasRightOfWay(this, other) || this.isDeadlockPriority) {
                const curDist = Math.hypot(p.x - other.mesh.position.x, p.z - other.mesh.position.z);
                const nextDist = Math.hypot(bx - other.mesh.position.x, bz - other.mesh.position.z);
                const dxOther = other.mesh.position.x - bx;
                const dzOther = other.mesh.position.z - bz;
                const otherInFront = (dxOther * Math.sin(nextHeading) + dzOther * Math.cos(nextHeading)) > 0.1;
                if (nextDist >= curDist - 0.05 || !otherInFront) {
                  continue; // Priority vehicle moving away/clearing along curve
                }
              }
              hit = true;
              break;
            }
          }
        }

        if (hit) {
          this.speed = 0;
          break;
        }

        this.turnProgress = nextProgress;
        p.x = bx;
        p.z = bz;
        this.mesh.rotation.y = nextHeading;

        if (this.turnProgress >= 1.0) break;
      }
    }

    const t = this.turnProgress;
    // Pure Pursuit Steering: calculate steering angle aiming at lookahead point along curve
    const tAhead = Math.min(1.0, t + 0.12);
    const [lax, laz] = evalCubicBezier(curve.p0, curve.p1, curve.p2, curve.p3, tAhead);
    const heading = this.mesh.rotation.y;
    const localX = (lax - p.x) * Math.cos(heading) - (laz - p.z) * Math.sin(heading);
    const localZ = (lax - p.x) * Math.sin(heading) + (laz - p.z) * Math.cos(heading);
    let steerCalc = Math.atan2(localX, localZ) * 1.35;

    // Smoothly unwind steering back to center as vehicle nears end of curve
    if (t > 0.80) {
      steerCalc *= Math.max(0, (1.0 - t) / 0.20);
    }
    this.targetSteerAngle = Math.max(-0.45, Math.min(0.45, steerCalc));

    if (this.turnProgress >= 1.0) {
      this.hasTurned = true;
      p.x = curve.p3[0];
      p.z = curve.p3[1];
      this.mesh.rotation.y = curve.exitHeading;
      this.targetSteerAngle = 0;
    }
  }

  hasClearedIntersection() {
    if (this.hasCleared) return false;
    // For turning vehicles, they MUST complete their turn curve before clearance can be evaluated
    if (this.route !== 'straight' && !this.hasTurned) return false;

    const p = this.mesh.position;
    const exit = this.exitRoad || ROUTE_EXIT_ROADS[this.approach]?.[this.route];

    // Priority corridor is held until ambulance reaches the exit road boundary (38.0m)
    let cleared = false;
    if (exit === 'north' && p.z <= -EXIT_BOUNDARY_DIST_3D) cleared = true;
    else if (exit === 'south' && p.z >= EXIT_BOUNDARY_DIST_3D) cleared = true;
    else if (exit === 'east' && p.x >= EXIT_BOUNDARY_DIST_3D) cleared = true;
    else if (exit === 'west' && p.x <= -EXIT_BOUNDARY_DIST_3D) cleared = true;

    if (cleared) {
      this.hasCleared = true;
      window.lastClearedAmbulance = {
        approach: this.approach,
        route: this.route,
        clearedAt: Date.now()
      };
      return true;
    }
    return false;
  }

  isOutOfBounds() {
    const p = this.mesh.position;
    return (
      p.x < -BOUNDS_3D - 15 || p.x > BOUNDS_3D + 15 ||
      p.z < -BOUNDS_3D - 15 || p.z > BOUNDS_3D + 15
    );
  }

  destroy() {
    scene.remove(this.mesh);
  }
}
window.Vehicle3D = Vehicle3D;

function clearAllVehicles3D() {
  vehicles3D.forEach(v => v.destroy());
  vehicles3D.length = 0;
}

function spawnAmbulance3D(approach, route = 'straight', caller = 'api', reason = 'operator_dispatch') {
  window.lastClearedAmbulance = null;
  // Always clean up any previous ambulances so dispatching starts fresh and reliable
  for (let i = vehicles3D.length - 1; i >= 0; i--) {
    if (vehicles3D[i].isAmbulance) {
      vehicles3D[i].destroy();
      vehicles3D.splice(i, 1);
    }
  }

  // Preserve all ordinary vehicles: NEVER delete, hide, or reset them on emergency dispatch!
  const amb = new Vehicle3D(approach, route, true, 'ambulance');
  vehicles3D.push(amb);
  const exitName = (ROUTE_EXIT_ROADS[approach]?.[route] || 'opposite').toUpperCase();
  addLocalEventLog('EMERGENCY', `Ambulance dispatched on ${approach.toUpperCase()} approach [Route: ${route.toUpperCase()} -> Exit: ${exitName}] by ${caller} (${reason}). Clearance preemption initiated.`);
}

// ============================================================================
// 9. HIGH-VISIBILITY 3D PEDESTRIANS & SYNCHRONIZATION
// ============================================================================

function createPedestrian3DMesh(colorHex = 0x10b981) {
  const root = new THREE.Group();
  const skinMat = new THREE.MeshStandardMaterial({ color: 0xfbcfe8, roughness: 0.75 });
  const clothesMat = new THREE.MeshStandardMaterial({
    color: colorHex,
    roughness: 0.35,
    emissive: colorHex,
    emissiveIntensity: 0.3
  });
  const limbMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7 });

  // Head
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.32, 14, 12), skinMat);
  head.position.y = 1.85;
  head.castShadow = true;
  root.add(head);

  // Hair / Hat cap
  const hat = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.35, 0.16, 12), limbMat);
  hat.position.y = 2.05;
  root.add(hat);

  // Torso (High-contrast bright jacket)
  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.90, 0.38), clothesMat);
  torso.position.y = 1.28;
  torso.castShadow = true;
  root.add(torso);

  // Left & Right Arms
  const leftArm = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.75, 0.18), clothesMat);
  leftArm.position.set(0.40, 1.25, 0);
  const rightArm = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.75, 0.18), clothesMat);
  rightArm.position.set(-0.40, 1.25, 0);
  root.add(leftArm, rightArm);

  // Left & Right Legs
  const leftLeg = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.95, 0.22), limbMat);
  leftLeg.position.set(0.18, 0.48, 0);
  const rightLeg = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.95, 0.22), limbMat);
  rightLeg.position.set(-0.18, 0.48, 0);
  root.add(leftLeg, rightLeg);

  root.userData.leftLeg = leftLeg;
  root.userData.rightLeg = rightLeg;
  root.userData.leftArm = leftArm;
  root.userData.rightArm = rightArm;

  return root;
}

class Pedestrian3D {
  constructor(crosswalkDir, reverse = false) {
    this.crosswalkDir = crosswalkDir; // 'north', 'south', 'east', 'west'
    this.reverse = reverse;
    this.progress = 0;
    // Walk duration calibrated to 7.0s WALK phase (at 60fps, 420 frames: 1/420 ≈ 0.0024)
    this.speed = 0.0024 + Math.random() * 0.0003;
    const colors = [0x06b6d4, 0xf59e0b, 0x10b981, 0xec4899, 0x8b5cf6, 0x3b82f6];
    const color = colors[Math.floor(Math.random() * colors.length)];
    this.mesh = createPedestrian3DMesh(color);
    this.updatePosition();
    scene.add(this.mesh);
  }

  update() {
    this.progress += this.speed;
    this.updatePosition();

    // Natural arm & leg swing walking cycle
    const swing = Math.sin(this.progress * 48) * 0.55;
    if (this.mesh.userData.leftLeg) this.mesh.userData.leftLeg.rotation.x = swing;
    if (this.mesh.userData.rightLeg) this.mesh.userData.rightLeg.rotation.x = -swing;
    if (this.mesh.userData.leftArm) this.mesh.userData.leftArm.rotation.x = -swing;
    if (this.mesh.userData.rightArm) this.mesh.userData.rightArm.rotation.x = swing;
  }

  updatePosition() {
    // Crosswalk spans between sidewalk curb lines at -7.8 and +7.8
    const startCoord = -HALF_ROAD_3D + 0.3;
    const endCoord = HALF_ROAD_3D - 0.3;
    const pVal = this.reverse ? (1.0 - this.progress) : this.progress;
    const current = startCoord + (endCoord - startCoord) * pVal;
    const lateralOffset = this.reverse ? 0.7 : -0.7; // Walk on opposite sides of zebra crossing!

    if (this.crosswalkDir === 'north') {
      this.mesh.position.set(current, 0.28, -CROSSWALK_DIST_3D + lateralOffset);
      this.mesh.rotation.y = this.reverse ? -Math.PI / 2 : Math.PI / 2;
    } else if (this.crosswalkDir === 'south') {
      this.mesh.position.set(-current, 0.28, CROSSWALK_DIST_3D + lateralOffset);
      this.mesh.rotation.y = this.reverse ? Math.PI / 2 : -Math.PI / 2;
    } else if (this.crosswalkDir === 'west') {
      this.mesh.position.set(-CROSSWALK_DIST_3D + lateralOffset, 0.28, -current);
      this.mesh.rotation.y = this.reverse ? Math.PI : 0;
    } else if (this.crosswalkDir === 'east') {
      this.mesh.position.set(CROSSWALK_DIST_3D + lateralOffset, 0.28, current);
      this.mesh.rotation.y = this.reverse ? 0 : Math.PI;
    }
  }

  destroy() {
    scene.remove(this.mesh);
  }
}
window.Pedestrian3D = Pedestrian3D;

function spawnPedestrians3D(crossing = 'north') {
  clearAllPedestrians3D();
  if (crossing === 'all') {
    ['north', 'south', 'east', 'west'].forEach(dir => {
      pedestrians3D.push(new Pedestrian3D(dir, false));
      pedestrians3D.push(new Pedestrian3D(dir, true));
    });
  } else {
    // Spawn two pedestrians crossing in opposite directions on the selected zebra crossing
    pedestrians3D.push(new Pedestrian3D(crossing, false));
    pedestrians3D.push(new Pedestrian3D(crossing, true));
  }
}

function clearAllPedestrians3D() {
  pedestrians3D.forEach(p => p.destroy());
  pedestrians3D.length = 0;
}

// ============================================================================
// 10. WORLD-ANCHORED 3D HUD OVERLAY PROJECTIONS
// ============================================================================

const HUD_WORLD_ANCHORS = {
  north: new THREE.Vector3(-4.0, 8.8, -12.0),
  south: new THREE.Vector3(4.0, 8.8, 12.0),
  east: new THREE.Vector3(12.0, 8.8, -4.0),
  west: new THREE.Vector3(-12.0, 8.8, 4.0)
};

function updateWorldHudLabels() {
  // Clean fixed four-panel layout at viewport corners to eliminate overlapping
  // and guarantee an unobstructed view of the 3D intersection.
  const dirs = ['north', 'south', 'east', 'west'];
  dirs.forEach(dir => {
    const cap = dir.charAt(0).toUpperCase() + dir.slice(1).toLowerCase();
    const el = document.getElementById(`hud${cap}`);
    if (el) {
      el.style.opacity = '1';
      // Clear any legacy inline positions so CSS corner anchoring rules govern
      el.style.left = '';
      el.style.top = '';
      el.style.bottom = '';
      el.style.right = '';
      el.style.transform = '';
    }
  });
}

function updateCompass() {
  const dial = document.getElementById('compassDial');
  if (!dial || !camera) return;

  // Exact 2D screen projection of World North vector (0, 0, -10) relative to intersection center (0, 0, 0)
  const centerNdc = new THREE.Vector3(0, 0, 0).project(camera);
  const northNdc = new THREE.Vector3(0, 0, -10).project(camera);

  const dx = northNdc.x - centerNdc.x;
  const dy = northNdc.y - centerNdc.y;

  // In CSS rotate: 0deg is up (towards +Y in NDC), positive angle rotates clockwise
  const angleRad = Math.atan2(dx, dy);
  const angleDeg = angleRad * (180 / Math.PI);

  dial.style.transform = `rotate(${angleDeg.toFixed(1)}deg)`;
}

// ============================================================================
// 11. 3D TRAFFIC SIGNAL LENSES UPDATE
// ============================================================================

function update3DSignalLenses() {
  const dirs = ['north', 'south', 'east', 'west'];

  dirs.forEach(d => {
    const lenses = signalLenses3D[d];
    const sig = state.signals[d];
    if (!lenses || !sig) return;

    // Vehicle lights
    const isRed = sig.vehicle === 'RED';
    const isYellow = sig.vehicle === 'YELLOW';
    const isGreen = sig.vehicle === 'GREEN';

    if (lenses.red) lenses.red.emissiveIntensity = isRed ? 2.8 : 0.05;
    if (lenses.yellow) lenses.yellow.emissiveIntensity = isYellow ? 2.8 : 0.05;
    if (lenses.green) lenses.green.emissiveIntensity = isGreen ? 2.8 : 0.05;

    // Pedestrian lights
    const isWalk = sig.pedestrian === 'WALK';
    const isFlash = sig.pedestrian === 'FLASHING_DONT_WALK';

    if (lenses.pedWalk) {
      lenses.pedWalk.emissiveIntensity = isWalk ? 2.4 : 0.05;
    }
    if (lenses.pedStop) {
      if (isFlash) {
        lenses.pedStop.emissiveIntensity = Math.floor(beaconTimer * 4) % 2 === 0 ? 2.2 : 0.05;
      } else {
        lenses.pedStop.emissiveIntensity = isWalk ? 0.05 : 2.2;
      }
    }
  });
}

// ============================================================================
// 11. TRAFFIC SPAWNER WITH SPEED & DENSITY SCALING
// ============================================================================

// Live queue counting and backend telemetry sync
// Live queue counting across all lanes and backend telemetry sync
let lastTelemetrySync = 0;

function getLiveQueueCounts() {
  const result = {
    north: { queue: 0, total: 0, lane0: 0, lane1: 0 },
    south: { queue: 0, total: 0, lane0: 0, lane1: 0 },
    east:  { queue: 0, total: 0, lane0: 0, lane1: 0 },
    west:  { queue: 0, total: 0, lane0: 0, lane1: 0 }
  };

  for (let i = 0; i < vehicles3D.length; i++) {
    const v = vehicles3D[i];
    if (v.isAmbulance || !v.approach || v.hasTurned) continue;
    const app = v.approach.toLowerCase();
    if (!result[app]) continue;

    if (!v.passedStopLine) {
      result[app].total++;
      // A vehicle is considered 'queued' only when:
      // - Near or behind the stop line (distToStop > 0 && distToStop < 42.0)
      // - Stopped or moving very slowly (speed < 0.25)
      // - Waiting for green or obstructed by another queued vehicle
      if (v.distToStop > 0 && v.distToStop < 42.0 && v.speed < 0.25) {
        result[app].queue++;
        if (v.laneIndex === 1) {
          result[app].lane1++; // Inner lane (Lane 1)
        } else {
          result[app].lane0++; // Outer lane (Lane 0)
        }
      }
    }
  }
  return result;
}

function syncTelemetryToBackend(now) {
  if (now - lastTelemetrySync < 1500) return;
  lastTelemetrySync = now;
  const counts = getLiveQueueCounts();
  const approaches = {
    north: counts.north.queue,
    south: counts.south.queue,
    east:  counts.east.queue,
    west:  counts.west.queue
  };
  fetch('/api/telemetry/vehicles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approaches, counts })
  }).catch(() => {});
}

function burstSpawnVehicles(approach, count = 4) {
  if (!approach || state.emergencyActive || !scene) return;
  const app = approach.toLowerCase();
  const existingOnApp = vehicles3D.filter(v => v.approach === app && !v.hasTurned);
  if (existingOnApp.length >= 10) return;

  const fleetTypes = ['sedan', 'suv', 'taxi', 'hatchback', 'van', 'truck', 'bus'];

  // Track the rearmost extent in each lane
  const getRearDist = (lane) => {
    let maxRear = 11.5; // Stop line is at 11.0m
    for (const v of vehicles3D) {
      if (v.approach === app && v.laneIndex === lane && !v.hasTurned) {
        let centerDist = 0;
        if (app === 'north') centerDist = -v.mesh.position.z;
        else if (app === 'south') centerDist = v.mesh.position.z;
        else if (app === 'east') centerDist = v.mesh.position.x;
        else if (app === 'west') centerDist = -v.mesh.position.x;
        const rear = centerDist + (v.length || 4.5) * 0.5;
        if (rear > maxRear) maxRear = rear;
      }
    }
    return maxRear;
  };

  let spawned = 0;
  for (let i = 0; i < count; i++) {
    if (vehicles3D.length >= 36) break;

    // Pick lane with fewer queued vehicles to maintain balanced side-by-side queues
    const countL0 = vehicles3D.filter(v => v.approach === app && v.laneIndex === 0 && !v.hasTurned).length;
    const countL1 = vehicles3D.filter(v => v.approach === app && v.laneIndex === 1 && !v.hasTurned).length;
    const targetLane = countL0 <= countL1 ? 0 : 1;

    const vType = fleetTypes[Math.floor(Math.random() * fleetTypes.length)];
    let vRoute = 'straight';
    if (targetLane === 0 && Math.random() < 0.25) vRoute = 'left';
    else if (targetLane === 1 && Math.random() < 0.25) vRoute = 'right';

    const v = new Vehicle3D(app, vRoute, false, vType, targetLane);
    const halfL = (v.length || 4.5) * 0.5;
    const laneOffset = targetLane === 1 ? 2.0 : 6.0;

    const currentRear = getRearDist(targetLane);
    // Buffer of 1.5m behind preceding vehicle bumper
    let candDist = Math.max(16.0, currentRear + 1.5 + halfL);

    const setPos = (d) => {
      if (app === 'north') v.mesh.position.set(-laneOffset, 0, -d);
      else if (app === 'south') v.mesh.position.set(laneOffset, 0, d);
      else if (app === 'east') v.mesh.position.set(d, 0, -laneOffset);
      else if (app === 'west') v.mesh.position.set(-d, 0, laneOffset);
    };

    setPos(candDist);

    // Verify non-intersection with all other vehicles using OBB collision check
    let attempts = 0;
    while (attempts < 10) {
      const candOBB = v.getOBB();
      const collides = vehicles3D.some(other => other !== v && testOBBCollision(candOBB, other.getOBB(), 0.15));
      if (!collides) break;
      candDist += 2.0;
      setPos(candDist);
      attempts++;
    }

    if (candDist < BOUNDS_3D + 5.0) {
      v.lastX = v.mesh.position.x;
      v.lastZ = v.mesh.position.z;
      v.speed = 0.0;
      vehicles3D.push(v);
      spawned++;
    } else {
      v.destroy();
    }
  }
}
window.burstSpawnVehicles = burstSpawnVehicles;

function handle3DTrafficSpawner(now) {
  if (!state.simulationRunning || selectedSpeedKmh === 0) return;

  // Max vehicles cap to maintain fluid realistic city flow without gridlock
  const MAX_VEHICLES = 36;
  if (vehicles3D.length >= MAX_VEHICLES) return;

  // Adaptive spawn rate based on global or approach density
  let spawnInterval = 1400; // Medium baseline
  if (state.trafficDensity === 'high') spawnInterval = 750;
  else if (state.trafficDensity === 'low') spawnInterval = 2600;

  if (now - lastSpawn3D > spawnInterval) {
    lastSpawn3D = now;

    // Dynamic High-Demand Direction Rotation:
    // High-demand approach receives ~65% of arrivals, while other directions receive ~11-12% each.
    const approaches = ['north', 'south', 'east', 'west'];
    const highApp = (selectedDensityApproach || state.currentHighDemandApproach || 'south').toLowerCase();

    const weights = {};
    approaches.forEach(app => {
      const metric = state.approachMetrics ? state.approachMetrics[app] : null;
      if (app === highApp || (metric && metric.density === 'high')) {
        weights[app] = 0.65;
      } else if (metric && metric.density === 'medium') {
        weights[app] = 0.18;
      } else {
        weights[app] = 0.11;
      }
    });

    const sumWeights = Object.values(weights).reduce((a, b) => a + b, 0);
    let r = Math.random() * sumWeights;
    let chosenApproach = highApp;
    for (const app of approaches) {
      if (r <= weights[app]) {
        chosenApproach = app;
        break;
      }
      r -= weights[app];
    }

    // Never spawn ordinary vehicles into an active emergency corridor
    if (state.emergencyActive && chosenApproach === state.emergencyApproach) {
      return;
    }

    // Realistic vehicle fleet distribution across 7 vehicle types
    const roll = Math.random();
    let vType = 'sedan';
    if (roll < 0.22) vType = 'sedan';
    else if (roll < 0.38) vType = 'hatchback';
    else if (roll < 0.52) vType = 'suv';
    else if (roll < 0.66) vType = 'taxi';
    else if (roll < 0.78) vType = 'van';
    else if (roll < 0.88) vType = 'truck';
    else vType = 'bus';

    // Route distribution: heavy vehicles stay straight or turn right
    const routeRoll = Math.random();
    let route = 'straight';
    if (vType === 'truck' || vType === 'bus') {
      if (routeRoll > 0.85) route = 'turn_right';
      else route = 'straight';
    } else {
      if (routeRoll > 0.82) route = 'turn_right';
      else if (routeRoll > 0.68) route = 'turn_left';
    }

    // Multi-lane selection:
    let chosenLane = 0;
    if (route === 'turn_right' || route === 'right') {
      chosenLane = 1; // Inner median lane for right turn across intersection
    } else if (route === 'turn_left' || route === 'left') {
      chosenLane = 0; // Outer curb lane for left turn
    } else {
      // Balance straight traffic across Lane 0 and Lane 1
      const countL0 = vehicles3D.filter(v => v.approach === chosenApproach && v.laneIndex === 0 && !v.hasTurned).length;
      const countL1 = vehicles3D.filter(v => v.approach === chosenApproach && v.laneIndex === 1 && !v.hasTurned).length;
      chosenLane = countL0 <= countL1 ? 0 : 1;
    }

    // Verify distance before spawning in chosen lane to avoid overlap at boundary
    const spawnOccupied = vehicles3D.some(v =>
      v.approach === chosenApproach &&
      v.laneIndex === chosenLane &&
      !v.hasTurned &&
      Math.hypot(v.mesh.position.x, v.mesh.position.z) > (BOUNDS_3D - (v.length || 4.5) - 3.0)
    );
    if (!spawnOccupied) {
      vehicles3D.push(new Vehicle3D(chosenApproach, route, false, vType, chosenLane));
    }
  }

  // Periodic telemetry queue synchronization with backend
  syncTelemetryToBackend(now);
}

// ============================================================================
// 12. MAIN 3D ANIMATION LOOP (60 FPS)
// ============================================================================

let lastFrameTime = 0;

function animate3D(time) {
  requestAnimationFrame(animate3D);

  if (!lastFrameTime) lastFrameTime = time;
  const rawDt = (time - lastFrameTime) * 0.001;
  lastFrameTime = time;
  const dt = Math.min(0.05, Math.max(0.005, rawDt || 0.016));
  const dtFactor = dt / 0.01667;

  beaconTimer += dt;

  // 1. Controls update
  if (controls) controls.update();

  // 2. World-Anchored 3D HUD Overlays & Fixed Compass Indicator
  updateWorldHudLabels();
  updateCompass();

  // 3. Traffic Spawner
  handle3DTrafficSpawner(time);

  // 4. Update 3D Traffic Signals
  update3DSignalLenses();

  // 4. Update Vehicles & compute average fleet speed telemetry
  let totalSpeed = 0;
  let activeCount = 0;

  for (let i = vehicles3D.length - 1; i >= 0; i--) {
    const v = vehicles3D[i];
    v.update(vehicles3D, dtFactor);
    totalSpeed += v.speed;
    activeCount++;
    if (v.isOutOfBounds()) {
      if (v.isAmbulance && state.emergencyActive) {
        apiControlAmbulance(v.approach, v.route, false, 'out_of_bounds_failsafe', 'Vehicle3D.isOutOfBounds');
      }
      v.destroy();
      vehicles3D.splice(i, 1);
    }
  }

  // Update Fleet Avg Speed readout in UI
  const telemetryAvg = document.getElementById('telemetryAvgSpeed');
  if (telemetryAvg) {
    if (activeCount > 0) {
      const avgKmh = Math.round((totalSpeed / activeCount / 0.45) * 50);
      telemetryAvg.textContent = `${avgKmh} km/h`;
    } else {
      telemetryAvg.textContent = `${selectedSpeedKmh} km/h`;
    }
  }

  // 5. Update Pedestrians
  for (let i = pedestrians3D.length - 1; i >= 0; i--) {
    const p = pedestrians3D[i];
    p.update();
    if (p.progress >= 1.0) {
      p.destroy();
      pedestrians3D.splice(i, 1);
    }
  }

  // 6. Emergency Strobe Light Pulse
  if (state.emergencyActive) {
    const strobeState = Math.floor(beaconTimer * 8) % 2;
    if (ambulancePointLight) {
      ambulancePointLight.intensity = 2.6;
      ambulancePointLight.color.setHex(strobeState === 0 ? 0xef4444 : 0x3b82f6);
    }
  } else if (ambulancePointLight) {
    ambulancePointLight.intensity = 0;
  }

  // 7. Render 3D Scene
  if (renderer && scene && camera) {
    renderer.render(scene, camera);
  }
}

// ============================================================================
// 13. VEHICLE DIAGNOSTICS & TELEMETRY API
// ============================================================================
window.getVehicleDiagnostics = function() {
  return (vehicles3D || []).map(v => {
    const p = v.mesh.position;
    const halfL = (v.length || 4.5) * 0.5;
    let distFromCenter = 999;
    if (v.approach === 'north') distFromCenter = -p.z;
    else if (v.approach === 'south') distFromCenter = p.z;
    else if (v.approach === 'east') distFromCenter = p.x;
    else if (v.approach === 'west') distFromCenter = -p.x;
    const frontFromCenter = distFromCenter - halfL;

    return {
      id: v.id,
      isAmbulance: v.isAmbulance,
      approach: v.approach,
      currentRoute: v.route,
      laneIndex: v.laneIndex,
      speed: Number(v.speed.toFixed(3)),
      x: Number(p.x.toFixed(2)),
      z: Number(p.z.toFixed(2)),
      distToStop: Number(v.getDistanceToStopLine().toFixed(2)),
      frontFromCenter: Number(frontFromCenter.toFixed(2)),
      entryPermission: v.entryPermission || 'NONE',
      entrySignalPhase: v.entrySignalPhase || null,
      entrySignalColor: v.entrySignalColor || null,
      intersectionOccupancy: !!v.inIntersection,
      exitClearanceStatus: v.exitClearanceStatus || 'approaching',
      hasEnteredOnGreen: !!v.hasEnteredOnGreen,
      crosswalkViolation: (frontFromCenter <= 10.6 && distFromCenter >= 8.2 && !v.clearedIntersection && v.entryPermission !== 'GRANTED'),
      boxViolation: (Math.abs(p.x) <= 8.5 && Math.abs(p.z) <= 8.5 && v.entryPermission === 'DENIED_RED')
    };
  });
};

// ============================================================================
// 14. INITIALIZATION
// ============================================================================

window.addEventListener('DOMContentLoaded', () => {
  fetchState();
  init3D();
  setVehicleSpeed(50);
});
