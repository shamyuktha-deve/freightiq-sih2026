# -*- coding: utf-8 -*-
"""model_evaluation.py
Utility functions to evaluate forecast accuracy.
Provides MAE, RMSE, and MAPE calculations.
"""

from typing import Dict
import numpy as np
import pandas as pd

def mae(y_true: pd.Series, y_pred: list) -> float:
    """Mean Absolute Error"""
    return float(np.mean(np.abs(y_true.values - np.array(y_pred))))

def rmse(y_true: pd.Series, y_pred: list) -> float:
    """Root Mean Squared Error"""
    return float(np.sqrt(np.mean((y_true.values - np.array(y_pred)) ** 2)))

def mape(y_true: pd.Series, y_pred: list) -> float:
    """Mean Absolute Percentage Error (percentage)
    Handles zero actuals by ignoring them in the denominator.
    """
    y_true_arr = y_true.values
    y_pred_arr = np.array(y_pred)
    mask = y_true_arr != 0
    if not np.any(mask):
        return float('inf')
    return float(np.mean(np.abs((y_true_arr[mask] - y_pred_arr[mask]) / y_true_arr[mask])) * 100)

def evaluate_forecast(y_true: pd.Series, y_pred: list) -> Dict[str, float]:
    """Return a dict with MAE, RMSE, MAPE."""
    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "mape": mape(y_true, y_pred),
    }
