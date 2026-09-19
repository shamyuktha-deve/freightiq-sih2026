import math
from typing import List
from sqlalchemy.orm import Session

from app.models.models import Route, Vessel, FreightRate, Forecast, PortConstraint
from app.schemas.schemas import RiskDimension, RiskEvaluateResponse
from app.services.feasibility_solver import evaluate_feasibility

def evaluate_risk(
    db: Session,
    route_id: str,
    vessel_id: str,
    cargo_quantity_mt: float
) -> RiskEvaluateResponse:
    """
    Evaluates multi-dimensional risk across:
    1. Freight Volatility (historical standard deviation)
    2. Forecast Uncertainty (quantile interval spread or missing forecast flag)
    3. Port Congestion (berth throughput and queuing)
    4. Vessel Feasibility (hydrographic clearance verification)
    5. Delay / Demurrage Exposure (daily demurrage penalty sensitivity)
    6. Data Quality (benchmark provenance verification)
    """
    if cargo_quantity_mt <= 0:
        raise ValueError("Cargo quantity must be strictly greater than zero.")

    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise KeyError(f"Route '{route_id}' not found.")

    vessel = db.query(Vessel).filter(Vessel.id == vessel_id).first()
    if not vessel:
        raise KeyError(f"Vessel '{vessel_id}' not found.")

    constraint = db.query(PortConstraint).filter(PortConstraint.port_id == route.destination_port_id).first()

    dimensions: List[RiskDimension] = []

    # -------------------------------------------------------------
    # 1. Freight Volatility
    # -------------------------------------------------------------
    history_records = (
        db.query(FreightRate)
        .filter(FreightRate.route_id == route_id)
        .order_by(FreightRate.rate_date.desc())
        .limit(30)
        .all()
    )
    rates = [r.spot_rate for r in history_records]

    if len(rates) >= 2:
        mean_rate = sum(rates) / len(rates)
        variance = sum((x - mean_rate) ** 2 for x in rates) / (len(rates) - 1)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_rate if mean_rate > 0 else 0.0

        if cv < 0.05:
            vol_score = 25
            vol_level = "LOW"
        elif cv < 0.10:
            vol_score = 55
            vol_level = "MEDIUM"
        else:
            vol_score = 78
            vol_level = "HIGH"

        vol_reason = (
            f"Observed 30-day freight rate standard deviation is ${std_dev:.2f}/MT "
            f"(Coefficient of Variation: {cv * 100:.1f}%, Mean: ${mean_rate:.2f}/MT)."
        )
        vol_mitigation = "Implement trailing market limit order with shipowners to capture intra-week dips."
    else:
        vol_score = 50
        vol_level = "MEDIUM"
        vol_reason = "Limited historical rate observations in database; volatility estimated with moderate baseline."
        vol_mitigation = "Gather at least 14 days of rate records before fixing long-term COAs."

    dimensions.append(RiskDimension(
        name="Freight Volatility",
        score=vol_score,
        level=vol_level,
        reason=vol_reason,
        mitigation=vol_mitigation
    ))

    # -------------------------------------------------------------
    # 2. Forecast Uncertainty
    # -------------------------------------------------------------
    forecast_record = (
        db.query(Forecast)
        .filter(Forecast.route_id == route_id)
        .order_by(Forecast.forecast_generated_at.desc())
        .first()
    )

    if forecast_record:
        spread = forecast_record.ci_upper_80 - forecast_record.ci_lower_80
        relative_spread = (spread / forecast_record.predicted_rate) if forecast_record.predicted_rate > 0 else 0.2
        if relative_spread < 0.10:
            uncert_score = 22
            uncert_level = "LOW"
        elif relative_spread < 0.20:
            uncert_score = 48
            uncert_level = "MEDIUM"
        else:
            uncert_score = 75
            uncert_level = "HIGH"

        uncert_reason = (
            f"Forecast interval spread is ±${spread / 2:.2f}/MT at 80% confidence bound "
            f"(Model: {forecast_record.model_name})."
        )
        uncert_mitigation = f"Set protective stop-loss fixing trigger at ${forecast_record.ci_upper_80:.2f}/MT threshold."
    else:
        uncert_score = 70
        uncert_level = "HIGH"
        uncert_reason = (
            "FORECAST_NOT_AVAILABLE: No forecasting model has generated future curves for this corridor. "
            "Forward market movements cannot be statistically bounded."
        )
        uncert_mitigation = "Rely on prompt spot fixtures; commission statistical forecasting service in Phase 3."

    dimensions.append(RiskDimension(
        name="Forecast Uncertainty",
        score=uncert_score,
        level=uncert_level,
        reason=uncert_reason,
        mitigation=uncert_mitigation
    ))

    # -------------------------------------------------------------
    # 3. Port Congestion Risk
    # -------------------------------------------------------------
    daily_discharge = constraint.daily_discharge_rate_tpd if constraint else 40000
    if daily_discharge >= 50000:
        cong_score = 25
        cong_level = "LOW"
        cong_reason = f"Destination port features automated high-speed unloader (~{daily_discharge:,} TPD)."
        cong_mitigation = "Coordinate Notice of Readiness (NOR) directly with automated terminal dispatch."
    elif daily_discharge >= 40000:
        cong_score = 48
        cong_level = "MEDIUM"
        cong_reason = f"Standard mechanized unloader operating at ~{daily_discharge:,} TPD. Average turnaround is normal."
        cong_mitigation = "Time voyage speed (eco-steaming) to synchronize arrival with scheduled berth vacation."
    else:
        cong_score = 72
        cong_level = "HIGH"
        cong_reason = "Manual / slower conveyor discharge throughput. Higher susceptibility to anchorage queues."
        cong_mitigation = "Incorporate generous reversible laytime allowances in charter party negotiations."

    dimensions.append(RiskDimension(
        name="Port Congestion",
        score=cong_score,
        level=cong_level,
        reason=cong_reason,
        mitigation=cong_mitigation
    ))

    # -------------------------------------------------------------
    # 4. Vessel Feasibility Risk
    # -------------------------------------------------------------
    feasibility = evaluate_feasibility(db, route_id, vessel_id, cargo_quantity_mt)
    if feasibility.status == "PASS":
        feas_score = 15
        feas_level = "LOW"
        feas_reason = "Nominated vessel dimensions and draft fully satisfy all hydrographic berth limits."
        feas_mitigation = "Validate seasonal post-monsoon channel depth bulletins prior to arrival."
    elif feasibility.status == "TIDAL_RESTRICTED":
        feas_score = 65
        feas_level = "MEDIUM"
        feas_reason = "Vessel draft requires tidal assistance; direct berthing is restricted to high-water windows."
        feas_mitigation = "Check lunar tide tables; prepare anchorage lightering contingency if tide delays exceed 2 days."
    else:
        feas_score = 95
        feas_level = "HIGH"
        feas_reason = "CRITICAL: Nominated vessel exceeds port LOA, beam, or deadweight limits. Severe terminal turn-away risk."
        feas_mitigation = "Immediate re-nomination required: switch to a compliant vessel class (e.g. Panamax)."

    dimensions.append(RiskDimension(
        name="Vessel Feasibility",
        score=feas_score,
        level=feas_level,
        reason=feas_reason,
        mitigation=feas_mitigation
    ))

    # -------------------------------------------------------------
    # 5. Delay / Demurrage Exposure
    # -------------------------------------------------------------
    demurrage_rate = vessel.daily_demurrage_rate or 22500.00
    if feasibility.status == "REJECTED":
        dem_score = 90
        dem_level = "HIGH"
        dem_reason = f"Infeasible hull risks indefinite anchorage delay at ${demurrage_rate:,.2f}/day demurrage."
        dem_mitigation = "Do not tender Notice of Readiness for an infeasible vessel."
    elif feasibility.status == "TIDAL_RESTRICTED":
        dem_score = 60
        dem_level = "MEDIUM"
        dem_reason = f"Tidal holding delays of 1–2 days incur estimated demurrage exposure of ${demurrage_rate * 1.5:,.2f}."
        dem_mitigation = "Insert custom tide-waiting laytime exception clauses into rider terms."
    else:
        dem_score = 28
        dem_level = "LOW"
        dem_reason = f"Berth line-up is clear; 1-day queue allowance is well within standard laytime limits."
        dem_mitigation = "Maintain standard laytime definitions (SHINC / reversible)."

    dimensions.append(RiskDimension(
        name="Delay & Demurrage",
        score=dem_score,
        level=dem_level,
        reason=dem_reason,
        mitigation=dem_mitigation
    ))

    # -------------------------------------------------------------
    # 6. Data Quality Risk
    # -------------------------------------------------------------
    has_simulated = any(r.is_simulated for r in history_records) if history_records else True
    if has_simulated:
        dq_score = 45
        dq_level = "MEDIUM"
        dq_reason = (
            "Current rates originate from 'FreightIQ Prototype Benchmark Data'. "
            "Data is simulated for SIH research evaluation; live market movements may deviate."
        )
        dq_mitigation = "Integrate live satellite AIS and Baltic Exchange API feeds prior to commercial execution."
    else:
        dq_score = 15
        dq_level = "LOW"
        dq_reason = "Verified market fixtures with authentic historical audit trail."
        dq_mitigation = "Maintain automated daily data validation pipelines."

    dimensions.append(RiskDimension(
        name="Data Quality",
        score=dq_score,
        level=dq_level,
        reason=dq_reason,
        mitigation=dq_mitigation
    ))

    # -------------------------------------------------------------
    # Overall Composite Score Calculation
    # -------------------------------------------------------------
    weights = {
        "Freight Volatility": 0.20,
        "Forecast Uncertainty": 0.15,
        "Port Congestion": 0.15,
        "Vessel Feasibility": 0.30,  # Heavily penalizes infeasible nominations
        "Delay & Demurrage": 0.10,
        "Data Quality": 0.10,
    }

    weighted_score = sum(d.score * weights.get(d.name, 0.15) for d in dimensions)
    overall_score = int(round(weighted_score))

    if overall_score < 40:
        overall_level = "LOW"
    elif overall_score < 65:
        overall_level = "MEDIUM"
    else:
        overall_level = "HIGH"

    data_provenance = (
        "Simulated Benchmark Data (SIH26006 Research Prototype)"
        if has_simulated
        else "Verified Historical Freight Data"
    )

    return RiskEvaluateResponse(
        route_id=route_id,
        vessel_id=vessel_id,
        dimensions=dimensions,
        overall_risk_score=overall_score,
        overall_risk_level=overall_level,
        data_provenance=data_provenance
    )
