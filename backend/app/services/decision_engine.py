from sqlalchemy.orm import Session
from app.models.models import Route, Vessel, Port, Forecast
from app.schemas.schemas import (
    DecisionAnalyzeResponse,
    RouteResponse,
    VesselPresetResponse,
    PortResponse,
)
from app.services.feasibility_solver import evaluate_feasibility
from app.services.scenario_engine import evaluate_scenarios
from app.services.risk_engine import evaluate_risk
from app.services.xai_engine import generate_recommendation

def analyze_charter_decision(
    db: Session,
    route_id: str,
    vessel_id: str,
    cargo_quantity_mt: float,
    cargo_type: str = "Coal",
) -> DecisionAnalyzeResponse:
    """
    Master Decision Engine orchestrating:
    Route ➔ Vessel ➔ Port constraints ➔ Feasibility ➔ Forecast data ➔
    Scenario evaluation ➔ Risk evaluation ➔ Explainable recommendation.
    """
    if cargo_quantity_mt <= 0:
        raise ValueError("Cargo quantity must be strictly greater than zero.")

    # 1. Retrieve Route
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise KeyError(f"Route '{route_id}' not found in database.")

    # 2. Retrieve Vessel
    vessel = db.query(Vessel).filter(Vessel.id == vessel_id).first()
    if not vessel:
        raise KeyError(f"Vessel '{vessel_id}' not found in database.")

    # 3. Retrieve Port
    port = db.query(Port).filter(Port.id == route.destination_port_id).first()
    if not port:
        raise KeyError(f"Destination port '{route.destination_port_id}' not found in database.")

    # 4. Feasibility Engine
    feasibility_res = evaluate_feasibility(
        db=db,
        route_id=route_id,
        vessel_id=vessel_id,
        cargo_quantity_mt=cargo_quantity_mt,
        cargo_type=cargo_type
    )

    # 5. Forecast Data (Honest reporting: if not generated, report unavailable)
    forecast_record = (
        db.query(Forecast)
        .filter(Forecast.route_id == route_id)
        .order_by(Forecast.forecast_generated_at.desc())
        .first()
    )
    if forecast_record:
        forecast_payload = {
            "status": "FORECAST_AVAILABLE",
            "model_name": forecast_record.model_name,
            "horizon_days": forecast_record.horizon_days,
            "predicted_rate": forecast_record.predicted_rate,
            "ci_lower_80": forecast_record.ci_lower_80,
            "ci_upper_80": forecast_record.ci_upper_80,
            "is_simulated": forecast_record.is_simulated
        }
    else:
        forecast_payload = {
            "status": "FORECAST_NOT_AVAILABLE",
            "message": "No forecast model records generated in database. Machine learning forecasting service is scheduled for Phase 3.",
            "is_simulated": True
        }

    # 6. Scenario Analysis Engine
    scenarios_res = evaluate_scenarios(
        db=db,
        route_id=route_id,
        vessel_id=vessel_id,
        cargo_quantity_mt=cargo_quantity_mt
    )

    # 7. Risk Evaluation Engine
    risk_res = evaluate_risk(
        db=db,
        route_id=route_id,
        vessel_id=vessel_id,
        cargo_quantity_mt=cargo_quantity_mt
    )

    # 8. Explainable Recommendation Engine (E-XAI)
    recommendation_res = generate_recommendation(
        route_id=route_id,
        vessel_id=vessel_id,
        cargo_quantity_mt=cargo_quantity_mt,
        feasibility=feasibility_res,
        scenarios_resp=scenarios_res,
        risk=risk_res
    )

    return DecisionAnalyzeResponse(
        route=RouteResponse.model_validate(route),
        vessel=VesselPresetResponse.model_validate(vessel),
        port=PortResponse.model_validate(port),
        feasibility=feasibility_res,
        forecast=forecast_payload,
        scenarios=scenarios_res.scenarios,
        risk=risk_res,
        recommendation=recommendation_res,
        data_provenance=scenarios_res.data_provenance
    )
