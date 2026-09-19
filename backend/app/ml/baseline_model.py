# -*- coding: utf-8 -*-
"""baseline_model.py
Utility functions for baseline and Holt‑Winters forecasting.
Provides:
- naive_forecast(series, horizon): simple last‑value forecast with 80 % confidence interval.
- holt_winters_forecast(series, horizon): Exponential Smoothing (additive trend, no seasonality).
- evaluate_models(train_series, test_series, horizon): returns forecasts for both models on the test horizon.
"""

from typing import Tuple, Dict
import numpy as np
import pandas as pd
import logging
from statsmodels.tsa.holtwinters import ExponentialSmoothing

logger = logging.getLogger(__name__)

def _calc_confidence_interval(residuals: np.ndarray, confidence: float = 0.80) -> float:
    """Return a symmetric half‑width for an approximate confidence interval.
    Uses the standard error of residuals and the normal quantile.
    """
    if residuals.size == 0:
        return 0.0
    sigma = np.std(residuals, ddof=1)
    # 80 % two‑sided => 10 % each tail => z≈1.28
    z = 1.28
    return z * sigma

def naive_forecast(series: pd.Series, horizon: int) -> Tuple[list, list, list]:
    """Naive last‑value forecast.

    Parameters
    ----------
    series: pd.Series – historical series indexed by datetime.
    horizon: int – number of future steps to forecast.

    Returns
    -------
    forecasts, lower_bounds, upper_bounds – each a list of length ``horizon``.
    """
    last_value = series.iloc[-1]
    forecasts = [last_value] * horizon
    residuals = series.diff().dropna().values
    half_width = _calc_confidence_interval(residuals)
    lower = [last_value - half_width] * horizon
    upper = [last_value + half_width] * horizon
    return forecasts, lower, upper

def holt_winters_forecast(series: pd.Series, horizon: int) -> Tuple[list, list, list]:
    """Holt‑Winters (Additive trend, no seasonality) forecast.
    Returns forecasts and approximate 80 % confidence intervals derived from residuals.
    """
    model = ExponentialSmoothing(series, trend="add", seasonal=None, damped_trend=False)
    fit = model.fit(optimized=True)
    forecasts = fit.forecast(steps=horizon).tolist()
    residuals = series - fit.fittedvalues
    half_width = _calc_confidence_interval(residuals.values)
    lower = [f - half_width for f in forecasts]
    upper = [f + half_width for f in forecasts]
    return forecasts, lower, upper

def evaluate_models(
    train_series: pd.Series,
    test_series: pd.Series,
    horizon: int = None,
) -> Dict[str, Dict]:
    """Generate forecasts for both naive and Holt‑Winters on a test split.

    Returns a dict keyed by model name containing ``pred`` and ``ci`` lists.
    If ``horizon`` is None, it defaults to the length of ``test_series``.
    """
    if horizon is None:
        horizon = len(test_series)
    naive_pred, naive_low, naive_up = naive_forecast(train_series, horizon)
    hw_pred, hw_low, hw_up = holt_winters_forecast(train_series, horizon)
    return {
        "naive": {"pred": naive_pred, "ci_lower": naive_low, "ci_upper": naive_up},
        "holt_winters": {"pred": hw_pred, "ci_lower": hw_low, "ci_upper": hw_up},
    }
