from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime

# -------------------------------------------------------------
# System & Meta Schemas
# -------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    project: str
    version: str
    database: str
    timestamp: datetime

class DataSourceMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    collection_date: Optional[date] = None
    confidence_rating: Optional[str] = None
    update_cadence: Optional[str] = None
    description: Optional[str] = None
    is_simulated: bool

# -------------------------------------------------------------
# Port & Route Schemas
# -------------------------------------------------------------
class PortConstraintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    port_id: str
    max_loa: float
    max_beam: float
    max_draft_cd: float
    air_draft_limit: Optional[float] = None
    min_ukc_pct: Optional[float] = 10.0
    daily_discharge_rate_tpd: Optional[int] = None
    advisory_notice: Optional[str] = None
    updated_at: Optional[datetime] = None

class PortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    terminal_name: str
    constraints: List[PortConstraintResponse] = []

class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_port: str
    origin_country: str
    destination_port_id: str
    primary_cargo: str
    typical_vessel_class: str
    distance_nautical_miles: Optional[int] = None
    average_transit_days: Optional[float] = None

class VesselPresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    vessel_class: str
    dwt: int
    loa: float
    beam: float
    design_draft: float
    daily_demurrage_rate: float

# -------------------------------------------------------------
# Freight Rate Schemas
# -------------------------------------------------------------
class FreightRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: str
    rate_date: date
    spot_rate: float
    currency: str
    unit: str
    data_source: str
    is_simulated: bool

class FreightHistoryResponse(BaseModel):
    route_id: str
    total_records: int
    records: List[FreightRateResponse]
    is_simulated: bool
    data_source: str

class CSVRowValidationError(BaseModel):
    row_number: int
    field: str
    error: str
    value: Optional[str] = None

class CSVUploadResponse(BaseModel):
    filename: str
    rows_received: int
    rows_inserted: int
    rows_rejected: int
    validation_errors: List[CSVRowValidationError]
    message: str

# -------------------------------------------------------------
# Phase 2: Feasibility Schemas
# -------------------------------------------------------------
class FeasibilityCheckRequest(BaseModel):
    route_id: str = Field(..., description="ID of the shipping route (e.g. 'australia-paradip')")
    vessel_id: str = Field(..., description="ID of the vessel preset (e.g. 'capesize')")
    cargo_quantity_mt: float = Field(..., gt=0, description="Cargo quantity in metric tons (must be > 0)")
    cargo_type: Optional[str] = Field("Coal", description="Cargo type declaration")

class FeasibilityParameterCheck(BaseModel):
    parameter: str
    vessel_value: Any
    limit: Any
    status: str  # PASS, FAIL, WARN
    margin: Optional[float] = None
    reason: str

class FeasibilityCheckResponse(BaseModel):
    status: str  # PASS, TIDAL_RESTRICTED, REJECTED
    feasible: bool
    vessel: VesselPresetResponse
    port: PortResponse
    checks: List[FeasibilityParameterCheck]
    reasons: List[str]
    warnings: List[str]

# -------------------------------------------------------------
# Phase 2: Scenario Engine Schemas
# -------------------------------------------------------------
class ScenarioEvaluateRequest(BaseModel):
    route_id: str = Field(..., description="ID of the route")
    vessel_id: str = Field(..., description="ID of the vessel")
    cargo_quantity_mt: float = Field(..., gt=0, description="Cargo quantity in MT (> 0)")
    waiting_days: Optional[int] = Field(7, ge=0, le=30, description="Anticipated laycan waiting days for wait strategy")
    bunker_adjustment: Optional[float] = Field(0.0, description="Optional bunker adjustment factor in $/MT")

class ScenarioDetail(BaseModel):
    scenario: str  # BOOK_SPOT_NOW, WAIT_5_7_DAYS, ALTERNATIVE_VESSEL
    label: str
    feasible: bool
    vessel_class: str
    freight_rate: float
    freight_rate_type: str  # OBSERVED_SPOT, FORECAST, ALTERNATIVE_VESSEL_SPOT
    cargo_quantity_mt: float
    freight_cost: float
    waiting_days: int
    waiting_cost: float
    total_cost: float
    expected_rate_change: Optional[float] = None
    expected_rate_change_pct: Optional[float] = None
    delay_risk: str
    score: int
    recommended: bool
    decision_factors: List[str]
    forecast_status: str

