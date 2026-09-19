# -*- coding: utf-8 -*-
"""preprocessing.py
Utility functions for preparing freight rate time series for forecasting.
"""

import pandas as pd
from sqlalchemy.orm import Session
from app.models.models import FreightRate

def get_clean_time_series(db: Session, route_id: str, min_observations: int = 14):
    """Retrieve and clean historical freight rates for a given route.
    Returns a dict containing a daily pandas Series (indexed by datetime) and metadata.
    Missing dates are detected and reported in ``missing_dates``; the series is forward‑filled
    **only for modeling purposes** to provide a regular frequency required by the forecasting
    models. No new market observations are fabricated.
    """
    records = (
        db.query(FreightRate)
        .filter(FreightRate.route_id == route_id)
        .order_by(FreightRate.rate_date.asc())
        .all()
    )
    if not records:
        return {"status": "INSUFFICIENT_HISTORY"}
    df = pd.DataFrame([
        {"date": r.rate_date, "spot_rate": r.spot_rate}
        for r in records
    ])
    # Drop duplicate dates, keep the most recent entry
    df = df.drop_duplicates(subset="date", keep="last")
    # Exclude non‑positive rates (invalid data)
    df = df[df["spot_rate"] > 0]
    df = df.sort_values("date")
    if len(df) < min_observations:
        return {"status": "INSUFFICIENT_HISTORY"}
    start = df["date"].iloc[0]
    end = df["date"].iloc[-1]
    full_range = pd.date_range(start=start, end=end, freq="D")
    # Identify missing dates for provenance reporting
    missing = full_range.difference(pd.to_datetime(df["date"]))
    missing_dates = [d.date() for d in missing]
    # Build a daily series and forward‑fill missing values deterministically for the model
    series = pd.Series(df["spot_rate"].values, index=pd.to_datetime(df["date"]))
    series = series.reindex(full_range, method="ffill")
    return {
        "route_id": route_id,
        "observations": len(series),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "missing_dates": missing_dates,
        "data_quality": "OK" if not missing_dates else "MISSING_DATES",
        "series": series,
    }

def chronological_split(series: pd.Series, train_ratio: float = 0.8):
    n = len(series)
    train_end = int(n * train_ratio)
    return series.iloc[:train_end], series.iloc[train_end:]
