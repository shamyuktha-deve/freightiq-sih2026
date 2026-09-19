import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.scenario_engine import evaluate_scenarios

client = TestClient(app)

def test_scenario_cost_calculation():
    """Verify freight cost = cargo * rate, waiting cost = demurrage * days, total = sum."""
    db = SessionLocal()
    try:
        cargo_mt = 75000
        waiting_days = 7
        res = evaluate_scenarios(
            db=db,
            route_id="australia-vizag",
            vessel_id="panamax",
            cargo_quantity_mt=cargo_mt,
            waiting_days=waiting_days
        )
        assert len(res.scenarios) == 3

        now_scen = next(s for s in res.scenarios if s.scenario == "BOOK_SPOT_NOW")
        wait_scen = next(s for s in res.scenarios if s.scenario == "WAIT_5_7_DAYS")
        alt_scen = next(s for s in res.scenarios if s.scenario == "ALTERNATIVE_VESSEL")

        # 1. Book spot now math
        expected_freight_now = round(cargo_mt * now_scen.freight_rate, 2)
        assert now_scen.freight_cost == expected_freight_now
        assert now_scen.waiting_cost == 0.0
        assert now_scen.total_cost == expected_freight_now

        # 2. Wait scenario math
        daily_dem = 17500.00  # Panamax demurrage
        expected_waiting_cost = round(daily_dem * waiting_days, 2)
        assert wait_scen.waiting_cost == expected_waiting_cost
        assert wait_scen.total_cost == round(wait_scen.freight_cost + expected_waiting_cost, 2)

        # 3. Alternative vessel
        assert alt_scen.total_cost == round(cargo_mt * alt_scen.freight_rate, 2)
    finally:
        db.close()

def test_alternative_vessel_selection():
    """Verify that an appropriate alternative vessel is identified from the database."""
    db = SessionLocal()
    try:
        res = evaluate_scenarios(db, "australia-paradip", "capesize", 140000)
        alt_scen = next(s for s in res.scenarios if s.scenario == "ALTERNATIVE_VESSEL")
        # For Capesize, alternative vessel should be Panamax
        assert "Panamax" in alt_scen.vessel_class or "Kamsarmax" in alt_scen.vessel_class
    finally:
        db.close()

def test_scenario_api_endpoint():
    """Test HTTP POST /api/v1/scenarios/evaluate returns 200 with 3 scenarios."""
    payload = {
        "route_id": "australia-paradip",
        "vessel_id": "capesize",
        "cargo_quantity_mt": 140000,
        "waiting_days": 7
    }
    response = client.post("/api/v1/scenarios/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["scenarios"]) == 3
    scenario_names = [s["scenario"] for s in data["scenarios"]]
    assert "BOOK_SPOT_NOW" in scenario_names
    assert "WAIT_5_7_DAYS" in scenario_names
    assert "ALTERNATIVE_VESSEL" in scenario_names
    assert "data_provenance" in data
