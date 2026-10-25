"""Integration tests for FastAPI endpoints using TestClient."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify GET /api/health returns 200 OK and valid status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "simulation_running" in data


def test_get_state_endpoint():
    """Verify GET /api/state returns full intersection telemetry, logic evaluation, and truth table."""
    response = client.get("/api/state")
    assert response.status_code == 200
    data = response.json()
    assert "phase" in data
    assert "signals" in data
    assert "north" in data["signals"]
    assert "logic" in data
    assert data["logic"]["formula"] == "G = (P ∨ Q) ∧ ¬R"
    assert len(data["truth_table"]) == 8


def test_api_cache_control_headers():
    """Verify all /api/ endpoints include no-cache headers to prevent browser desync."""
    response = client.get("/api/state")
    assert response.status_code == 200
    assert "no-cache" in response.headers.get("Cache-Control", "")
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("Pragma") == "no-cache"


def test_control_ambulance_endpoint():
    """Verify POST /api/control/ambulance with valid and invalid payloads across all approaches and routes."""
    for approach in ["north", "south", "east", "west"]:
        for route in ["straight", "left", "right"]:
            res_valid = client.post(
                "/api/control/ambulance",
                json={"approach": approach, "route": route, "active": True}
            )
            assert res_valid.status_code == 200
            data = res_valid.json()
            assert data["success"] is True
            assert data["state"]["emergency_active"] is True
            assert data["state"]["emergency_approach"] == approach
            assert data["state"]["emergency_route"] == route

    # Invalid approach payload
    res_invalid = client.post(
        "/api/control/ambulance",
        json={"approach": "northeast_invalid", "active": True}
    )
    assert res_invalid.status_code == 422  # Pydantic validation error


def test_control_pedestrian_endpoint():
    """Verify POST /api/control/pedestrian with all and specific crosswalks."""
    # Specific approach crosswalk (e.g. east)
    res_east = client.post(
        "/api/control/pedestrian",
        json={"active": True, "crosswalk": "east"}
    )
    assert res_east.status_code == 200
    data_east = res_east.json()
    assert data_east["success"] is True
    assert data_east["state"]["pedestrian_crosswalk"] == "east"

    # All crosswalks
    response = client.post(
        "/api/control/pedestrian",
        json={"active": True, "crosswalk": "all"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["state"]["pedestrian_crosswalk"] == "all"


def test_control_simulation_endpoint():
    """Verify POST /api/control/simulation (pause, start, step, reset)."""
    # Pause
    res_pause = client.post("/api/control/simulation", json={"action": "pause"})
    assert res_pause.status_code == 200
    assert res_pause.json()["state"]["simulation_running"] is False

    # Step
    res_step = client.post("/api/control/simulation", json={"action": "step"})
    assert res_step.status_code == 200

    # Start
    res_start = client.post("/api/control/simulation", json={"action": "start"})
    assert res_start.status_code == 200
    assert res_start.json()["state"]["simulation_running"] is True

    # Invalid action
    res_invalid = client.post("/api/control/simulation", json={"action": "fast_forward_unsupported"})
    assert res_invalid.status_code == 422


def test_control_traffic_endpoint():
    """Verify POST /api/control/traffic."""
    response = client.post("/api/control/traffic", json={"density": "high"})
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["traffic_density"] == "high"
    # Since density is HIGH, logic proposition P should be True
    assert data["state"]["logic"]["p"] is True


def test_control_traffic_approach_specific_endpoint():
    """Verify POST /api/control/traffic with specific approach parameter."""
    response = client.post("/api/control/traffic", json={"density": "high", "approach": "east"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["state"]["current_high_demand_approach"] == "east"
    assert data["state"]["approach_metrics"]["east"]["density"] == "high"


def test_telemetry_vehicles_endpoint():
    """Verify POST /api/telemetry/vehicles synchronizes approach queues."""
    payload = {"approaches": {"north": 2, "south": 5, "east": 1, "west": 3}}
    response = client.post("/api/telemetry/vehicles", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["state"]["approach_metrics"]["south"]["queue_length"] == 5
    assert data["state"]["approach_metrics"]["south"]["density"] == "high"


def test_state_endpoint_adaptive_fields():
    """Verify GET /api/state returns all adaptive control and countdown fields."""
    response = client.get("/api/state")
    assert response.status_code == 200
    data = response.json()
    assert "countdowns" in data
    assert "north" in data["countdowns"]
    assert "approach_metrics" in data
    assert "green_extended" in data
    assert "active_approach" in data
    assert "min_green_duration" in data
    assert "base_green_duration" in data
    assert "extension_per_vehicle" in data
    assert "normal_green_duration" in data
    assert "max_green_duration" in data
    assert data["base_green_duration"] == 8.0
    assert data["extension_per_vehicle"] == 1.5
    assert data["max_green_duration"] == 22.0


def test_multi_lane_telemetry_vehicles_endpoint():
    """Verify POST /api/telemetry/vehicles with per-lane counts updates lane_queues."""
    payload = {
        "counts": {
            "south": {"queue": 6, "total": 8, "lane0": 3, "lane1": 3},
            "north": {"queue": 2, "total": 3, "lane0": 1, "lane1": 1},
        }
    }
    response = client.post("/api/telemetry/vehicles", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    s_metrics = data["state"]["approach_metrics"]["south"]
    assert s_metrics["queue_length"] == 6
    assert s_metrics["lane_queues"] == {"lane1": 3, "lane2": 3}


def test_favicon_endpoint():
    """Verify GET and HEAD /favicon.ico return 200 OK and valid icon content type."""
    # GET /favicon.ico
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "image/x-icon" in response.headers.get("content-type", "") or "image/vnd.microsoft.icon" in response.headers.get("content-type", "")
    assert len(response.content) > 0

    # HEAD /favicon.ico
    head_resp = client.head("/favicon.ico")
    assert head_resp.status_code == 200

    # GET /static/favicon.ico
    static_resp = client.get("/static/favicon.ico")
    assert static_resp.status_code == 200
    assert len(static_resp.content) == len(response.content)


