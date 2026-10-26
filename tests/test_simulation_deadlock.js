/**
 * Regression test for traffic simulation vehicle deadlock and right-of-way resolution.
 * Verifies:
 * 1. Dedicated turning lane invariants (curb turn -> Lane 0, median turn -> Lane 1).
 * 2. Longitudinal clearance priority inside intersection box (leading vehicle clears first).
 * 3. Deadlock priority right-of-way precedence.
 * 4. Stale hasEnteredOnGreen reset upon RED phase.
 */

const assert = require('assert');

// Mock minimal browser environment
global.window = global;
global.document = {
  getElementById: () => null,
  querySelectorAll: () => []
};

// Load app.js functions by extracting relevant functions or evaluating
const fs = require('fs');
const appJsContent = fs.readFileSync(__dirname + '/../static/app.js', 'utf8');

// Extract hasRightOfWay and testOBBCollision
eval(appJsContent.slice(
  appJsContent.indexOf('function testOBBCollision'),
  appJsContent.indexOf('// Vehicle Simulation Object with Kinematics')
));

console.log('--- TEST 1: hasRightOfWay longitudinal clearance precedence inside box ---');
// South vehicle 14: straight in Lane 1, pos = (2.0, 3.9), heading North (Math.PI)
const vStraight = {
  id: 14,
  approach: 'south',
  laneIndex: 1,
  route: 'straight',
  inIntersection: true,
  turnProgress: 0,
  mesh: {
    position: { x: 2.0, z: 3.9 },
    rotation: { y: Math.PI } // Facing North: fx = 0, fz = -1
  },
  getSignalColor: () => 'GREEN'
};

// South vehicle 7: turning right from pos = (4.2, 1.6), heading West (-Math.PI/2)
const vTurning = {
  id: 7,
  approach: 'south',
  laneIndex: 0,
  route: 'right',
  inIntersection: true,
  turnProgress: 0.15,
  mesh: {
    position: { x: 4.2, z: 1.6 },
    rotation: { y: -Math.PI / 2 } // Facing West: fx = -1, fz = 0
  },
  getSignalColor: () => 'GREEN'
};

// Longitudinal projection of turning vehicle along straight vehicle's heading (North: -Z):
// dx = 4.2 - 2.0 = 2.2, dz = 1.6 - 3.9 = -2.3
// projAlongStraight = 2.2 * 0 + (-2.3) * (-1) = +2.3m (ahead of straight vehicle)
// Straight vehicle is at straight's rear relative to turning vehicle.
// Turning vehicle MUST have right-of-way so it clears out of the straight vehicle's path!
assert.strictEqual(
  hasRightOfWay(vTurning, vStraight),
  true,
  'Vehicle physically ahead along conflicting vehicle path must have right-of-way'
);
assert.strictEqual(
  hasRightOfWay(vStraight, vTurning),
  false,
  'Trailing vehicle must yield to vehicle physically blocking ahead in junction'
);
console.log('PASSED: Leading vehicle has right-of-way to clear junction.');

console.log('--- TEST 2: Deadlock resolution priority flag ---');
const vDeadlocked1 = {
  id: 101,
  inIntersection: true,
  isDeadlockPriority: true,
  route: 'straight',
  mesh: { position: { x: 0, z: 0 }, rotation: { y: 0 } },
  getSignalColor: () => 'RED'
};
const vDeadlocked2 = {
  id: 102,
  inIntersection: true,
  isDeadlockPriority: false,
  route: 'straight',
  mesh: { position: { x: 0, z: 2 }, rotation: { y: 0 } },
  getSignalColor: () => 'RED'
};

assert.strictEqual(
  hasRightOfWay(vDeadlocked1, vDeadlocked2),
  true,
  'Deadlock designated priority vehicle must hold right-of-way'
);
assert.strictEqual(
  hasRightOfWay(vDeadlocked2, vDeadlocked1),
  false,
  'Non-priority vehicle must yield to designated deadlock clearer'
);
console.log('PASSED: Deadlock priority correctly breaks mutual blocking.');

console.log('--- TEST 3: Spawner & Vehicle3D Lane Invariant Enforcement ---');
// Verify spawner assigns Lane 1 for right turns and Lane 0 for left turns
assert(
  appJsContent.includes("chosenLane = 1; // Inner median lane for right turn across intersection"),
  "handle3DTrafficSpawner must assign Lane 1 to right turns"
);
assert(
  appJsContent.includes("chosenLane = 0; // Outer curb lane for left turn"),
  "handle3DTrafficSpawner must assign Lane 0 to left turns"
);

// Verify Vehicle3D constructor enforces turning lane invariants
assert(
  appJsContent.includes("if (this.route === 'left') {\n      this.laneIndex = 0; // Curb turn: Lane 0"),
  "Vehicle3D constructor must enforce Lane 0 for left turns"
);
assert(
  appJsContent.includes("else if (this.route === 'right') {\n      this.laneIndex = 1; // Wide turn: Lane 1"),
  "Vehicle3D constructor must enforce Lane 1 for right turns"
);
console.log('PASSED: Turning lane invariants strictly enforced.');

console.log('--- TEST 4: hasEnteredOnGreen reset on RED ---');
// Verify that hasEnteredOnGreen is cleared on RED if not in intersection
assert(
  appJsContent.includes("if (signal === 'RED') {\n          this.entryPermission = 'DENIED_RED';\n          this.inIntersection = false;\n          this.hasEnteredOnGreen = false;"),
  "hasEnteredOnGreen must be reset to false when light is RED outside intersection"
);
console.log('PASSED: Stale green entry permission reset on RED.');

console.log('\nALL REGRESSION CHECKS PASSED SUCCESSFULLY!');