class ScenarioEvaluateResponse(BaseModel):
    route_id: str
    selected_vessel_id: str
    alternative_vessel_id: Optional[str] = None
    scenarios: List[ScenarioDetail]
    data_provenance: str

# -------------------------------------------------------------
# Phase 2: Risk Engine Schemas
# -------------------------------------------------------------
class RiskEvaluateRequest(BaseModel):
    route_id: str = Field(..., description="ID of the route")
    vessel_id: str = Field(..., description="ID of the vessel")
    cargo_quantity_mt: float = Field(..., gt=0, description="Cargo quantity in MT (> 0)")

class RiskDimension(BaseModel):
    name: str
    score: int  # 0 to 100
    level: str  # LOW, MEDIUM, HIGH
    reason: str
    mitigation: str

class RiskEvaluateResponse(BaseModel):
    route_id: str
    vessel_id: str
    dimensions: List[RiskDimension]
    overall_risk_score: int
    overall_risk_level: str
    data_provenance: str

# -------------------------------------------------------------
# Phase 2: Explainable Recommendation (E-XAI) Schemas
# -------------------------------------------------------------
class KeyFactor(BaseModel):
    factor: str
    impact: str  # POSITIVE, NEGATIVE, NEUTRAL
    value: str
    reason: str

class RecommendationExplainResponse(BaseModel):
    recommended_action: str  # BOOK_NOW, WAIT, ALTERNATIVE_VESSEL, NO_FEASIBLE_OPTION, INSUFFICIENT_DATA
    when: str
    which_vessel: str
    feasibility: str
    what_action: str
    why: List[str]
    key_factors: List[KeyFactor]
    data_provenance: str

# -------------------------------------------------------------
# Phase 2: Master Decision Engine Schemas
# -------------------------------------------------------------

class ForecastGenerateRequest(BaseModel):
    route_id: str = Field(..., description="ID of the route for which to generate forecasts")
    horizon: int = Field(14, ge=1, le=30, description="Number of future days to forecast (default 14)")

class ForecastRecord(BaseModel):
    id: int
    route_id: str
    forecast_generated_at: datetime
    target_date: date
    horizon_days: int
    predicted_rate: float
    ci_lower_80: float
    ci_upper_80: float
    model_name: str
    model_version: str
    is_simulated: bool

class ForecastGenerateResponse(BaseModel):
    forecasts: List[ForecastRecord]

class DecisionAnalyzeRequest(BaseModel):
    route_id: str = Field(..., description="ID of the shipping route")
    vessel_id: str = Field(..., description="ID of the vessel nomination")
    cargo_quantity_mt: float = Field(..., gt=0, description="Cargo quantity in MT (> 0)")
    cargo_type: Optional[str] = Field("Coal", description="Cargo type declaration")

class DecisionAnalyzeResponse(BaseModel):
    route: RouteResponse
    vessel: VesselPresetResponse
    port: PortResponse
    feasibility: FeasibilityCheckResponse
    forecast: Dict[str, Any]
    scenarios: List[ScenarioDetail]
    risk: RiskEvaluateResponse
    recommendation: RecommendationExplainResponse
    data_provenance: str
class DecisionAnalyzeRequest(BaseModel):
    route_id: str = Field(..., description="ID of the shipping route")
    vessel_id: str = Field(..., description="ID of the vessel nomination")
    cargo_quantity_mt: float = Field(..., gt=0, description="Cargo quantity in MT (> 0)")
    cargo_type: Optional[str] = Field("Coal", description="Cargo type declaration")

class DecisionAnalyzeResponse(BaseModel):
    route: RouteResponse
    vessel: VesselPresetResponse
    port: PortResponse
    feasibility: FeasibilityCheckResponse
    forecast: Dict[str, Any]
    scenarios: List[ScenarioDetail]
    risk: RiskEvaluateResponse
    recommendation: RecommendationExplainResponse
    data_provenance: str
