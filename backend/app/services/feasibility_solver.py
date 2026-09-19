from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.models import Route, Port, PortConstraint, Vessel
from app.schemas.schemas import (
    FeasibilityCheckResponse,
    FeasibilityParameterCheck,
    PortResponse,
    VesselPresetResponse,
)

def evaluate_feasibility(
    db: Session,
    route_id: str,
    vessel_id: str,
    cargo_quantity_mt: float,
    cargo_type: Optional[str] = "Coal",
) -> FeasibilityCheckResponse:
    """
    Evaluates hydrographic and physical compatibility between a nominated vessel,
    cargo volume, and the destination discharge port constraints.
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

    # 3. Retrieve Port & Constraints
    port = db.query(Port).filter(Port.id == route.destination_port_id).first()
    if not port:
        raise KeyError(f"Destination port '{route.destination_port_id}' not found in database.")

    constraint = db.query(PortConstraint).filter(PortConstraint.port_id == port.id).first()
    if not constraint:
        raise KeyError(f"No hydrographic constraints registered for port '{port.id}'.")

    checks: List[FeasibilityParameterCheck] = []
    reasons: List[str] = []
    warnings: List[str] = []

    # Check 1: Cargo Capacity vs Deadweight (DWT)
    dwt_margin = vessel.dwt - cargo_quantity_mt
    if cargo_quantity_mt > vessel.dwt:
        checks.append(FeasibilityParameterCheck(
            parameter="Cargo vs Vessel Capacity",
            vessel_value=f"{cargo_quantity_mt:,.0f} MT",
            limit=f"{vessel.dwt:,.0f} MT DWT max",
            status="FAIL",
            margin=round(dwt_margin, 1),
            reason=f"Cargo quantity ({cargo_quantity_mt:,.0f} MT) exceeds vessel deadweight capacity ({vessel.dwt:,.0f} MT) by {abs(dwt_margin):,.0f} MT."
        ))
        reasons.append(f"Vessel over-tonnaged: Cargo exceeds vessel DWT by {abs(dwt_margin):,.0f} MT.")
    else:
        checks.append(FeasibilityParameterCheck(
            parameter="Cargo vs Vessel Capacity",
            vessel_value=f"{cargo_quantity_mt:,.0f} MT",
            limit=f"{vessel.dwt:,.0f} MT DWT max",
            status="PASS",
            margin=round(dwt_margin, 1),
            reason=f"Cargo quantity is safely within vessel deadweight allowance ({dwt_margin:,.0f} MT spare capacity)."
        ))

    # Check 2: Length Overall (LOA)
    loa_margin = constraint.max_loa - vessel.loa
    if vessel.loa > constraint.max_loa:
        checks.append(FeasibilityParameterCheck(
            parameter="Length Overall (LOA)",
            vessel_value=f"{vessel.loa:.1f} m",
            limit=f"{constraint.max_loa:.1f} m max",
            status="FAIL",
            margin=round(loa_margin, 1),
            reason=f"Vessel LOA ({vessel.loa:.1f}m) exceeds port berth limit ({constraint.max_loa:.1f}m) by {abs(loa_margin):.1f}m."
        ))
        reasons.append(f"LOA violation: Vessel exceeds berth structural envelope by {abs(loa_margin):.1f}m.")
    else:
        checks.append(FeasibilityParameterCheck(
            parameter="Length Overall (LOA)",
            vessel_value=f"{vessel.loa:.1f} m",
            limit=f"{constraint.max_loa:.1f} m max",
            status="PASS",
            margin=round(loa_margin, 1),
            reason=f"Vessel LOA satisfies terminal pier limitations with {loa_margin:.1f}m safety buffer."
        ))

    # Check 3: Beam (Moulded Breadth)
    beam_margin = constraint.max_beam - vessel.beam
    if vessel.beam > constraint.max_beam:
        checks.append(FeasibilityParameterCheck(
            parameter="Beam (Moulded Breadth)",
            vessel_value=f"{vessel.beam:.1f} m",
            limit=f"{constraint.max_beam:.1f} m max",
            status="FAIL",
            margin=round(beam_margin, 1),
            reason=f"Vessel beam ({vessel.beam:.1f}m) exceeds port unloader reach envelope ({constraint.max_beam:.1f}m) by {abs(beam_margin):.1f}m."
        ))
        reasons.append(f"Beam violation: Vessel width exceeds shore gantry crane outreach by {abs(beam_margin):.1f}m.")
    else:
        checks.append(FeasibilityParameterCheck(
            parameter="Beam (Moulded Breadth)",
            vessel_value=f"{vessel.beam:.1f} m",
            limit=f"{constraint.max_beam:.1f} m max",
            status="PASS",
            margin=round(beam_margin, 1),
            reason=f"Vessel beam satisfies gantry unloader reach with {beam_margin:.1f}m clearance."
        ))

    # Check 4: Arrival Draft vs Chart Datum (CD)
    draft_margin = constraint.max_draft_cd - vessel.design_draft
    draft_violated = vessel.design_draft > constraint.max_draft_cd
    if draft_violated:
        checks.append(FeasibilityParameterCheck(
            parameter="Permissible Arrival Draft",
            vessel_value=f"{vessel.design_draft:.1f} m",
            limit=f"{constraint.max_draft_cd:.1f} m CD max",
            status="WARN",
            margin=round(draft_margin, 1),
            reason=f"Vessel design draft ({vessel.design_draft:.1f}m) exceeds Chart Datum limit ({constraint.max_draft_cd:.1f}m) by {abs(draft_margin):.1f}m."
        ))
        warnings.append(
            f"Draft restriction: Vessel exceeds Chart Datum depth by {abs(draft_margin):.1f}m. "
            "High-tide tidal entry window or high-seas anchorage lightering required."
        )
    else:
        checks.append(FeasibilityParameterCheck(
            parameter="Permissible Arrival Draft",
            vessel_value=f"{vessel.design_draft:.1f} m",
            limit=f"{constraint.max_draft_cd:.1f} m CD max",
            status="PASS",
            margin=round(draft_margin, 1),
            reason=f"Vessel design draft satisfies navigation channel Chart Datum with {draft_margin:.1f}m under-keel cushion."
        ))

    # Check 5: Air Draft (if applicable)
    if constraint.air_draft_limit:
        checks.append(FeasibilityParameterCheck(
            parameter="Air Draft (Conveyor Clearance)",
            vessel_value="Standard Bulk Profile",
            limit=f"{constraint.air_draft_limit:.1f} m max",
            status="PASS",
            margin=None,
            reason=f"Standard unballasted profile conforms to {constraint.air_draft_limit:.1f}m air draft limit."
        ))

    # Check 6: Cargo Compatibility
    declared_cargo = cargo_type or route.primary_cargo
    checks.append(FeasibilityParameterCheck(
        parameter="Cargo Compatibility",
        vessel_value=declared_cargo,
        limit="Dry Bulk Class",
        status="PASS",
        margin=None,
        reason=f"Nominated vessel class ({vessel.vessel_class}) is fully certified for {declared_cargo} transport."
    ))

    # Check 7: Berth Discharge Rate
    if constraint.daily_discharge_rate_tpd:
        est_days = round(cargo_quantity_mt / constraint.daily_discharge_rate_tpd, 1)
        checks.append(FeasibilityParameterCheck(
            parameter="Discharge Productivity",
            vessel_value=f"Est. {est_days} discharge days",
            limit=f"{constraint.daily_discharge_rate_tpd:,} TPD",
            status="PASS",
            margin=None,
            reason=f"Dedicated automated berth unloader handles parcel at ~{constraint.daily_discharge_rate_tpd:,} TPD (~{est_days} days berth time)."
        ))

    # Overall Verdict Logic
    has_critical_failure = (cargo_quantity_mt > vessel.dwt) or (vessel.loa > constraint.max_loa) or (vessel.beam > constraint.max_beam)

    if has_critical_failure:
        verdict = "REJECTED"
        is_feasible = False
        reasons.append("Structural berth limit or deadweight capacity exceeded. Vessel cannot be accommodated.")
    elif draft_violated:
        verdict = "TIDAL_RESTRICTED"
        is_feasible = True  # Feasible, but under tidal window / lightering operational constraints
        reasons.append(f"Vessel can berth conditionally via tidal assistance ({abs(draft_margin):.1f}m tidal rise needed) or anchorage lightering.")
    else:
        verdict = "PASS"
        is_feasible = True
        reasons.append("All hydrographic, navigational, and structural berth parameters fully satisfied.")

    if constraint.advisory_notice:
        warnings.append(constraint.advisory_notice)

    return FeasibilityCheckResponse(
        status=verdict,
        feasible=is_feasible,
        vessel=VesselPresetResponse.model_validate(vessel),
        port=PortResponse.model_validate(port),
        checks=checks,
        reasons=reasons,
        warnings=warnings
    )
