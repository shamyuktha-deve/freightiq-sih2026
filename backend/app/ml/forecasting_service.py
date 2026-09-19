# -*- coding: utf-8 -*-
"""forecasting_service.py
Backend service to generate freight rate forecasts for a given route.
Implements:
- Retrieval & cleaning of historical freight rates
- Chronological 80/20 train‑test split
- Evaluation of Naive and Holt‑Winters models
- Selection of the best model (lowest MAE on test split)
- Retraining on the full series and forecasting T+1 … T+14
- Approx. 80 % confidence intervals derived from model prediction intervals
- Persistence of forecasts to the ``forecasts`` table with provenance flag
"""

from typing import List
from datetime import timedelta, date
import logging

import pandas as pd
from sqlalchemy.orm import Session

from app.models.models import Forecast
from app.ml.preprocessing import get_clean_time_series, chronological_split
from app.ml.baseline_model import naive_forecast, holt_winters_forecast, evaluate_models
from app.ml.model_evaluation import evaluate_forecast

logger = logging.getLogger(__name__)

def _persist_forecasts(
    db: Session,
    route_id: str,
    base_date: date,
    forecasts: List[float],
    lower_bounds: List[float],
    upper_bounds: List[float],
    model_name: str,
    model_version: str = "1.0.0",
) -> List[Forecast]:
    """Create Forecast ORM objects and commit them.

    Parameters
    ----------
    db: Session – active DB session
    route_id: str – route identifier
    base_date: date – date of the last observed rate (forecast start)
    forecasts, lower_bounds, upper_bounds: lists of equal length (horizon)
    model_name, model_version: provenance strings
    """
    records = []
    for i, (pred, lo, hi) in enumerate(zip(forecasts, lower_bounds, upper_bounds), start=1):
        target = base_date + timedelta(days=i)
        rec = Forecast(
            route_id=route_id,
            target_date=target,
            horizon_days=i,
            predicted_rate=pred,
            ci_lower_80=lo,
            ci_upper_80=hi,
            model_name=model_name,
            model_version=model_version,
            is_simulated=True,  # output derived from simulated input; keep flag true
        )
        db.add(rec)
        records.append(rec)
    db.commit()
    for rec in records:
        db.refresh(rec)
    return records

def generate_forecast(db: Session, route_id: str, horizon: int = 14) -> List[Forecast]:
    """Generate and store forecasts for a route.

    Returns the list of persisted Forecast objects.
    """
    # 1. Retrieve and clean historical series
    data = get_clean_time_series(db, route_id, min_observations=horizon)
    if data.get("status") == "INSUFFICIENT_HISTORY":
        raise ValueError(f"Insufficient historical freight data for route {route_id}")

    series: pd.Series = data["series"]
    is_simulated = data.get("is_simulated", False)

    # 2. Chronological train/test split (80/20)
    train_series, test_series = chronological_split(series, train_ratio=0.8)
    if len(test_series) == 0:
        raise ValueError("Train/test split resulted in empty test set.")

    # 3. Evaluate models on the training split using the test horizon length
    eval_results = evaluate_models(train_series, test_series, horizon=len(test_series))
    # 4. Choose best model by lowest MAE on the test set
    best_name = min(
        eval_results,
        key=lambda n: evaluate_forecast(test_series, eval_results[n]["pred"])["mae"],
    )
    logger.info(f"Best model for route {route_id}: {best_name}")

    # 5. Retrain selected model on the full series and forecast the required horizon
    if best_name == "naive":
        forecasts, lower, upper = naive_forecast(series, horizon)
        model_version = "1.0.0"
    else:
        forecasts, lower, upper = holt_winters_forecast(series, horizon)
        model_version = "1.0.0"

    # 6. Persist forecasts
    last_observed_date = series.index[-1].date()
    persisted = _persist_forecasts(
        db=db,
        route_id=route_id,
        base_date=last_observed_date,
        forecasts=forecasts,
        lower_bounds=lower,
        upper_bounds=upper,
        model_name=best_name,
        model_version=model_version,
    )
    return persisted

def get_latest_forecasts(db: Session, route_id: str, horizon: int = 14) -> List[Forecast]:
    """Return the most recent forecast set for a route.
    Assumes forecasts are stored with a common ``forecast_generated_at`` timestamp.
    """
    subq = (
        db.query(Forecast.forecast_generated_at)
        .filter(Forecast.route_id == route_id)
        .order_by(Forecast.forecast_generated_at.desc())
        .limit(1)
        .subquery()
    )
    latest_ts = db.query(subq).scalar()
    if not latest_ts:
        return []
    rows = (
        db.query(Forecast)
        .filter(Forecast.route_id == route_id, Forecast.forecast_generated_at == latest_ts)
        .order_by(Forecast.horizon_days.asc())
        .limit(horizon)
        .all()
    )
    return rows
