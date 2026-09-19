from typing import List, Dict, Any
from app.schemas.schemas import (
    FeasibilityCheckResponse,
    ScenarioEvaluateResponse,
    RiskEvaluateResponse,
    RecommendationExplainResponse,
    KeyFactor,
)

def generate_recommendation(
    route_id: str,
    vessel_id: str,
    cargo_quantity_mt: float,
    feasibility: FeasibilityCheckResponse,
    scenarios_resp: ScenarioEvaluateResponse,
    risk: RiskEvaluateResponse,
) -> RecommendationExplainResponse:
    """
    Synthesizes an explainable, auditable chartering recommendation derived
    deterministically from hydrographic feasibility, scenario payoffs, and risk evaluation.
    This is a structured mathematical rule engine, not a generative chatbot.
    """
    why_bullets: List[str] = []
    key_factors: List[KeyFactor] = []

    # Map scenario details for easy lookup
    scen_map = {s.scenario: s for s in scenarios_resp.scenarios}
    now_scen = scen_map.get("BOOK_SPOT_NOW")
    wait_scen = scen_map.get("WAIT_5_7_DAYS")
    alt_scen = scen_map.get("ALTERNATIVE_VESSEL")

    # -------------------------------------------------------------
    # CASE 1: Infeasible Vessel (Structural or Capacity Failure)
    # -------------------------------------------------------------
    if feasibility.status == "REJECTED":
        if alt_scen and alt_scen.feasible:
            action = "ALTERNATIVE_VESSEL"
            when_text = "Immediate Re-Nomination"
            which_vessel_text = alt_scen.vessel_class
            feas_text = f"REJECTED for {feasibility.vessel.vessel_class} (PASS for {alt_scen.vessel_class})"
            what_action_text = f"Switch charter fixture from {feasibility.vessel.vessel_class} to {alt_scen.vessel_class}."

            why_bullets.append(
                f"Hydrographic Incompatibility: The nominated vessel ({feasibility.vessel.name}) exceeds destination "
                f"port limits ({', '.join(feasibility.reasons)})."
            )
            why_bullets.append(
                f"Feasible Alternative Available: Switching to {alt_scen.vessel_class} delivers full physical clearance "
                f"at {feasibility.port.name}, avoiding terminal turn-away."
            )
            why_bullets.append(
                f"Commercial Impact: Total estimated freight bill for {alt_scen.vessel_class} is ${alt_scen.total_cost:,.2f} "
                f"(${alt_scen.freight_rate:.2f}/MT), eliminating demurrage exposure of ${feasibility.vessel.daily_demurrage_rate:,.2f}/day."
            )
            why_bullets.append(
                "Immediate Action: Advise procurement and freight desk to substitute vessel nomination before laycan cutoff."
            )

            key_factors.append(KeyFactor(
                factor="Port Berth Dimensions",
                impact="NEGATIVE",
                value=f"Violated by {feasibility.vessel.vessel_class}",
                reason="Nominated hull exceeds terminal pier or channel limits."
            ))
            key_factors.append(KeyFactor(
                factor="Alternative Vessel Fit",
                impact="POSITIVE",
                value=f"{alt_scen.vessel_class} Compliant",
                reason="Alternative hull meets all navigation channel constraints."
            ))
            key_factors.append(KeyFactor(
                factor="Demurrage Penalty Risk",
                impact="NEGATIVE",
                value=f"${feasibility.vessel.daily_demurrage_rate:,.0f}/day",
                reason="Infeasible nomination risks terminal turn-away demurrage."
            ))
        else:
            action = "NO_FEASIBLE_OPTION"
            when_text = "Suspend Tender"
            which_vessel_text = "None Available"
            feas_text = "ALL NOMINATIONS INFEASIBLE"
            what_action_text = "Do not fix any vessel. Cargo volume or port constraints require renegotiation."
            why_bullets.append(
                f"Critical Infeasibility: Neither the nominated {feasibility.vessel.vessel_class} nor alternative fleet presets "
                f"can safely discharge {cargo_quantity_mt:,.0f} MT at {feasibility.port.name}."
            )
            why_bullets.append("Split-parcel shipment or high-seas anchorage lightering must be formally contracted.")

            key_factors.append(KeyFactor(
                factor="Berth Clearance",
                impact="NEGATIVE",
                value="Zero Feasible Hulls",
                reason="No registered vessel class meets port physical dimensions for this cargo volume."
            ))

    # -------------------------------------------------------------
    # CASE 2: Feasible Vessel (PASS or TIDAL_RESTRICTED)
    # -------------------------------------------------------------
    else:
        is_wait_recommended = wait_scen and wait_scen.recommended

        if is_wait_recommended:
            action = "WAIT"
            when_text = f"Wait {wait_scen.waiting_days} Days for Rate Trough"
            which_vessel_text = feasibility.vessel.vessel_class
            feas_text = "FEASIBLE (PASS)" if feasibility.status == "PASS" else "TIDAL RESTRICTED"
            what_action_text = f"Hold spot bids; implement trailing limit order at ${wait_scen.freight_rate:.2f}/MT."

            savings = (now_scen.total_cost - wait_scen.total_cost) if now_scen else 0.0
            why_bullets.append(
                f"Rate Trough Opportunity: Model projects a freight rate decrease to ${wait_scen.freight_rate:.2f}/MT "
                f"({wait_scen.expected_rate_change_pct:+.1f}%), yielding net savings of ${savings:,.2f} even after {wait_scen.waiting_days} days demurrage."
            )
            why_bullets.append(
                f"Berth Clearance Validated: {feasibility.vessel.vessel_class} satisfies {feasibility.port.name} "
                f"physical limits ({feasibility.status})."
            )
            why_bullets.append(
                f"Risk Profile: Overall risk index is {risk.overall_risk_score}/100 ({risk.overall_risk_level}), "
                "indicating market conditions favor patient charter timing."
            )

            key_factors.append(KeyFactor(
                factor="Forecast Rate Movement",
                impact="POSITIVE",
                value=f"{wait_scen.expected_rate_change_pct:+.1f}%",
                reason="Anticipated freight softening exceeds laycan holding cost."
            ))
            key_factors.append(KeyFactor(
                factor="Net Financial Payoff",
                impact="POSITIVE",
                value=f"${savings:,.2f} Savings",
                reason="Waiting strategy minimizes total landed procurement cost."
            ))
            key_factors.append(KeyFactor(
                factor="Port Hydrographic Fit",
                impact="POSITIVE" if feasibility.status == "PASS" else "NEUTRAL",
                value=feasibility.status,
                reason="Vessel navigation clearance verified."
            ))

        else:
            action = "BOOK_NOW"
            when_text = "Prompt Fixture (Within 48 Hours)"
            which_vessel_text = feasibility.vessel.vessel_class
            feas_text = "FEASIBLE (PASS)" if feasibility.status == "PASS" else "TIDAL RESTRICTED"
            what_action_text = f"Execute spot charter fixture at observed rate (${now_scen.freight_rate if now_scen else 0:.2f}/MT)."

            why_bullets.append(
                f"Schedule & Laycan Certainty: Immediate fixture at ${now_scen.freight_rate if now_scen else 0:.2f}/MT "
                f"(Total: ${now_scen.total_cost if now_scen else 0:,.2f}) eliminates laycan delay risk."
            )
            if wait_scen and wait_scen.forecast_status == "FORECAST_NOT_AVAILABLE":
                why_bullets.append(
                    "Data Prudence: Forward forecast models are currently unavailable in database; "
                    "waiting would incur holding cost without verified market discount evidence."
                )
            elif wait_scen and wait_scen.expected_rate_change_pct and wait_scen.expected_rate_change_pct > 0:
                why_bullets.append(
                    f"Rising Market Protection: Rates are projected to rise by +{wait_scen.expected_rate_change_pct:.1f}%; "
                    "fixing today prevents commercial budget escalation."
                )
            else:
                why_bullets.append(
                    "Demurrage Trade-off: Holding freight costs exceed potential rate discount."
                )

            why_bullets.append(
                f"Feasibility Status: Vessel conforms to {feasibility.port.name} terminal limits ({feasibility.status})."
            )

            key_factors.append(KeyFactor(
                factor="Spot Market Certainty",
                impact="POSITIVE",
                value=f"${now_scen.freight_rate if now_scen else 0:.2f}/MT",
                reason="Locks in verified baseline rate and eliminates laycan penalties."
            ))
            key_factors.append(KeyFactor(
                factor="Holding Demurrage Cost",
                impact="NEGATIVE",
                value=f"${feasibility.vessel.daily_demurrage_rate:,.0f}/day",
                reason="Waiting incurs daily demurrage that outweighs unproven market dips."
            ))
            key_factors.append(KeyFactor(
                factor="Port Hydrographic Fit",
                impact="POSITIVE" if feasibility.status == "PASS" else "NEUTRAL",
                value=feasibility.status,
                reason="Physical vessel dimensions satisfy port limits."
            ))

    # Add Data Quality Transparency Factor
    key_factors.append(KeyFactor(
        factor="Data Provenance",
        impact="NEUTRAL",
        value=scenarios_resp.data_provenance,
        reason="Decision grounded in recorded database benchmark rates."
    ))

    return RecommendationExplainResponse(
        recommended_action=action,
        when=when_text,
        which_vessel=which_vessel_text,
        feasibility=feas_text,
        what_action=what_action_text,
        why=why_bullets,
        key_factors=key_factors,
        data_provenance=scenarios_resp.data_provenance
    )
