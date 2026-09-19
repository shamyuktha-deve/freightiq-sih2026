import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.decision_engine import analyze_charter_decision

client = TestClient(app)

def test_master_decision_feasible_vessel():
    """Verify complete decision object when vessel is feasible."""
    db = SessionLocal()
    try:
        res = analyze_charter_decision(
            db=db,
            route_id="australia-paradip",
            vessel_id="capesize",
            cargo_quantity_mt=140000
        )
        assert res.route.id == "australia-paradip"
        assert res.vessel.id == "capesize"
        assert res.feasibility.feasible is True
        assert len(res.scenarios) == 3
        assert len(res.risk.dimensions) == 6
        assert res.recommendation.recommended_action in ["BOOK_NOW", "WAIT", "ALTERNATIVE_VESSEL"]
        assert len(res.recommendation.why) >= 3
        assert len(res.recommendation.key_factors) >= 3
    finally:
        db.close()

def test_master_decision_infeasible_cargo_excess():
    """
    Verify that when cargo strictly exceeds all available fleet capacities,
    the recommendation appropriately flags NO_FEASIBLE_OPTION.
    """
    db = SessionLocal()
    try:
        res = analyze_charter_decision(
            db=db,
            route_id="australia-vizag",
            vessel_id="panamax",
            cargo_quantity_mt=250000  # Exceeds entire bulk fleet
        )
        assert res.feasibility.status == "REJECTED"
        assert res.feasibility.feasible is False
        assert res.recommendation.recommended_action == "NO_FEASIBLE_OPTION"
        assert "ALL NOMINATIONS INFEASIBLE" in res.recommendation.feasibility
    finally:
        db.close()

def test_master_decision_alternative_vessel_switch():
    """
    Verify that when the nominated vessel fails (e.g. Supramax with 70k MT),
    the system successfully selects and recommends a feasible alternative vessel (Panamax).
    """
    db = SessionLocal()
    try:
        # Supramax DWT is 58,000 MT. Cargo is 70,000 MT.
        # Supramax fails capacity, but alternative (Panamax DWT 75,000 MT) is feasible!
        res = analyze_charter_decision(
            db=db,
            route_id="indonesia-dhamra",
            vessel_id="supramax",
            cargo_quantity_mt=70000
        )
        assert res.feasibility.status == "REJECTED"
        assert res.feasibility.feasible is False
        assert res.recommendation.recommended_action == "ALTERNATIVE_VESSEL"
        assert "Panamax" in res.recommendation.which_vessel
        assert "PASS" in res.recommendation.feasibility
    finally:
        db.close()

def test_decision_api_analyze_endpoint():
    """Test HTTP POST /api/v1/decision/analyze endpoint integration."""
    payload = {
        "route_id": "australia-paradip",
        "vessel_id": "capesize",
        "cargo_quantity_mt": 140000,
        "cargo_type": "Coal"
    }
    response = client.post("/api/v1/decision/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "route" in data
    assert "vessel" in data
    assert "port" in data
    assert "feasibility" in data
    assert "forecast" in data
    assert "scenarios" in data
    assert "risk" in data
    assert "recommendation" in data
    assert data["recommendation"]["when"] != ""
    assert data["recommendation"]["which_vessel"] != ""
    assert data["recommendation"]["what_action"] != ""

def test_recommendation_explain_endpoint():
    """Test HTTP POST /api/v1/recommendation/explain endpoint."""
    payload = {
        "route_id": "australia-vizag",
        "vessel_id": "panamax",
        "cargo_quantity_mt": 75000,
        "cargo_type": "Coal"
    }
    response = client.post("/api/v1/recommendation/explain", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "recommended_action" in data
    assert len(data["why"]) >= 3
    assert len(data["key_factors"]) >= 3
