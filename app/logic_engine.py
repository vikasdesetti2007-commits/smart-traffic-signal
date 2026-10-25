"""Propositional Logic Engine for Smart Traffic Signal Demonstration.

Formal Propositions:
- P: Traffic density is high.
- Q: Emergency vehicle (ambulance) is detected.
- R: Pedestrian crossing is active.
- G: Green signal permissibility formula:
     G = (P OR Q) AND NOT R

Note on Safety vs Logic Demonstration:
This logical formula serves as an illustrative formal verification rule.
In physical traffic engineering, a single boolean cannot govern multi-phase
conflicting approaches or clearance intervals. The deterministic
IntersectionController state machine uses this logic evaluation to inform
phase transitions while strictly enforcing clearance intervals (Yellow/All-Red)
and non-conflicting green allocations.
"""

from typing import List, Tuple
from app.schemas import LogicEvaluation, TruthTableRow


def compute_formula(p: bool, q: bool, r: bool) -> Tuple[bool, bool, bool]:
    """Compute (P OR Q), NOT R, and G = (P OR Q) AND NOT R."""
    p_or_q = p or q
    not_r = not r
    g = p_or_q and not_r
    return p_or_q, not_r, g


def get_truth_table() -> List[TruthTableRow]:
    """Generate all 8 combinations of the truth table for G = (P OR Q) AND NOT R."""
    table: List[TruthTableRow] = []
    
    # 8 combinations ordered canonically: 000, 001, 010, 011, 100, 101, 110, 111
    cases = [
        (
            1, False, False, False,
            "Low traffic, no emergency, no pedestrian request.",
            "Normal baseline: Vehicles rest or cycle on demand; high-priority green not demanded."
        ),
        (
            2, False, False, True,
            "Pedestrian crossing active; low traffic, no emergency.",
            "Safe Pedestrian Walk: Vehicle movements stopped (G=False); crosswalk active."
        ),
        (
            3, False, True, False,
            "Emergency vehicle detected on low-density road.",
            "Emergency Preemption: Route priority granted (G=True) after safe clearance."
        ),
        (
            4, False, True, True,
            "Conflict: Emergency vehicle detected while pedestrian crossing active.",
            "Safety Resolution: G=False halts general vehicle movement. Controller enforces safe pedestrian clearance before opening emergency corridor."
        ),
        (
            5, True, False, False,
            "High traffic density with no emergency and no pedestrian.",
            "Capacity Flow: Green phase extended (G=True) to maximize vehicular throughput."
        ),
        (
            6, True, False, True,
            "High traffic density, but pedestrian button pressed.",
            "Pedestrian Right-of-Way: Vehicles held (G=False); pedestrians safely cross despite high traffic volume."
        ),
        (
            7, True, True, False,
            "High traffic density AND emergency vehicle present.",
            "Emergency Supersedes Congestion: Priority corridor granted (G=True) to ambulance."
        ),
        (
            8, True, True, True,
            "High traffic, emergency vehicle, AND pedestrian crossing.",
            "Critical Conflict: G=False holds traffic. State machine safely finishes crosswalk clearance, then immediately gives ambulance exclusive green."
        ),
    ]

    for row_id, p, q, r, desc, safety in cases:
        p_or_q, not_r, g = compute_formula(p, q, r)
        table.append(TruthTableRow(
            row_id=row_id,
            p=p,
            q=q,
            r=r,
            p_or_q=p_or_q,
            not_r=not_r,
            g=g,
            description=desc,
            safety_context=safety
        ))

    return table


def evaluate_traffic_proposition(p: bool, q: bool, r: bool) -> LogicEvaluation:
    """Evaluate the current intersection condition against the formal proposition."""
    p_or_q, not_r, g = compute_formula(p, q, r)
    
    # Identify canonical row: row = (P*4 + Q*2 + R*1) + 1
    row_id = (int(p) * 4 + int(q) * 2 + int(r) * 1) + 1
    
    table = get_truth_table()
    matched_row = next((row for row in table if row.row_id == row_id), table[0])

    safety_notes = {
        1: "Baseline resting/cyclic flow. G=False indicates high-priority green is not asserted.",
        2: "Pedestrians have active walk phase. Vehicles held at all-red stop lines.",
        3: "Ambulance priority active. Vehicle green granted along ambulance corridor.",
        4: "Concurrent Emergency + Pedestrian: Proposition holds G=False to protect pedestrians while controller clears route.",
        5: "High traffic green phase enabled to flush traffic queue.",
        6: "Pedestrian safety overrides vehicle queue demand. Vehicles must yield.",
        7: "Emergency preemption overrides high traffic congestion.",
        8: "Triple-condition conflict: Pedestrians cleared under strict priority, followed by emergency corridor."
    }

    return LogicEvaluation(
        p=p,
        q=q,
        r=r,
        g=g,
        p_or_q=p_or_q,
        not_r=not_r,
        active_row=row_id,
        formula="G = (P ∨ Q) ∧ ¬R",
        description=matched_row.description,
        safety_note=safety_notes.get(row_id, "Normal deterministic safety supervision.")
    )
