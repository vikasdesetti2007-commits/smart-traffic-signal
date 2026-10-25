"""Unit tests for the formal propositional logic engine."""

import pytest
from app.logic_engine import compute_formula, evaluate_traffic_proposition, get_truth_table


def test_truth_table_has_eight_rows():
    """Verify that exactly 2^3 = 8 combinations exist in the truth table."""
    table = get_truth_table()
    assert len(table) == 8
    
    # Check that row_ids are 1 through 8
    row_ids = [row.row_id for row in table]
    assert row_ids == list(range(1, 9))


@pytest.mark.parametrize(
    "p, q, r, expected_g",
    [
        (False, False, False, False),  # 000 -> (0 or 0) and not 0 = 0 and 1 = 0
        (False, False, True, False),   # 001 -> (0 or 0) and not 1 = 0 and 0 = 0
        (False, True, False, True),    # 010 -> (0 or 1) and not 0 = 1 and 1 = 1 (Ambulance priority)
        (False, True, True, False),    # 011 -> (0 or 1) and not 1 = 1 and 0 = 0 (Ambulance + Pedestrian)
        (True, False, False, True),    # 100 -> (1 or 0) and not 0 = 1 and 1 = 1 (High density flow)
        (True, False, True, False),    # 101 -> (1 or 0) and not 1 = 1 and 0 = 0 (High density + Pedestrian)
        (True, True, False, True),     # 110 -> (1 or 1) and not 0 = 1 and 1 = 1 (High density + Ambulance)
        (True, True, True, False),     # 111 -> (1 or 1) and not 1 = 1 and 0 = 0 (All active conflict)
    ]
)
def test_all_truth_table_combinations(p, q, r, expected_g):
    """Verify the proposition G = (P OR Q) AND NOT R across all 8 binary inputs."""
    p_or_q, not_r, g = compute_formula(p, q, r)
    assert g == expected_g
    assert p_or_q == (p or q)
    assert not_r == (not r)


def test_evaluate_traffic_proposition():
    """Verify evaluate_traffic_proposition mapping to active rows."""
    # Test Row 3: P=0, Q=1, R=0
    eval_row3 = evaluate_traffic_proposition(p=False, q=True, r=False)
    assert eval_row3.active_row == 3
    assert eval_row3.g is True
    assert "Ambulance" in eval_row3.description or "Emergency" in eval_row3.description

    # Test Row 8: P=1, Q=1, R=1
    eval_row8 = evaluate_traffic_proposition(p=True, q=True, r=True)
    assert eval_row8.active_row == 8
    assert eval_row8.g is False
    assert "Conflict" in eval_row8.description or "emergency" in eval_row8.description
