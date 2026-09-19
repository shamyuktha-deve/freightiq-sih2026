import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.risk_engine import evaluate_risk

client = TestClient(app)

def test_risk_scoring_six_dimensions():
    """Verify all 6 risk dimensions are calculated with scores, levels, reasons, and mitigations."""
    db = SessionLocal()
    try:
        res = evaluate_risk(
            db=db,
            route_id="australia-paradip",
            vessel_id="capesize",
            cargo_quantity_mt=140000
        )
        assert len(res.dimensions) == 6
        dim_names = [d.name for d in res.dimensions]
        assert "Freight Volatility" in dim_names
        assert "Forecast Uncertainty" in dim_names
        assert "Port Congestion" in dim_names
        assert "Vessel Feasibility" in dim_names
        assert "Delay & Demurrage" in dim_names
        assert "Data Quality" in dim_names

        for d in res.dimensions:
            assert 0 <= d.score <= 100
            assert d.level in ["LOW", "MEDIUM", "HIGH"]
            assert len(d.reason) > 5
            assert len(d.mitigation) > 5

        assert 0 <= res.overall_risk_score <= 100
        assert res.overall_risk_level in ["LOW", "MEDIUM", "HIGH"]
        assert "Simulated Benchmark Data" in res.data_provenance
    finally:
        db.close()

def test_risk_api_endpoint():
    """Test HTTP POST /api/v1/risk/evaluate endpoint."""
    payload = {
        "route_id": "australia-vizag",
        "vessel_id": "panamax",
        "cargo_quantity_mt": 75000
    }
    response = client.post("/api/v1/risk/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["dimensions"]) == 6
    assert "overall_risk_score" in data
    assert "overall_risk_level" in data
