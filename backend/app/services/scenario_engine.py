from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta

from app.models.models import Route, Vessel, FreightRate, Forecast
from app.schemas.schemas import ScenarioDetail, ScenarioEvaluateResponse
from app.services.feasibility_solver import evaluate_feasibility

def evaluate_scenarios(
    db: Session,
    route_id: str,
    vessel_id: str,
    cargo_quantity_mt: float,
    waiting_days: int = 7,
    bunker_adjustment: float = 0.0
) -> ScenarioEvaluateResponse:
    """
    Evaluates commercial strategies:
    1. BOOK_SPOT_NOW: Lock in currently observed spot rate at Day 0.
    2. WAIT_5_7_DAYS: Hold chartering for forecasted dip, incorporating demurrage cost.
    3. ALTERNATIVE_VESSEL: Switch vessel class to optimize draft or unit economies.
    """
    if cargo_quantity_mt <= 0:
        raise ValueError("Cargo quantity must be strictly positive.")

    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise KeyError(f"Route '{route_id}' not found.")

    vessel = db.query(Vessel).filter(Vessel.id == vessel_id).first()
    if not vessel:
        raise KeyError(f"Vessel '{vessel_id}' not found.")

    # 1. Feasibility of selected vessel
    feasibility = evaluate_feasibility(db, route_id, vessel_id, cargo_quantity_mt)
    selected_is_feasible = feasibility.feasible and (feasibility.status != "REJECTED")

    # 2. Get latest observed spot rate
    latest_rate_record = (
        db.query(FreightRate)
        .filter(FreightRate.route_id == route_id)
        .order_by(FreightRate.rate_date.desc())
        .first()
    )
    if not latest_rate_record:
        raise ValueError(f"No historical or spot freight rates available in database for route '{route_id}'.")

    current_spot_rate = latest_rate_record.spot_rate
    is_simulated = latest_rate_record.is_simulated

    # 3. Check for stored forecast record (~7 days horizon)
    forecast_record = (
        db.query(Forecast)
        .filter(Forecast.route_id == route_id, Forecast.horizon_days >= 5, Forecast.horizon_days <= 10)
        .order_by(Forecast.forecast_generated_at.desc())
        .first()
    )

    forecast_status = "FORECAST_AVAILABLE" if forecast_record else "FORECAST_NOT_AVAILABLE"

    # -------------------------------------------------------------
    # Scenario A: BOOK_SPOT_NOW
    # -------------------------------------------------------------
    now_freight_cost = round(cargo_quantity_mt * (current_spot_rate + bunker_adjustment), 2)
    now_waiting_cost = 0.0
    now_total_cost = now_freight_cost

    now_decision_factors = [
        f"Observed benchmark spot rate: ${current_spot_rate:.2f}/MT.",
        "Zero laycan waiting penalty (Day 0 market entry).",
        "Guarantees forward cargo delivery schedule without market volatility exposure."
    ]
    if not selected_is_feasible:
        now_decision_factors.append("WARNING: Nominated vessel fails port physical limits.")

    # -------------------------------------------------------------
    # Scenario B: WAIT_5_7_DAYS
    # -------------------------------------------------------------
    wait_days_int = max(1, waiting_days)
    daily_demurrage = vessel.daily_demurrage_rate or 22500.00
    wait_holding_cost = round(daily_demurrage * wait_days_int, 2)

    if forecast_record:
        wait_rate = forecast_record.predicted_rate
        expected_rate_change = round(wait_rate - current_spot_rate, 2)
        expected_rate_change_pct = round((expected_rate_change / current_spot_rate) * 100, 1)
        wait_freight_cost = round(cargo_quantity_mt * (wait_rate + bunker_adjustment), 2)
        wait_decision_factors = [
            f"Forecasted rate at Day +{forecast_record.horizon_days}: ${wait_rate:.2f}/MT ({expected_rate_change_pct:+.1f}%).",
            f"Holding / demurrage exposure for {wait_days_int} days: ${wait_holding_cost:,.2f}.",
            f"Net difference vs spot: ${wait_freight_cost + wait_holding_cost - now_total_cost:,.2f}."
        ]
    else:
        # Transparent data honesty: if no forecast exists, do NOT fabricate!
        wait_rate = current_spot_rate
        expected_rate_change = None
        expected_rate_change_pct = None
        wait_freight_cost = now_freight_cost
        wait_decision_factors = [
            "FORECAST_NOT_AVAILABLE: No forecast model output registered in database.",
            f"Holding cost of ${wait_holding_cost:,.2f} incurred over {wait_days_int} days without verified freight discount."
        ]

    wait_total_cost = round(wait_freight_cost + wait_holding_cost, 2)

    # -------------------------------------------------------------
    # Scenario C: ALTERNATIVE_VESSEL
    # -------------------------------------------------------------
    # Dynamically select an alternative vessel class from the DB
    all_vessels = db.query(Vessel).all()
    alt_vessel: Optional[Vessel] = None

    # Priority selection for alternative
    if vessel.vessel_class.lower() == "capesize":
        alt_vessel = next((v for v in all_vessels if v.vessel_class.lower() == "panamax"), None)
    elif vessel.vessel_class.lower() in ["panamax", "kamsarmax"]:
        alt_vessel = next((v for v in all_vessels if v.vessel_class.lower() in ["supramax", "capesize"]), None)
    else:
        alt_vessel = next((v for v in all_vessels if v.vessel_class.lower() == "panamax"), None)

    if not alt_vessel:
        alt_vessel = next((v for v in all_vessels if v.id != vessel.id), vessel)

    # Evaluate alternative vessel feasibility
    alt_feasibility = evaluate_feasibility(db, route_id, alt_vessel.id, min(cargo_quantity_mt, float(alt_vessel.dwt)))
    alt_is_feasible = alt_feasibility.feasible and (alt_feasibility.status != "REJECTED")

    # Unit rate adjustment for alternative class based on historical benchmark spread
    # (Smaller vessels incur slightly higher ton-mile rate, larger vessels have scale discount)
    if alt_vessel.dwt < vessel.dwt:
        alt_rate = round(current_spot_rate * 1.06, 2)  # +6% size premium for handier sizes
    elif alt_vessel.dwt > vessel.dwt:
        alt_rate = round(current_spot_rate * 0.94, 2)  # -6% scale economy
    else:
        alt_rate = current_spot_rate

    alt_freight_cost = round(cargo_quantity_mt * (alt_rate + bunker_adjustment), 2)
    alt_waiting_cost = 0.0
    alt_total_cost = alt_freight_cost

    alt_decision_factors = [
        f"Alternative vessel nomination: {alt_vessel.name} ({alt_vessel.vessel_class}).",
        f"Adjusted benchmark rate: ${alt_rate:.2f}/MT.",
        f"Berth hydrographic status: {alt_feasibility.status}."
    ]

    # -------------------------------------------------------------
    # Deterministic Scoring & Recommendation Logic
    # -------------------------------------------------------------
    # Case 1: Selected vessel fails berth limits
    if not selected_is_feasible:
        rec_now = False
        rec_wait = False
        rec_alt = alt_is_feasible

        score_now = 35
        score_wait = 25
        score_alt = 85 if alt_is_feasible else 40

    # Case 2: Selected vessel is feasible
    else:
        # If forecast exists and waiting yields net savings even after demurrage
        if forecast_record and (wait_total_cost < now_total_cost):
            rec_now = False
            rec_wait = True
            rec_alt = False
            score_wait = 88
            score_now = 72
            score_alt = 65
        else:
            rec_now = True
            rec_wait = False
            rec_alt = False
            score_now = 90
            score_wait = 60 if forecast_record else 45
            score_alt = 68

    scenarios = [
        ScenarioDetail(
            scenario="BOOK_SPOT_NOW",
            label="Book Spot Immediately",
            feasible=selected_is_feasible,
            vessel_class=vessel.vessel_class,
            freight_rate=current_spot_rate,
            freight_rate_type="OBSERVED_SPOT",
            cargo_quantity_mt=cargo_quantity_mt,
            freight_cost=now_freight_cost,
            waiting_days=0,
            waiting_cost=now_waiting_cost,
            total_cost=now_total_cost,
            expected_rate_change=0.0,
            expected_rate_change_pct=0.0,
            delay_risk="LOW",
            score=score_now,
            recommended=rec_now,
            decision_factors=now_decision_factors,
            forecast_status=forecast_status
        ),
        ScenarioDetail(
            scenario="WAIT_5_7_DAYS",
            label=f"Wait {wait_days_int} Days",
            feasible=selected_is_feasible,
            vessel_class=vessel.vessel_class,
            freight_rate=wait_rate,
            freight_rate_type="FORECAST" if forecast_record else "OBSERVED_SPOT",
            cargo_quantity_mt=cargo_quantity_mt,
            freight_cost=wait_freight_cost,
            waiting_days=wait_days_int,
            waiting_cost=wait_holding_cost,
            total_cost=wait_total_cost,
            expected_rate_change=expected_rate_change,
            expected_rate_change_pct=expected_rate_change_pct,
            delay_risk="MEDIUM" if wait_days_int > 5 else "LOW",
            score=score_wait,
            recommended=rec_wait,
            decision_factors=wait_decision_factors,
            forecast_status=forecast_status
        ),
        ScenarioDetail(
            scenario="ALTERNATIVE_VESSEL",
            label=f"Switch to {alt_vessel.vessel_class}",
            feasible=alt_is_feasible,
            vessel_class=alt_vessel.vessel_class,
            freight_rate=alt_rate,
            freight_rate_type="ALTERNATIVE_VESSEL_SPOT",
            cargo_quantity_mt=cargo_quantity_mt,
            freight_cost=alt_freight_cost,
            waiting_days=0,
            waiting_cost=alt_waiting_cost,
            total_cost=alt_total_cost,
            expected_rate_change=round(alt_rate - current_spot_rate, 2),
            expected_rate_change_pct=round(((alt_rate - current_spot_rate) / current_spot_rate) * 100, 1),
            delay_risk="LOW" if alt_is_feasible else "HIGH",
            score=score_alt,
            recommended=rec_alt,
            decision_factors=alt_decision_factors,
            forecast_status=forecast_status
        )
    ]

    data_provenance = (
        "Simulated Benchmark Data (SIH26006 Research Prototype)"
        if is_simulated
        else "Verified Historical Freight Data"
    )

    return ScenarioEvaluateResponse(
        route_id=route_id,
        selected_vessel_id=vessel_id,
        alternative_vessel_id=alt_vessel.id if alt_vessel else None,
        scenarios=scenarios,
        data_provenance=data_provenance
    )
