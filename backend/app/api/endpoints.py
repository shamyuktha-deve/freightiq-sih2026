from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional

from app.database import get_db
from app.config import settings
from app.models.models import (
    Port,
    PortConstraint,
    Route,
    Vessel,
    FreightRate,
    DataSourceMetadata,
)
from app.schemas.schemas import (
    HealthResponse,
    PortResponse,
    PortConstraintResponse,
    RouteResponse,
    VesselPresetResponse,
    FreightHistoryResponse,
    FreightRateResponse,
    DataSourceMetadataResponse,
    CSVUploadResponse,
    FeasibilityCheckRequest,
    FeasibilityCheckResponse,
    ScenarioEvaluateRequest,
    ScenarioEvaluateResponse,
    RiskEvaluateRequest,
    RiskEvaluateResponse,
    RecommendationExplainResponse,
    DecisionAnalyzeRequest,
    DecisionAnalyzeResponse,
)
from app.services.csv_importer import parse_and_validate_csv
from app.services.feasibility_solver import evaluate_feasibility
from app.services.scenario_engine import evaluate_scenarios
from app.services.risk_engine import evaluate_risk
from app.services.xai_engine import generate_recommendation
from app.services.decision_engine import analyze_charter_decision

router = APIRouter()

# -------------------------------------------------------------
# Phase 1: Health & Metadata Endpoints
# -------------------------------------------------------------
@router.get("/health", response_model=HealthResponse, tags=["System Health"])
def get_health():
    """Returns backend system status, version, and database engine type."""
    db_type = "PostgreSQL" if "postgresql" in settings.DATABASE_URL.lower() else "SQLite"
    return HealthResponse(
        status="healthy",
        project="FreightIQ Backend - SIH26006",
        version=settings.VERSION,
        database=db_type,
        timestamp=datetime.utcnow()
    )

@router.get("/routes", response_model=List[RouteResponse], tags=["Routes"])
def get_routes(db: Session = Depends(get_db)):
    """Retrieve all bulk freight corridors."""
    routes = db.query(Route).all()
    return routes

@router.get("/ports", response_model=List[PortResponse], tags=["Ports & Constraints"])
def get_ports(db: Session = Depends(get_db)):
    """Retrieve all discharge ports and their associated berth limits."""
    ports = db.query(Port).all()
    return ports

@router.get("/ports/{port_id}/constraints", response_model=List[PortConstraintResponse], tags=["Ports & Constraints"])
def get_port_constraints(port_id: str, db: Session = Depends(get_db)):
    """Retrieve hydrographic and berth constraints for a specific discharge port."""
    port = db.query(Port).filter(Port.id == port_id).first()
    if not port:
        raise HTTPException(status_code=404, detail=f"Port with ID '{port_id}' not found.")
    return port.constraints

@router.get("/vessels/presets", response_model=List[VesselPresetResponse], tags=["Vessels"])
def get_vessel_presets(db: Session = Depends(get_db)):
    """Retrieve standard bulk carrier presets (Capesize, Kamsarmax, Panamax, Supramax, Handysize)."""
    vessels = db.query(Vessel).all()
    return vessels

@router.get("/freight/history", response_model=FreightHistoryResponse, tags=["Freight Data"])
def get_freight_history(
    route_id: str = Query(..., description="ID of the shipping corridor (e.g. 'australia-paradip')"),
    days: int = Query(30, ge=1, le=365, description="Number of historical days to fetch"),
    db: Session = Depends(get_db)
):
    """Retrieve historical freight rates for a route within the given lookback window."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail=f"Route with ID '{route_id}' not found.")

    since_date = (datetime.utcnow() - timedelta(days=days)).date()
    rates = (
        db.query(FreightRate)
        .filter(FreightRate.route_id == route_id, FreightRate.rate_date >= since_date)
        .order_by(FreightRate.rate_date.asc())
        .all()
    )

    is_sim = any(r.is_simulated for r in rates) if rates else True
    data_src = rates[0].data_source if rates else "FreightIQ Prototype Benchmark"

    return FreightHistoryResponse(
        route_id=route_id,
        total_records=len(rates),
        records=rates,
        is_simulated=is_sim,
        data_source=data_src
    )

@router.get("/data-sources", response_model=List[DataSourceMetadataResponse], tags=["Data Provenance"])
def get_data_sources(db: Session = Depends(get_db)):
    """Retrieve metadata on all registered data sources, confidence levels, and update frequencies."""
    sources = db.query(DataSourceMetadata).all()
    return sources

@router.post("/freight/upload-csv", response_model=CSVUploadResponse, tags=["Freight Data"])
async def upload_freight_csv(
    file: UploadFile = File(..., description="CSV file containing freight records"),
    db: Session = Depends(get_db)
):
    """Upload and validate a historical freight dataset without silent failures."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a valid .csv format.")

    content = await file.read()
    response = parse_and_validate_csv(
        file_content=content,
        filename=file.filename,
        db=db
    )
    return response

