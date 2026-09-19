# -*- coding: utf-8 -*-
"""forecasting_service.py
Provides the core forecasting workflow for Phase 3.
Functions:
- generate_forecast(db: Session, route_id: str, horizon: int) -> List[Forecast]
  Trains models, selects the best based on MAE, retrains on full series,
  produces T+1…T+{horizon} forecasts with 80 % CI, persists them, and returns the ORM objects.
- get_latest_forecasts(db: Session, route_id: str, limit: int = 14) -> List[Forecast]
  Retrieves the most recent horizon forecasts for a route.
"""

from typing import List
import pandas as pd
from sqlalchemy.orm import Session
from app.models.models import Forecast, FreightRate
from app.ml import preprocessing, baseline_model, model_evaluation, model_registry


def get_latest_forecasts(db: Session, route_id: str, limit: int = 14) -> List[Forecast]:
    """Return the most recent *limit* forecast rows for *route_id* ordered by target_date descending.
    If no forecasts exist, an empty list is returned.
    """
    return (
        db.query(Forecast)
        .filter(Forecast.route_id == route_id)
        .order_by(Forecast.target_date.desc())
        .limit(limit)
        .all()
    )


def generate_forecast(db: Session, route_id: str, horizon: int) -> List[Forecast]:
    """Generate and persist forecasts for a given *route_id*.

    Steps:
    1. Retrieve and clean the historical series via ``preprocessing.get_clean_time_series``.
       If the series is insufficient, raise ``ValueError``.
    2. Perform a chronological 80/20 train‑test split.
    3. Fit both Naive and Holt‑Winters models on the training split using
       ``baseline_model.evaluate_models`` which returns forecasts for the test horizon.
    4. Evaluate each model on the test split with ``model_evaluation.evaluate_forecast``
       and pick the one with the lowest MAE.
    5. Retrain the selected model on the **full** series and generate ``horizon``
       forward forecasts (including CI bounds).
    6. Persist each forecast row into the ``forecasts`` table, filling metadata:
       - model_name / model_version from ``model_registry.get_model_info``
       - is_simulated propagated from the underlying ``FreightRate`` records
         (if any historic row for the route has ``is_simulated=False`` then ``False``
         else ``True``).
    7. Return the list of persisted ``Forecast`` ORM objects.
    """
    # 1. Clean series
    ts_info = preprocessing.get_clean_time_series(db, route_id)
    if ts_info.get("status") == "INSUFFICIENT_HISTORY":
        raise ValueError(f"Insufficient historical data for route '{route_id}'.")
    series: pd.Series = ts_info["series"]

    # 2. Chronological split (80/20)
    train_series, test_series = preprocessing.chronological_split(series, train_ratio=0.8)
    if len(test_series) == 0:
        raise ValueError("Not enough data after chronological split for testing.")

    # 3. Evaluate both models on the training split
    eval_dict = baseline_model.evaluate_models(train_series, test_series)

    # 4. Compute metrics on the test set for each model
    metrics = {}
    for model_name, preds in eval_dict.items():
        mae_val = model_evaluation.mae(test_series.tolist(), preds["pred"])
        rmse_val = model_evaluation.rmse(test_series.tolist(), preds["pred"])
        mape_val = model_evaluation.mape(test_series.tolist(), preds["pred"])
        metrics[model_name] = {"mae": mae_val, "rmse": rmse_val, "mape": mape_val}

    # Select best model (lowest MAE)
    best_model_name = min(metrics, key=lambda k: metrics[k]["mae"])
    best_info = model_registry.get_model_info(best_model_name)

    # 5. Retrain on full series and produce horizon forecasts
    if best_model_name == "naive":
        forecasts, lower, upper = baseline_model.naive_forecast(series, horizon)
    else:
        forecasts, lower, upper = baseline_model.holt_winters_forecast(series, horizon)

    # 6. Determine is_simulated flag based on underlying freight rates
    any_real = (
        db.query(FreightRate)
        .filter(FreightRate.route_id == route_id, FreightRate.is_simulated.is_(False))
        .first()
        is not None
    )
    is_simulated_flag = not any_real

    # 7. Persist forecasts
    persisted = []
    now = pd.Timestamp.utcnow().to_pydatetime()
    for i in range(horizon):
        target_date = (series.index[-1] + pd.Timedelta(days=i + 1)).date()
        rec = Forecast(
            route_id=route_id,
            forecast_generated_at=now,
            target_date=target_date,
            horizon_days=i + 1,
            predicted_rate=forecasts[i],
            ci_lower_80=lower[i],
            ci_upper_80=upper[i],
            model_name=best_model_name,
            model_version=best_info["version"],
            is_simulated=is_simulated_flag,
        )
        db.add(rec)
        persisted.append(rec)
    db.commit()
    for rec in persisted:
        db.refresh(rec)
    return persisted