# -------------------------------------------------------------
# Phase 2: Decision Engines REST Endpoints
# -------------------------------------------------------------
# @router.post("/feasibility/check", response_model=FeasibilityCheckResponse, tags=["Decision Engines"])  # Placeholder - endpoint defined elsewhere

# -------------------------------------------------------------
# Phase 3: Forecasting Endpoints
# -------------------------------------------------------------

from app.schemas.schemas import ForecastGenerateRequest, ForecastGenerateResponse
from app.services.forecasting_service import generate_forecast, get_latest_forecasts

@router.post("/forecast/generate", response_model=ForecastGenerateResponse, tags=["Forecasting"])
def generate_route_forecast(req: ForecastGenerateRequest, db: Session = Depends(get_db)):
    """Generate and persist forecasts for a route using the best model.
    Returns the persisted Forecast records.
    """
    try:
        forecasts = generate_forecast(db=db, route_id=req.route_id, horizon=req.horizon)
        # Convert ORM objects to dicts for response (FastAPI will use Pydantic models)
        return ForecastGenerateResponse(forecasts=[f.__dict__ for f in forecasts])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/forecast/{route_id}", response_model=ForecastGenerateResponse, tags=["Forecasting"])
def get_route_forecast(route_id: str, db: Session = Depends(get_db)):
    """Retrieve the latest forecasts for a route. Returns up to the most recent 14 horizon forecasts."""
    forecasts = get_latest_forecasts(db, route_id)
    if not forecasts:
        raise HTTPException(status_code=404, detail=f"No forecasts found for route '{route_id}'.")
    return ForecastGenerateResponse(forecasts=[f.__dict__ for f in forecasts])

@router.post("/feasibility/check", response_model=FeasibilityCheckResponse, tags=["Decision Engines"])
def check_feasibility(req: FeasibilityCheckRequest, db: Session = Depends(get_db)):
    """Evaluates physical and hydrographic compatibility of a vessel and cargo quantity
    against the destination discharge port constraints.
    """
    try:
        res = evaluate_feasibility(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt,
            cargo_type=req.cargo_type,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/scenarios/evaluate", response_model=ScenarioEvaluateResponse, tags=["Decision Engines"])
def evaluate_scenarios_endpoint(req: ScenarioEvaluateRequest, db: Session = Depends(get_db)):
    """
    Evaluates three commercial chartering strategies:
    BOOK_SPOT_NOW, WAIT_5_7_DAYS, and ALTERNATIVE_VESSEL.
    Calculates exact freight bills, waiting demurrage costs, and net savings.
    """
    try:
        res = evaluate_scenarios(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt,
            waiting_days=req.waiting_days or 7,
            bunker_adjustment=req.bunker_adjustment or 0.0
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/risk/evaluate", response_model=RiskEvaluateResponse, tags=["Decision Engines"])
def evaluate_risk_endpoint(req: RiskEvaluateRequest, db: Session = Depends(get_db)):
    """
    Evaluates risk across six dimensions:
    Freight volatility, forecast uncertainty, port congestion, vessel feasibility,
    delay/demurrage exposure, and data quality.
    """
    try:
        res = evaluate_risk(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/recommendation/explain", response_model=RecommendationExplainResponse, tags=["Decision Engines"])
def explain_recommendation_endpoint(req: DecisionAnalyzeRequest, db: Session = Depends(get_db)):
    """
    Generates a structured, auditable explainable recommendation answering:
    WHEN?, WHICH VESSEL?, IS IT FEASIBLE?, WHAT ACTION?, WHY?, and KEY FACTORS.
    """
    try:
        feasibility_res = evaluate_feasibility(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt,
            cargo_type=req.cargo_type
        )
        scenarios_res = evaluate_scenarios(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt
        )
        risk_res = evaluate_risk(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt
        )
        rec_res = generate_recommendation(
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt,
            feasibility=feasibility_res,
            scenarios_resp=scenarios_res,
            risk=risk_res
        )
        return rec_res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decision/analyze", response_model=DecisionAnalyzeResponse, tags=["Decision Engines"])
def analyze_decision_endpoint(req: DecisionAnalyzeRequest, db: Session = Depends(get_db)):
    """
    Master Decision Endpoint orchestrating:
    Route ➔ Vessel ➔ Port Constraints ➔ Feasibility ➔ Forecast Data ➔
    Scenario Evaluation ➔ Risk Evaluation ➔ Explainable Recommendation.
    """
    try:
        res = analyze_charter_decision(
            db=db,
            route_id=req.route_id,
            vessel_id=req.vessel_id,
            cargo_quantity_mt=req.cargo_quantity_mt,
            cargo_type=req.cargo_type or "Coal"
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
